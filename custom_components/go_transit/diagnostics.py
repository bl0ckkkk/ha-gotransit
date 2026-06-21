"""Diagnostics support for GO Transit."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_API_KEY, DOMAIN
from .coordinator import (
    AlertCoordinator,
    ConsistCoordinator,
    DepartureCoordinator,
    GuaranteeCoordinator,
    VehicleCoordinator,
)

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coords: dict = hass.data[DOMAIN][entry.entry_id]
    dep: DepartureCoordinator = coords["departures"]
    veh: VehicleCoordinator = coords["vehicles"]
    ale: AlertCoordinator = coords["alerts"]
    con: ConsistCoordinator = coords["consist"]
    gua: GuaranteeCoordinator = coords["guarantee"]

    def _coord_info(coord, extra: dict | None = None) -> dict:
        info = {
            "last_update_success": coord.last_update_success,
            "last_exception": str(coord.last_exception) if coord.last_exception else None,
            "update_interval_seconds": int(coord.update_interval.total_seconds()),
            "consecutive_failures": getattr(coord, "_consecutive_failures", 0),
            "pause_outside_service": getattr(coord, "pause_outside_service", False),
            "service_window": f"{getattr(coord, 'service_start', '?')}–{getattr(coord, 'service_end', '?')}",
            "processed_data": coord.data,
            "raw_api_responses": coord.last_raw,
        }
        if extra:
            info.update(extra)
        return info

    return {
        "config": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "coordinators": {
            "departures": _coord_info(dep),
            "vehicles": _coord_info(veh, {
                "in_commute_window": veh.data.get("in_commute_window") if veh.data else None,
            }),
            "alerts": _coord_info(ale),
            "consist": _coord_info(con, {
                "trip_number_used": con.data.get("trip_number") if con.data else None,
            }),
            "guarantee": _coord_info(gua, {
                "trip_number_used": gua.data.get("trip_number") if gua.data else None,
                "guarantee_active": gua.data.get("guarantee_active") if gua.data else None,
            }),
        },
    }
