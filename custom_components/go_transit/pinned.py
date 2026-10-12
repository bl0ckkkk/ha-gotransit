"""Persist a per-route pin and publish changes from the existing feeds."""
import logging

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .pinning import UNPINNED, active_pin, departure_options, make_pin, match_train


class PinnedTrainCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, departures, vehicles):
        super().__init__(hass, logging.getLogger(__name__), name=f"{DOMAIN}_pinned")
        self.departures = departures
        self.vehicles = vehicles
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.pinned_train")

    async def async_load(self):
        self.async_set_updated_data(active_pin(await self._store.async_load(), dt_util.now()))

    @property
    def pin(self):
        return active_pin(self.data, dt_util.now())

    @property
    def choices(self):
        options = departure_options(self.departures.data or {})
        if self.pin:
            options[self.pin["label"]] = self.pin
        return options

    @property
    def train(self):
        pin = self.pin
        return match_train((self.vehicles.data or {}).get("vehicle_positions", []),
                           pin["trip_number"] if pin else None)

    async def async_select(self, option):
        if option == UNPINNED:
            pin = None
        elif self.pin and option == self.pin["label"]:
            return
        else:
            departure = self.choices.get(option)
            if departure is None:
                raise HomeAssistantError("That departure is no longer available. Select another train.")
            pin = make_pin(option, departure, dt_util.now())
        await self._store.async_save(pin)
        self.async_set_updated_data(pin)

    @callback
    def async_feed_updated(self):
        # Notify even when the pin itself is unchanged: choices/status may change.
        self.async_update_listeners()
