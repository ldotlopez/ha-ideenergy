# -*- coding: utf-8 -*-

# Copyright (C) 2021 Luis López <luis@cuarentaydos.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

# TODO
# Maybe we need to mark some function as callback but I'm not sure whose.
# from homeassistant.core import callback

from homeassistant.components.sensor import STATE_CLASS_MEASUREMENT
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from typing import Type

SensorType = Type["IDeEntity"]


class IDeEntity(CoordinatorEntity):
    """The IDeSensor class provides:
    __init__
    __repr__
    name
    unique_id
    device_info
    entity_registry_enabled_default
    """

    I_DE_DATA_SETS = []  # type: ignore[var-annotated]

    def __init__(self, *args, config_entry, device_info, **kwargs):
        super().__init__(*args, **kwargs)

        self._attr_unique_id = _build_entity_unique_id(
            config_entry, device_info, self.__class__
        )
        self.entity_id = _build_entity_entity_id(
            config_entry, device_info, self.I_DE_PLATFORM, self.__class__
        )

        self._attr_name = _build_entity_name(config_entry, device_info, self.__class__)

        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_device_info = device_info
        self._attr_entity_registry_enabled_default = True
        self._attr_entity_registry_visible_default = True

    def __repr__(self):
        clsname = self.__class__.__name__
        if hasattr(self, "coordinator"):
            api = self.coordinator.api.username
        else:
            api = self.api

        return f"<{clsname} {api.username}/{api._contract}>"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.coordinator.register_sensor(self)

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.unregister_sensor(self)
        await super().async_will_remove_from_hass()

    # async def async_added_to_hass(self) -> None:
    #     # Try to load previous state using RestoreEntity
    #     #
    #     # self.async_get_last_state().last_update is tricky and can't be trusted in our
    #     # scenario. last_updated can be the last time HA exited because state is saved
    #     # at exit with last_updated=exit_time, not last_updated=sensor_last_update
    #     #
    #     # It's easier to just load the value and schedule an update with
    #     # schedule_update_ha_state() (which is meant for push sensors but...)

    #     await super().async_added_to_hass()

    #     state = await self.async_get_last_state()

    #     if (
    #         not state
    #         or state.state is None
    #         or state.state == STATE_UNKNOWN
    #         or state.state == STATE_UNAVAILABLE
    #     ):
    #         self._logger.debug("restore state: No previous state")

    #     else:
    #         try:
    #             self._state = float(state.state)
    #             self._logger.debug(
    #                 f"restore state: Got {self._state} {ENERGY_KILO_WATT_HOUR}"
    #             )

    #         except ValueError:
    #             self._logger.debug(
    #                 f"restore state: Discard invalid previous state {state!r}"
    #             )

    #     if self._state is None:
    #         self._logger.debug(
    #             "restore state: No previous state: scheduling force update"
    #         )
    #         self._barrier.force_next()
    #         self.schedule_update_ha_state(force_refresh=True)


def _build_entity_unique_id(
    config_entry: ConfigEntry, device_info: DeviceInfo, SensorClass: SensorType
) -> str:
    cups = dict(device_info["identifiers"])["cups"]
    return f"{config_entry.entry_id}-{cups}-{SensorClass.I_DE_SENSOR_TYPE}".lower()


def _build_entity_entity_id(
    config_entry: ConfigEntry,
    device_info: DeviceInfo,
    platform: str,
    SensorClass: SensorType,
) -> str:
    cups = dict(device_info["identifiers"])["cups"]
    base_id = slugify(f"{DOMAIN}_{cups}_{SensorClass.I_DE_SENSOR_TYPE}")

    return f"{platform}.{base_id}".lower()


def _build_entity_name(
    config_entry: ConfigEntry,
    device_info: DeviceInfo,
    SensorClass: SensorType,
) -> str:
    return " ".join(x.capitalize() for x in SensorClass.I_DE_SENSOR_TYPE.split("-"))
