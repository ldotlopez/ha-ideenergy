# -*- coding: utf-8 -*-

# Copyright (C) 2021-2022 Luis López <luis@cuarentaydos.com>
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

import logging
from typing import Type

from homeassistant.components import recorder
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from homeassistant_historical_sensor.recorderutil import (
    delete_entity_invalid_states,
    hass_recorder_session,
)

SensorType = Type["IDeEntity"]


_LOGGER = logging.getLogger(__name__)


class IDeEntity(CoordinatorEntity):
    """The IDeSensor class provides:
    __init__
    __repr__
    name
    unique_id
    device_info
    entity_registry_enabled_default
    """

    I_DE_ENTITY_NAME = ""
    I_DE_DATA_SETS = []  # type: ignore[var-annotated]

    def __init__(self, *args, config_entry, device_info, **kwargs):
        super().__init__(*args, **kwargs)

        self._attr_has_entity_name = True
        self._attr_name = self.I_DE_ENTITY_NAME

        self._attr_unique_id = _build_entity_unique_id(
            device_info, self.I_DE_ENTITY_NAME
        )
        self._attr_entity_id = _build_entity_entity_id(
            self.I_DE_PLATFORM, device_info, self.I_DE_ENTITY_NAME
        )

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
        n_invalid_states = await self.async_delete_invalid_states()
        _LOGGER.debug(f"{self.entity_id}: cleaned {n_invalid_states} invalid states")

        await super().async_added_to_hass()

        self.coordinator.register_sensor(self)

        await self.coordinator.async_request_refresh()

    async def async_will_remove_from_hass(self) -> None:
        self.coordinator.unregister_sensor(self)
        await super().async_will_remove_from_hass()

    async def async_delete_invalid_states(self) -> int:
        if getattr(self, "hass", None) is None:
            raise TypeError(f"{self.entity_id} is not added to hass")

        def fn():
            with hass_recorder_session(self.hass) as session:
                return delete_entity_invalid_states(session, self)

        return await recorder.get_instance(self.hass).async_add_executor_job(fn)


def _build_entity_unique_id(device_info: DeviceInfo, entity_unique_name: str) -> str:
    cups = dict(device_info["identifiers"])["cups"]
    return slugify(f"{cups}-{entity_unique_name}", separator="-")


def _build_entity_entity_id(
    platform: str,
    device_info: DeviceInfo,
    entity_unique_name: str,
) -> str:
    partial_id = _build_entity_unique_id(device_info, entity_unique_name)

    return f"{platform}.{partial_id}".lower()
