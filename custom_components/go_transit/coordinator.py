"""Data coordinators for GO Transit integration.

All response parsing is delegated to the pure functions in parsers.py
(which are unit-tested). Coordinators handle only I/O and scheduling.

  DepartureCoordinator  : next departure + schedule + cancellation  (2 min)
  VehicleCoordinator    : train positions                           (30s / 5min)
  AlertCoordinator      : service alerts                            (15 min)
  ConsistCoordinator    : coach count + car lineup                  (5 min)
  GuaranteeCoordinator  : service guarantee status                  (5 min)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import parsers
from .const import (
    BACKOFF_MAX_INTERVAL,
    BACKOFF_MULTIPLIER,
    BACKOFF_THRESHOLD,
    BASE_URL,
    DEFAULT_SERVICE_END,
    DEFAULT_SERVICE_START,
    DOMAIN,
    INTERVAL_ALERTS,
    INTERVAL_CONSIST,
    INTERVAL_DEPARTURES,
    INTERVAL_GUARANTEE,
    INTERVAL_VEHICLES_ACTIVE,
    INTERVAL_VEHICLES_IDLE,
)

_LOGGER = logging.getLogger(__name__)


async def _api_get(
    session: aiohttp.ClientSession, api_key: str, path: str, params: dict | None = None
) -> Any:
    url = f"{BASE_URL}/{path}"
    p = {"key": api_key}
    if params:
        p.update(params)
    try:
        async with session.get(url, params=p, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                raise UpdateFailed(f"GO API HTTP {resp.status} for {path}")
            text = await resp.text()
            try:
                return json.loads(text)
            except (ValueError, TypeError) as err:
                raise UpdateFailed(f"GO API non-JSON response for {path}: {text[:120]}") from err
    except aiohttp.ClientError as err:
        raise UpdateFailed(f"Network error for {path}: {err}") from err


class _GoTransitBase(DataUpdateCoordinator):
    def __init__(
        self, hass: HomeAssistant, name: str, api_key: str,
        from_stop_code: str, from_stop_name: str,
        to_stop_code: str, to_stop_name: str,
        line_code: str, line_name: str, max_departures: int,
        commute_start: str, commute_end: str, update_interval: timedelta,
    ) -> None:
        super().__init__(hass, _LOGGER, name=name, update_interval=update_interval)
        self.api_key = api_key
        self.from_stop_code = from_stop_code
        self.from_stop_name = from_stop_name
        self.to_stop_code = to_stop_code
        self.to_stop_name = to_stop_name
        self.line_code = line_code
        self.line_name = line_name
        self.max_departures = max_departures
        self.commute_start = commute_start
        self.commute_end = commute_end
        self._session = async_get_clientsession(hass)
        self.last_raw: dict[str, Any] = {}
        # Backoff state
        self._base_interval = update_interval
        self._consecutive_failures = 0
        # Service-hours window (when no trains run, departure-type coords pause)
        self.service_start = DEFAULT_SERVICE_START
        self.service_end = DEFAULT_SERVICE_END
        # Subclasses set this True if they should pause outside service hours
        self.pause_outside_service = False

    async def _get(self, path: str, params: dict | None = None) -> Any:
        try:
            data = await _api_get(self._session, self.api_key, path, params)
            self._note_success()
            return data
        except UpdateFailed:
            self._note_failure()
            raise

    def _note_success(self) -> None:
        if self._consecutive_failures:
            self._consecutive_failures = 0
            self.update_interval = self._base_interval

    def _note_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= BACKOFF_THRESHOLD:
            backed_off = min(
                self._base_interval.total_seconds()
                * (BACKOFF_MULTIPLIER ** (self._consecutive_failures - BACKOFF_THRESHOLD + 1)),
                BACKOFF_MAX_INTERVAL,
            )
            self.update_interval = timedelta(seconds=backed_off)
            _LOGGER.warning(
                "%s: %d consecutive failures, backing off to %ds",
                self.name, self._consecutive_failures, int(backed_off),
            )

    def _service_paused(self) -> bool:
        """True if this coordinator should skip the fetch (outside service hours)."""
        if not self.pause_outside_service:
            return False
        return not parsers.in_service_hours(self.service_start, self.service_end)


class DepartureCoordinator(_GoTransitBase):
    def __init__(self, hass, api_key, from_stop_code, from_stop_name,
                 to_stop_code, to_stop_name, line_code, line_name,
                 max_departures, commute_start, commute_end):
        super().__init__(
            hass, f"{DOMAIN}_departures", api_key,
            from_stop_code, from_stop_name, to_stop_code, to_stop_name,
            line_code, line_name, max_departures, commute_start, commute_end,
            timedelta(seconds=INTERVAL_DEPARTURES),
        )
        self.pause_outside_service = True

    async def _async_update_data(self) -> dict:
        now = datetime.now()
        # Skip the fetch overnight when no trains run — preserve last data.
        if self._service_paused():
            return self.data or {
                "next_departure": None, "departures": [], "delay_seconds": None,
                "from_stop": self.from_stop_name, "to_stop": self.to_stop_name,
                "line": self.line_name, "updated_at": now.isoformat(),
                "service_paused": True,
            }
        result: dict[str, Any] = {
            "next_departure": None, "departures": [], "delay_seconds": None,
            "from_stop": self.from_stop_name, "to_stop": self.to_stop_name,
            "line": self.line_name, "updated_at": now.isoformat(),
        }

        # Next service
        try:
            raw = await self._get(f"Stop/NextService/{self.from_stop_code}")
            self.last_raw["next_service"] = raw
            result["next_departure"] = parsers.parse_next_service(raw, self.line_code, self.to_stop_name)
        except UpdateFailed as err:
            _LOGGER.warning("Next service fetch failed: %s", err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Next service unexpected error: %s", err)

        # Journey schedule
        try:
            date_str = now.strftime("%Y%m%d")
            time_str = now.strftime("%H:%M")
            raw = await self._get(
                f"Schedule/Journey/{date_str}/{self.from_stop_code}"
                f"/{self.to_stop_code}/{time_str}/{self.max_departures}"
            )
            self.last_raw["journey"] = raw
            journeys = parsers._as_list(raw.get("Journey", {}).get("Trips", {}).get("Trip"))
            result["departures"] = [
                {
                    "trip_number": t.get("TripNumber"),
                    "departure_time": t.get("DepartureTime"),
                    "arrival_time": t.get("ArrivalTime"),
                    "duration": t.get("Duration"),
                    "line": t.get("LineName"),
                    "status": t.get("Status", "Scheduled"),
                }
                for t in journeys
            ]
        except UpdateFailed as err:
            _LOGGER.warning("Journey fetch failed: %s", err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Journey unexpected error: %s", err)

        # Exceptions / cancellation
        if result["next_departure"]:
            trip_number = result["next_departure"].get("trip_number")
            try:
                raw = await self._get("ServiceUpdate/Exceptions/All")
                self.last_raw["exceptions"] = raw
                exc = parsers.parse_exceptions(raw, trip_number, self.from_stop_code)
                if exc["matched"]:
                    result["next_departure"]["is_cancelled"] = exc["is_cancelled"]
                    result["next_departure"]["stop_is_cancelled"] = exc["stop_is_cancelled"]
                    result["next_departure"]["stop_is_stopping"] = exc["stop_is_stopping"]
                    result["next_departure"]["stop_actual_time"] = exc["stop_actual_time"]
            except UpdateFailed as err:
                _LOGGER.warning("Exceptions fetch failed: %s", err)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Exceptions unexpected error: %s", err)

        if result["next_departure"]:
            delay = result["next_departure"].get("delay_minutes")
            result["delay_seconds"] = (delay or 0) * 60

        return result


class VehicleCoordinator(_GoTransitBase):
    def __init__(self, hass, api_key, from_stop_code, from_stop_name,
                 to_stop_code, to_stop_name, line_code, line_name,
                 max_departures, commute_start, commute_end):
        super().__init__(
            hass, f"{DOMAIN}_vehicles", api_key,
            from_stop_code, from_stop_name, to_stop_code, to_stop_name,
            line_code, line_name, max_departures, commute_start, commute_end,
            timedelta(seconds=INTERVAL_VEHICLES_ACTIVE),
        )

    async def _async_update_data(self) -> dict:
        active = parsers.in_commute_window(self.commute_start, self.commute_end)
        self.update_interval = timedelta(
            seconds=INTERVAL_VEHICLES_ACTIVE if active else INTERVAL_VEHICLES_IDLE
        )
        result: dict[str, Any] = {
            "vehicle_positions": [], "in_commute_window": active,
            "updated_at": datetime.now().isoformat(),
        }
        try:
            raw = await self._get("ServiceataGlance/Trains/All")
            self.last_raw["trains"] = raw
            result["vehicle_positions"] = parsers.parse_trains(raw, self.line_code)
        except UpdateFailed as err:
            _LOGGER.warning("Vehicle fetch failed: %s", err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Vehicle unexpected error: %s", err)
        return result


class AlertCoordinator(_GoTransitBase):
    def __init__(self, hass, api_key, from_stop_code, from_stop_name,
                 to_stop_code, to_stop_name, line_code, line_name,
                 max_departures, commute_start, commute_end):
        super().__init__(
            hass, f"{DOMAIN}_alerts", api_key,
            from_stop_code, from_stop_name, to_stop_code, to_stop_name,
            line_code, line_name, max_departures, commute_start, commute_end,
            timedelta(seconds=INTERVAL_ALERTS),
        )

    async def _async_update_data(self) -> dict:
        result: dict[str, Any] = {"alerts": [], "updated_at": datetime.now().isoformat()}
        try:
            raw = await self._get("ServiceUpdate/ServiceAlert/All")
            self.last_raw["alerts"] = raw
            result["alerts"] = parsers.parse_alerts(raw, self.line_code)
        except UpdateFailed as err:
            _LOGGER.warning("Alert fetch failed: %s", err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Alert unexpected error: %s", err)
        return result


class ConsistCoordinator(_GoTransitBase):
    def __init__(self, hass, api_key, from_stop_code, from_stop_name,
                 to_stop_code, to_stop_name, line_code, line_name,
                 max_departures, commute_start, commute_end,
                 departure_coordinator: "DepartureCoordinator"):
        super().__init__(
            hass, f"{DOMAIN}_consist", api_key,
            from_stop_code, from_stop_name, to_stop_code, to_stop_name,
            line_code, line_name, max_departures, commute_start, commute_end,
            timedelta(seconds=INTERVAL_CONSIST),
        )
        self._dep = departure_coordinator
        self.pause_outside_service = True

    async def _async_update_data(self) -> dict:
        result: dict[str, Any] = {
            "coach_count": None, "engine_number": None, "consist_number": None,
            "lineup": [], "trip_number": None, "updated_at": datetime.now().isoformat(),
        }
        if self._service_paused():
            return self.data or result
        trip_number = ((self._dep.data or {}).get("next_departure") or {}).get("trip_number")
        if not trip_number:
            return result
        result["trip_number"] = trip_number
        try:
            raw = await self._get("Fleet/Consist/All")
            self.last_raw["consist"] = raw
            parsed = parsers.parse_consist(raw, trip_number)
            result.update(parsed)
        except UpdateFailed as err:
            _LOGGER.warning("Consist fetch failed: %s", err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Consist unexpected error: %s", err)
        return result


class GuaranteeCoordinator(_GoTransitBase):
    def __init__(self, hass, api_key, from_stop_code, from_stop_name,
                 to_stop_code, to_stop_name, line_code, line_name,
                 max_departures, commute_start, commute_end,
                 departure_coordinator: "DepartureCoordinator"):
        super().__init__(
            hass, f"{DOMAIN}_guarantee", api_key,
            from_stop_code, from_stop_name, to_stop_code, to_stop_name,
            line_code, line_name, max_departures, commute_start, commute_end,
            timedelta(seconds=INTERVAL_GUARANTEE),
        )
        self._dep = departure_coordinator
        self.pause_outside_service = True

    async def _async_update_data(self) -> dict:
        result: dict[str, Any] = {
            "guarantee_active": False, "trip_number": None,
            "affected_stops": [], "reason": None,
            "updated_at": datetime.now().isoformat(),
        }
        if self._service_paused():
            return self.data or result
        trip_number = ((self._dep.data or {}).get("next_departure") or {}).get("trip_number")
        if not trip_number:
            return result
        result["trip_number"] = trip_number
        today = datetime.now().strftime("%Y%m%d")
        try:
            raw = await self._get(f"ServiceUpdate/ServiceGuarantee/{trip_number}/{today}")
            self.last_raw["guarantee"] = raw
            parsed = parsers.parse_guarantee(raw, self.from_stop_code)
            result.update(parsed)
        except UpdateFailed as err:
            _LOGGER.debug("Guarantee returned no data for trip %s: %s", trip_number, err)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Guarantee unexpected error: %s", err)
        return result
