"""Choose a train to follow independently of the next departure."""
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .pinning import UNPINNED


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([GoTransitPinnedTrainSelect(hass.data[DOMAIN][entry.entry_id]["pinned"], entry)])


class GoTransitPinnedTrainSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Pinned Train"
    _attr_icon = "mdi:pin"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_pinned_train"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def options(self):
        return [UNPINNED, *self.coordinator.choices]

    @property
    def current_option(self):
        pin = self.coordinator.pin
        return pin["label"] if pin else UNPINNED

    @property
    def extra_state_attributes(self):
        return dict(self.coordinator.pin or {})

    async def async_select_option(self, option):
        await self.coordinator.async_select(option)
