import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, dt_util
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import DOMAIN
from .datacoordinator import DataSetType
from .entity import IDeEntity

PLATFORM = "button"
_LOGGER = logging.getLogger(__name__)


class ForceUpdateButton(IDeEntity, ButtonEntity):
    I_DE_PLATFORM = PLATFORM
    I_DE_ENTITY_NAME = "Force Data Update"
    I_DE_DATA_SETS = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_icon = "mdi:refresh"

    async def async_added_to_hass(self) -> None:
        # Skip IDeEntity's async_delete_invalid_states (not applicable to buttons)
        # but still register with the coordinator
        await super(IDeEntity, self).async_added_to_hass()
        self.coordinator.register_sensor(self)

    async def async_press(self) -> None:
        _LOGGER.debug("Force data update requested")

        for ds_type, barrier in self.coordinator.barriers.items():
            # Reset TimeDeltaBarrier by setting last_success to epoch 0
            if hasattr(barrier, "_last_success"):
                barrier._last_success = dt_util.utc_from_timestamp(0)

            # Force TimeWindowBarrier to allow next update
            if hasattr(barrier, "force_next"):
                barrier.force_next()

            _LOGGER.debug(f"Barrier for {ds_type.name} reset")

        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
):
    coordinator, device_info = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        [
            ForceUpdateButton(
                config_entry=config_entry,
                device_info=device_info,
                coordinator=coordinator,
            )
        ]
    )
