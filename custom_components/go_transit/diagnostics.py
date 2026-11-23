"""Privacy-preserving diagnostics for GO Transit."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Export polling health without route settings, responses, or error text."""
    coordinators = hass.data[DOMAIN][entry.entry_id]
    report = {}
    for name in ("departures", "vehicles", "alerts", "consist", "guarantee"):
        coord = coordinators[name]
        report[name] = {
            "last_update_success": coord.last_update_success,
            "last_successful_request": coord.last_successful_request,
            "last_error_type": type(coord.last_exception).__name__ if coord.last_exception else None,
            "update_interval_seconds": int(coord.update_interval.total_seconds()),
            "consecutive_failures": coord._consecutive_failures,
        }
    return {"coordinators": report}
