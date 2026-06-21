"""Binary sensor platform for GO Transit — 'catchable' decision sensor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import parsers
from .const import (
    BINARY_CATCHABLE,
    CONF_TRAVEL_TIME_FIXED,
    CONF_TRAVEL_TIME_SENSOR,
    DEFAULT_TRAVEL_TIME_FIXED,
    DOMAIN,
)
from .coordinator import DepartureCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coords = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GoTransitCatchableSensor(hass, coords["departures"], entry)])


class GoTransitCatchableSensor(CoordinatorEntity[DepartureCoordinator], BinarySensorEntity):
    """On when you can still make the next train from your boarding platform.

    Compares minutes-until-departure against live travel time (from a HA sensor
    if configured, else a fixed fallback). Cancelled trains stay On so you
    redirect to the next departure."""

    def __init__(self, hass: HomeAssistant, coordinator: DepartureCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{BINARY_CATCHABLE}"
        self._attr_name = f"{entry.title} — Catchable"
        self._attr_icon = "mdi:run-fast"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Metrolinx",
            model=coordinator.line_name or "GO Transit",
        )

    def _travel_minutes(self) -> float | None:
        """Read live travel time from the configured HA sensor (minutes).
        Falls back to the fixed value if the sensor is missing/unavailable."""
        sensor_id = self._entry.data.get(CONF_TRAVEL_TIME_SENSOR)
        fixed = self._entry.data.get(CONF_TRAVEL_TIME_FIXED, DEFAULT_TRAVEL_TIME_FIXED)
        if sensor_id:
            state = self._hass.states.get(sensor_id)
            if state and state.state not in ("unknown", "unavailable", None, ""):
                try:
                    return float(state.state)
                except (ValueError, TypeError):
                    _LOGGER.debug("Travel sensor %s state not numeric: %s", sensor_id, state.state)
        return float(fixed) if fixed is not None else None

    @property
    def is_on(self) -> bool:
        dep = (self.coordinator.data or {}).get("next_departure")
        if not dep:
            return False
        departure_time = dep.get("computed_time") or dep.get("scheduled_time")
        mins = parsers.minutes_until(departure_time)
        travel = self._travel_minutes()
        return parsers.is_catchable(mins, travel, dep.get("is_cancelled", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dep = (self.coordinator.data or {}).get("next_departure") or {}
        departure_time = dep.get("computed_time") or dep.get("scheduled_time")
        mins = parsers.minutes_until(departure_time)
        travel = self._travel_minutes()
        return {
            "minutes_to_departure": mins,
            "travel_minutes": travel,
            "departure_time": departure_time,
            "trip_number": dep.get("trip_number"),
            "is_cancelled": dep.get("is_cancelled", False),
            "travel_sensor": self._entry.data.get(CONF_TRAVEL_TIME_SENSOR),
            "updated_at": (self.coordinator.data or {}).get("updated_at"),
        }
