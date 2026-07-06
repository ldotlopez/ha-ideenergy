from __future__ import annotations

from logging import getLogger

import ideenergy
from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import IDeEnergyDataCoordinator
from .data import IntegrationIDeEnergyConfigEntry, build_entity_unique_id

PLATFORM = "button"
PARALLEL_UPDATES = 1

LOGGER = getLogger(__name__)


class ICPReconnectButton(CoordinatorEntity, ButtonEntity):
    """Button to request ICP reconnection."""

    I_DE_ENTITY_NAME = "Reconnect ICP"
    _attr_translation_key = "reconnect_icp"

    coordinator: IDeEnergyDataCoordinator

    def __init__(
        self,
        *,
        coordinator: IDeEnergyDataCoordinator,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)

        self._attr_has_entity_name = True
        self._attr_unique_id = build_entity_unique_id(
            device_info, self.I_DE_ENTITY_NAME
        )
        self._attr_device_info = device_info

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.coordinator.async_reconnect_icp()
        except ideenergy.ClientError as exc:
            raise HomeAssistantError(f"Unable to reconnect ICP: {exc}") from exc

        LOGGER.info("%s requested ICP reconnection", self.entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntegrationIDeEnergyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            ICPReconnectButton(
                coordinator=entry.runtime_data.coordinator,
                device_info=entry.runtime_data.device_info,
            )
        ]
    )
