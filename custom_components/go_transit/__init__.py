"""GO Transit integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry

from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_KEY,
    CONF_COMMUTE_END,
    CONF_COMMUTE_START,
    CONF_SERVICE_END,
    CONF_SERVICE_START,
    DEFAULT_SERVICE_END,
    DEFAULT_SERVICE_START,
    PLATFORMS,
    CONF_FROM_STOP,
    CONF_FROM_STOP_CODE,
    CONF_LINE_CODE,
    CONF_LINE_NAME,
    CONF_MAX_DEPARTURES,
    CONF_TO_STOP,
    CONF_TO_STOP_CODE,
    DEFAULT_COMMUTE_END,
    DEFAULT_COMMUTE_START,
    DOMAIN,
)
from .coordinator import (
    AlertCoordinator,
    ConsistCoordinator,
    DepartureCoordinator,
    GuaranteeCoordinator,
    VehicleCoordinator,
)

_LOGGER = logging.getLogger(__name__)


def _build_coordinators(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    kwargs = dict(
        hass=hass,
        api_key=entry.data[CONF_API_KEY],
        from_stop_code=entry.data[CONF_FROM_STOP_CODE],
        from_stop_name=entry.data[CONF_FROM_STOP],
        to_stop_code=entry.data[CONF_TO_STOP_CODE],
        to_stop_name=entry.data[CONF_TO_STOP],
        line_code=entry.data.get(CONF_LINE_CODE, ""),
        line_name=entry.data.get(CONF_LINE_NAME, ""),
        max_departures=entry.data.get(CONF_MAX_DEPARTURES, 5),
        commute_start=entry.options.get(
            CONF_COMMUTE_START,
            entry.data.get(CONF_COMMUTE_START, DEFAULT_COMMUTE_START),
        ),
        commute_end=entry.options.get(
            CONF_COMMUTE_END,
            entry.data.get(CONF_COMMUTE_END, DEFAULT_COMMUTE_END),
        ),
    )
    svc_start = entry.options.get(
        CONF_SERVICE_START, entry.data.get(CONF_SERVICE_START, DEFAULT_SERVICE_START)
    )
    svc_end = entry.options.get(
        CONF_SERVICE_END, entry.data.get(CONF_SERVICE_END, DEFAULT_SERVICE_END)
    )
    dep = DepartureCoordinator(**kwargs)
    coords = {
        "departures": dep,
        "vehicles": VehicleCoordinator(**kwargs),
        "alerts": AlertCoordinator(**kwargs),
        "consist": ConsistCoordinator(**kwargs, departure_coordinator=dep),
        "guarantee": GuaranteeCoordinator(**kwargs, departure_coordinator=dep),
    }
    for coord in coords.values():
        coord.service_start = svc_start
        coord.service_end = svc_end
    return coords


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change (e.g. commute window)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinators = _build_coordinators(hass, entry)

    # Departures must refresh first — consist + guarantee read its trip number.
    await coordinators["departures"].async_config_entry_first_refresh()
    await coordinators["vehicles"].async_refresh()
    await coordinators["alerts"].async_refresh()
    await coordinators["consist"].async_refresh()
    await coordinators["guarantee"].async_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when options change so the new commute window takes effect.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
