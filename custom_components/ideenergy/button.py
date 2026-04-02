import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, dt_util
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.util import slugify

from .const import DOMAIN

PLATFORM = "button"
_LOGGER = logging.getLogger(__name__)


class ForceUpdateButton(ButtonEntity):
    _attr_icon = "mdi:refresh"
    _attr_has_entity_name = True
    _attr_name = "Force Data Update"

    def __init__(self, coordinator, device_info: DeviceInfo):
        self._coordinator = coordinator
        self._attr_device_info = device_info

        cups = dict(device_info["identifiers"])["cups"]
        self._attr_unique_id = slugify(
            f"{cups}-force-data-update", separator="-"
        )

    async def async_press(self) -> None:
        _LOGGER.warning("Force data update requested, resetting all barriers")

        for ds_type, barrier in self._coordinator.barriers.items():
            if hasattr(barrier, "_last_success"):
                barrier._last_success = dt_util.utc_from_timestamp(0)
            if hasattr(barrier, "force_next"):
                barrier.force_next()

        await self._coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
):
    coordinator, device_info = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([ForceUpdateButton(coordinator, device_info)])
