"""Device tracker platform for GO Transit — live train position on the map.

Tracks the pinned train, or the next departure when unpinned, so it
appears on Home Assistant's native map. Position comes from the vehicle feed."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, TRACKER_TRAIN
from .coordinator import DepartureCoordinator, VehicleCoordinator
from .pinning import match_train

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coords = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        GoTransitTrainTracker(coords["vehicles"], coords["departures"], entry, coords["pinned"])
    ])


class GoTransitTrainTracker(CoordinatorEntity[VehicleCoordinator], TrackerEntity):
    """Map marker for the pinned train or next departure.

    Listens to the vehicle coordinator for position, and the departure
    coordinator for which trip number to follow."""

    def __init__(
        self,
        vehicle_coordinator: VehicleCoordinator,
        departure_coordinator: DepartureCoordinator,
        entry: ConfigEntry,
        pinned_coordinator,
    ):
        super().__init__(vehicle_coordinator)
        self._dep = departure_coordinator
        self._entry = entry
        self._pinned = pinned_coordinator
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{entry.entry_id}_{TRACKER_TRAIN}"
        self._attr_name = "Train"
        self._attr_icon = "mdi:train"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Metrolinx",
            model=vehicle_coordinator.line_name or "GO Transit",
        )

    def _matched_train(self) -> dict | None:
        """Match the selected trip without falling back while pinned."""
        pin = self._pinned.pin
        trip_number = (pin or (self._dep.data or {}).get("next_departure") or {}).get("trip_number")
        return match_train((self.coordinator.data or {}).get("vehicle_positions", []), trip_number)

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        train = self._matched_train()
        if train and train.get("latitude") is not None:
            try:
                return float(train["latitude"])
            except (ValueError, TypeError):
                return None
        return None

    @property
    def longitude(self) -> float | None:
        train = self._matched_train()
        if train and train.get("longitude") is not None:
            try:
                return float(train["longitude"])
            except (ValueError, TypeError):
                return None
        return None

    @property
    def available(self) -> bool:
        """Only available when we have a matched train with coordinates."""
        return bool(self.coordinator.last_update_success and self.latitude is not None
                    and self.longitude is not None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        train = self._matched_train() or {}
        return {
            "trip_number": (self._pinned.pin or train).get("trip_number"),
            "pinned": self._pinned.pin is not None,
            "direction": train.get("direction"),
            "next_stop": train.get("next_stop"),
            "status": train.get("status"),
            "delay_minutes": train.get("delay_minutes"),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Refresh when either coordinator updates."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Subscribe to the departure coordinator too, not just vehicles."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._dep.async_add_listener(self._handle_coordinator_update)
        )
        self.async_on_remove(
            self._pinned.async_add_listener(self._handle_coordinator_update)
        )
