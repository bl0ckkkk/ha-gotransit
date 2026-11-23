"""Persist a per-route pin and publish changes from the existing feeds."""
import asyncio
import logging
from datetime import timedelta

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .commute import (
    CANCELLED,
    DESTINATION_NEXT,
    boarding_deadline,
    departure_alerts,
    destination_is_next,
    is_fresh,
)
from .const import DOMAIN
from .pinning import UNPINNED, active_pin, departure_options, go_datetime, make_pin, match_pinned_train

_LOGGER = logging.getLogger(__name__)


class PinnedTrainCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, departures, vehicles):
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_pinned")
        self.departures = departures
        self.vehicles = vehicles
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.pinned_train")
        self._lock = asyncio.Lock()
        self._alert_listener = None
        self._alert_task = None
        self._alert_refresh_pending = False

    async def async_load(self):
        self.async_set_updated_data(active_pin(await self._store.async_load(), dt_util.now()))

    @property
    def pin(self):
        return active_pin(self.data, dt_util.now())

    @property
    def choices(self):
        options = departure_options(
            self.departures.data or {}, self.departures.line_code, self.departures.to_stop_name
        )
        if pin := self.pin:
            options[pin["label"]] = pin
        return options

    @property
    def train(self):
        pin = self.pin
        if pin is None or not self.vehicles.last_update_success:
            return None
        data = self.vehicles.data or {}
        observed = go_datetime(data.get("feed_timestamp") or data.get("updated_at"))
        if not is_fresh(observed, dt_util.now(), timedelta(minutes=6)):
            return None
        return match_pinned_train(data.get("vehicle_positions", []), pin, self.departures.line_code, observed)

    @callback
    def is_watching_departure(self):
        pin = self.pin
        if not pin or pin.get("_commute", {}).get(CANCELLED):
            return False
        deadline = boarding_deadline(pin)
        return deadline is not None and dt_util.now() <= deadline

    async def async_select(self, option):
        async with self._lock:
            if option == UNPINNED:
                pin = None
            elif self.pin and option == self.pin["label"]:
                return
            else:
                departure = self.choices.get(option)
                if departure is None:
                    raise HomeAssistantError("That departure is no longer available. Select another train.")
                pin = make_pin(option, departure, dt_util.now())
                pin["_commute"] = {
                    "platform": str(departure.get("actual_platform") or "").strip(),
                    "computed_datetime": departure.get("computed_datetime"),
                }
            await self._store.async_save(pin)
            self.async_set_updated_data(pin)
        self._schedule_alerts()

    @callback
    def async_listen_for_alerts(self, listener):
        self._alert_listener = listener

        @callback
        def remove_listener():
            self._alert_listener = None
            self._alert_refresh_pending = False

        return remove_listener

    async def async_finish_pending_alerts(self):
        """Let any in-flight storage write complete before a config-entry reload."""
        if self._alert_task is not None:
            await asyncio.gather(self._alert_task, return_exceptions=True)

    @callback
    def async_feed_updated(self):
        self.async_update_listeners()
        self._schedule_alerts()

    @callback
    def _schedule_alerts(self):
        if self._alert_listener is None or self.pin is None:
            return
        self._alert_refresh_pending = True
        if self._alert_task is None or self._alert_task.done():
            self._alert_task = self.hass.async_create_task(self._async_check_pending_alerts())

    async def _async_check_pending_alerts(self):
        while self._alert_refresh_pending and self._alert_listener is not None:
            self._alert_refresh_pending = False
            async with self._lock:
                await self._async_evaluate_alerts()

    async def _async_evaluate_alerts(self):
        pin = self.pin
        listener = self._alert_listener
        if pin is None or listener is None:
            return

        now = dt_util.now()
        previous = pin.get("_commute", {})
        state = previous.copy()
        departure_data = self.departures.data or {}
        departure_time = go_datetime(departure_data.get("updated_at"))
        events = []
        if self.departures.last_update_success and is_fresh(departure_time, now, timedelta(minutes=4)):
            events = departure_alerts(pin, state, departure_data, now, self.departures.line_code)

        vehicle_data = self.vehicles.data or {}
        vehicle_time = go_datetime(vehicle_data.get("feed_timestamp"))
        if not state.get(CANCELLED) and not state.get(DESTINATION_NEXT) and is_fresh(
            vehicle_time, now, timedelta(seconds=90)
        ):
            train = self.train
            if train and destination_is_next(
                {**pin, "_commute": state}, train, self.departures.from_stop_code,
                self.departures.to_stop_code, vehicle_time,
            ):
                state[DESTINATION_NEXT] = True
                events.append((DESTINATION_NEXT, {"next_stop": self.departures.to_stop_code}))

        if state == previous:
            return
        pin = {**pin, "_commute": state}
        await self._store.async_save(pin)
        self.async_set_updated_data(pin)

        if self._alert_listener is listener:
            for event, attributes in events:
                listener(event, {
                    "trip_number": pin["trip_number"],
                    "departure_datetime": pin["departure_datetime"],
                    "origin": self.departures.from_stop_name,
                    "destination": self.departures.to_stop_name,
                    **attributes,
                })
