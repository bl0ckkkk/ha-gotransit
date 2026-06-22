"""Sensor platform for GO Transit integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    SENSOR_ALERTS,
    SENSOR_CONSIST,
    SENSOR_DELAY,
    SENSOR_DEPARTURES,
    SENSOR_GUARANTEE,
    SENSOR_NEXT_DEPARTURE,
    SENSOR_PLATFORM,
    SENSOR_STATUS,
    SENSOR_VEHICLE_POSITION,
)
from .coordinator import (
    AlertCoordinator,
    ConsistCoordinator,
    DepartureCoordinator,
    GuaranteeCoordinator,
    VehicleCoordinator,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coords = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        GoTransitNextDepartureSensor(coords["departures"], entry),
        GoTransitPlatformSensor(coords["departures"], entry),
        GoTransitStatusSensor(coords["departures"], entry),
        GoTransitDelaySensor(coords["departures"], entry),
        GoTransitDeparturesSensor(coords["departures"], entry),
        GoTransitVehiclePositionSensor(coords["vehicles"], entry),
        GoTransitAlertsSensor(coords["alerts"], entry),
        GoTransitConsistSensor(coords["consist"], entry),
        GoTransitGuaranteeSensor(coords["guarantee"], entry),
    ])


def _device(entry: ConfigEntry, line_name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Metrolinx",
        model=line_name or "GO Transit",
    )


class GoTransitNextDepartureSensor(CoordinatorEntity[DepartureCoordinator], SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: DepartureCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_NEXT_DEPARTURE}"
        self._attr_name = "Next Departure"
        self._attr_icon = "mdi:train"
        self._attr_device_info = _device(entry, coordinator.line_name)

    @property
    def native_value(self) -> datetime | None:
        """The next departure as a tz-aware datetime so HA renders it as a
        clock time plus a relative 'in X minutes' countdown."""
        dep = self.coordinator.data.get("next_departure")
        if not dep:
            return None
        # Prefer the full API datetimes ('YYYY-MM-DD HH:MM:SS', naive local).
        raw = dep.get("computed_datetime") or dep.get("scheduled_datetime")
        parsed = dt_util.parse_datetime(raw) if raw else None
        if parsed is None:
            # Fall back to a bare 'HH:MM', anchored to today's local date.
            hhmm = dep.get("computed_time") or dep.get("scheduled_time")
            if not hhmm:
                return None
            try:
                t = datetime.strptime(hhmm, "%H:%M").time()
            except ValueError:
                return None
            parsed = dt_util.now().replace(
                hour=t.hour, minute=t.minute, second=0, microsecond=0, tzinfo=None
            )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        return parsed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dep = self.coordinator.data.get("next_departure") or {}
        return {
            "trip_number": dep.get("trip_number"),
            "destination": dep.get("destination"),
            "line": dep.get("line_name"),
            "service_type": dep.get("service_type"),
            "direction": dep.get("direction_code"),
            "scheduled_time": dep.get("scheduled_time"),
            "computed_time": dep.get("computed_time"),
            "departure_status": dep.get("departure_status"),
            "scheduled_platform": dep.get("scheduled_platform"),
            "actual_platform": dep.get("actual_platform"),
            "status": dep.get("status"),
            "delay_minutes": dep.get("delay_minutes"),
            "is_cancelled": dep.get("is_cancelled", False),
            "stop_is_cancelled": dep.get("stop_is_cancelled", False),
            "stop_is_stopping": dep.get("stop_is_stopping", True),
            "latitude": dep.get("latitude"),
            "longitude": dep.get("longitude"),
            "update_time": dep.get("update_time"),
            "updated_at": self.coordinator.data.get("updated_at"),
        }


class GoTransitPlatformSensor(CoordinatorEntity[DepartureCoordinator], SensorEntity):
    """Boarding platform for the next departure.

    Reports the actual platform once GO posts it, falling back to the
    scheduled platform. `track_confirmed` is True when the actual platform
    is known — useful for a 'platform now posted' automation."""

    def __init__(self, coordinator: DepartureCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_PLATFORM}"
        self._attr_name = "Platform"
        self._attr_icon = "mdi:bus-stop"
        self._attr_device_info = _device(entry, coordinator.line_name)

    @property
    def native_value(self) -> str | None:
        dep = self.coordinator.data.get("next_departure") or {}
        return dep.get("actual_platform") or dep.get("scheduled_platform")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dep = self.coordinator.data.get("next_departure") or {}
        return {
            "scheduled_platform": dep.get("scheduled_platform"),
            "actual_platform": dep.get("actual_platform"),
            "track_confirmed": bool(dep.get("actual_platform")),
            "trip_number": dep.get("trip_number"),
            "updated_at": self.coordinator.data.get("updated_at"),
        }


class GoTransitStatusSensor(CoordinatorEntity[DepartureCoordinator], SensorEntity):
    """Human-readable status of the next departure.

    Derived from cancellation + delay rather than the API's cryptic status
    codes, which are kept as attributes."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["Cancelled", "Delayed", "On time", "Unknown"]

    def __init__(self, coordinator: DepartureCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_STATUS}"
        self._attr_name = "Status"
        self._attr_icon = "mdi:information-outline"
        self._attr_device_info = _device(entry, coordinator.line_name)

    @property
    def native_value(self) -> str:
        dep = self.coordinator.data.get("next_departure")
        if not dep:
            return "Unknown"
        if dep.get("is_cancelled") or dep.get("stop_is_cancelled"):
            return "Cancelled"
        delay = dep.get("delay_minutes") or 0
        if delay > 0:
            return "Delayed"
        return "On time"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dep = self.coordinator.data.get("next_departure") or {}
        return {
            "delay_minutes": dep.get("delay_minutes"),
            "departure_status": dep.get("departure_status"),
            "raw_status": dep.get("status"),
            "is_cancelled": dep.get("is_cancelled", False),
            "stop_is_cancelled": dep.get("stop_is_cancelled", False),
            "trip_number": dep.get("trip_number"),
            "updated_at": self.coordinator.data.get("updated_at"),
        }


class GoTransitDelaySensor(CoordinatorEntity[DepartureCoordinator], SensorEntity):
    def __init__(self, coordinator: DepartureCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_DELAY}"
        self._attr_name = "Delay"
        self._attr_icon = "mdi:clock-alert-outline"
        self._attr_native_unit_of_measurement = "min"
        self._attr_device_info = _device(entry, coordinator.line_name)

    @property
    def native_value(self) -> int:
        dep = self.coordinator.data.get("next_departure")
        if not dep:
            return 0
        return dep.get("delay_minutes") or 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dep = self.coordinator.data.get("next_departure") or {}
        return {
            "trip_number": dep.get("trip_number"),
            "departure_status": dep.get("departure_status"),
            "status": dep.get("status"),
            "is_cancelled": dep.get("is_cancelled", False),
        }


class GoTransitDeparturesSensor(CoordinatorEntity[DepartureCoordinator], SensorEntity):
    def __init__(self, coordinator: DepartureCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_DEPARTURES}"
        self._attr_name = "Upcoming Departures"
        self._attr_icon = "mdi:train-variant"
        self._attr_device_info = _device(entry, coordinator.line_name)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("departures", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "departures": self.coordinator.data.get("departures", []),
            "from": self.coordinator.data.get("from_stop"),
            "to": self.coordinator.data.get("to_stop"),
            "updated_at": self.coordinator.data.get("updated_at"),
        }


class GoTransitVehiclePositionSensor(CoordinatorEntity[VehicleCoordinator], SensorEntity):
    def __init__(self, coordinator: VehicleCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_VEHICLE_POSITION}"
        self._attr_name = "Active Trains"
        self._attr_icon = "mdi:train-car"
        self._attr_device_info = _device(entry, coordinator.line_name)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("vehicle_positions", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "trains": self.coordinator.data.get("vehicle_positions", []),
            "in_commute_window": self.coordinator.data.get("in_commute_window"),
            "poll_interval_seconds": int(self.coordinator.update_interval.total_seconds()),
            "updated_at": self.coordinator.data.get("updated_at"),
        }


class GoTransitAlertsSensor(CoordinatorEntity[AlertCoordinator], SensorEntity):
    def __init__(self, coordinator: AlertCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_ALERTS}"
        self._attr_name = "Service Alerts"
        self._attr_icon = "mdi:alert-circle-outline"
        self._attr_device_info = _device(entry, coordinator.line_name)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.get("alerts", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "alerts": self.coordinator.data.get("alerts", []),
            "updated_at": self.coordinator.data.get("updated_at"),
        }


class GoTransitConsistSensor(CoordinatorEntity[ConsistCoordinator], SensorEntity):
    def __init__(self, coordinator: ConsistCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_CONSIST}"
        self._attr_name = "Train Consist"
        self._attr_icon = "mdi:train-car-passenger"
        self._attr_native_unit_of_measurement = "coaches"
        self._attr_device_info = _device(entry, coordinator.line_name)

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get("coach_count")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "trip_number": data.get("trip_number"),
            "consist_number": data.get("consist_number"),
            "engine_number": data.get("engine_number"),
            "lineup": data.get("lineup", []),
            "updated_at": data.get("updated_at"),
        }


class GoTransitGuaranteeSensor(CoordinatorEntity[GuaranteeCoordinator], SensorEntity):
    """Whether GO's service guarantee applies to the next departure."""

    def __init__(self, coordinator: GuaranteeCoordinator, entry: ConfigEntry):
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{SENSOR_GUARANTEE}"
        self._attr_name = "Service Guarantee"
        self._attr_icon = "mdi:shield-check-outline"
        self._attr_device_info = _device(entry, coordinator.line_name)

    @property
    def native_value(self) -> str:
        """'Active' or 'Not active' — readable state for the UI."""
        return "Active" if self.coordinator.data.get("guarantee_active") else "Not active"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        return {
            "trip_number": data.get("trip_number"),
            "reason": data.get("reason"),
            "affected_stops": data.get("affected_stops", []),
            "updated_at": data.get("updated_at"),
        }
