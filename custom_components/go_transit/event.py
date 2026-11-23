"""Home Assistant automation events for the pinned commute."""
from homeassistant.components.event import EventEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo

from .commute import EVENT_TYPES
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    pinned = hass.data[DOMAIN][entry.entry_id]["pinned"]
    async_add_entities([GoTransitCommuteEvent(pinned, entry)])


class GoTransitCommuteEvent(EventEntity):
    """Report changes to the selected trip and when the destination is next."""

    _attr_has_entity_name = True
    _attr_name = "Commute Alerts"
    _attr_event_types = EVENT_TYPES
    _attr_icon = "mdi:train"

    def __init__(self, pinned, entry):
        self._pinned = pinned
        self._attr_unique_id = f"{entry.entry_id}_commute_alerts"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Metrolinx",
            model=pinned.departures.line_name or "GO Transit",
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self._pinned.async_listen_for_alerts(self._handle_alert))

    @callback
    def _handle_alert(self, event_type, attributes):
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
