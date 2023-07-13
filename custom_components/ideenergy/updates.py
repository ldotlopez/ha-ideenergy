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


import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

from custom_components.ideenergy.const import DOMAIN

from .entity import IDeEntity
from .entity import _build_entity_unique_id as _build_entity_unique_id_v3
from .sensor import AccumulatedConsumption, HistoricalConsumption

_LOGGER = logging.getLogger(__name__)

SensorType = type[IDeEntity]


def update_integration(
    hass: HomeAssistant, config_entry: ConfigEntry, device_info: DeviceInfo
) -> None:
    if config_entry.version < 2:
        _update_entity_registry_v1(hass, config_entry, device_info)
        _update_device_registry_v1(hass, config_entry, device_info)
        _update_config_entry_v1(hass, config_entry)

        _LOGGER.debug("Update to version 2 completed")

    if config_entry.version < 3:
        _update_config_v2(hass, config_entry, device_info)

        _LOGGER.debug("Update to version 3 completed")


def _update_config_v2(
    hass: HomeAssistant, config_entry: ConfigEntry, device_info: DeviceInfo
) -> None:
    dr = device_registry.async_get(hass)
    er = entity_registry.async_get(hass)

    device = dr.async_get_device(device_info["identifiers"])
    entities = {id: e for id, e in er.entities.items() if e.device_id == device.id}

    for _, entity in entities.items():
        old_unique_id = entity.unique_id
        new_unique_id = _build_entity_unique_id_v3(
            device_info, entity.name or entity.original_name
        )

        er.async_update_entity(
            entity.entity_id,
            new_unique_id=new_unique_id,
        )
        _LOGGER.debug(f"Updated entity '{entity.entity_id}'")
        _LOGGER.debug(f"  [-] unique_id '{old_unique_id}'")
        _LOGGER.debug(f"  [+] unique_id '{new_unique_id}'")

    config_entry.version = 3

    hass.config_entries.async_update_entry(config_entry)
    _LOGGER.debug(f"ConfigEntry updated to version '{config_entry.version}'")


def _build_entity_unique_id_v2(
    config_entry: ConfigEntry,
    device_info: DeviceInfo,
    SensorClass: SensorType,
) -> str:
    cups = dict(device_info["identifiers"])["cups"]

    return slugify(SensorClass.I_DE_ENTITY_NAME).replace("_", "-")


def _build_entity_entity_id_v2(
    config_entry: ConfigEntry,
    device_info: DeviceInfo,
    SensorClass: SensorType,
) -> str:
    cups = dict(device_info["identifiers"])["cups"]
    base_id = slugify(f"{DOMAIN}" + f"_{cups}" + f"_{SensorClass.I_DE_ENTITY_NAME}")

    return f"{SensorClass.I_DE_PLATFORM}.{base_id}".lower()


#
# Don't modify anything below this line unless it's critical
#


def _update_config_entry_v1(hass: HomeAssistant, config_entry: ConfigEntry):
    new_data = dict(config_entry.data)
    new_data.pop("name")

    config_entry.version = 2

    hass.config_entries.async_update_entry(config_entry, data=new_data)
    _LOGGER.debug(f"ConfigEntry updated to version '{config_entry.version}'")


def _update_device_registry_v1(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_info: DeviceInfo,
):
    dr = device_registry.async_get(hass)
    for dev in dr.devices.values():
        if config_entry.entry_id not in dev.config_entries:
            continue

        if dev.identifiers == device_info["identifiers"]:
            continue

        old_ids = dev.identifiers
        new_ids = device_info["identifiers"]

        dr.async_update_device(dev.id, new_identifiers=new_ids)
        _LOGGER.debug(f"DeviceEntry '{dev.id}' updated ({old_ids} → {new_ids})")

        _LOGGER.debug(f"Updated device '{dev.id}'")
        _LOGGER.debug(f"  [-] identifiers '{old_ids}'")
        _LOGGER.debug(f"  [+] identifiers '{new_ids}'")


def _update_entity_registry_v1(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_info: DeviceInfo,
):
    er = entity_registry.async_get(hass)
    migrate = (
        ("accumulated", AccumulatedConsumption),
        ("historical", HistoricalConsumption),
    )

    for old_sensor_type, new_sensor_cls in migrate:
        entity_id = er.async_get_entity_id(
            "sensor",
            "ideenergy",
            _build_entity_unique_id_v1(config_entry, old_sensor_type),
        )
        if not entity_id:
            continue

        entity = er.async_get(entity_id)
        if not entity:
            continue

        old_unique_id = entity.unique_id
        new_unique_id = _build_entity_unique_id_v2(
            config_entry, device_info, new_sensor_cls
        )

        new_entity_id = _build_entity_entity_id_v2(
            config_entry, device_info, new_sensor_cls
        )

        old_name = getattr(entity, "name")
        new_name = new_sensor_cls.I_DE_ENTITY_NAME

        er.async_update_entity(
            entity.entity_id,
            new_unique_id=new_unique_id,
            # new_entity_id=new_entity_id,
            original_name=new_name,
        )

        _LOGGER.debug(f"Updated entity '{entity_id}'")
        _LOGGER.debug(f"  [-] unique_id '{old_unique_id}'")
        _LOGGER.debug(f"  [-] name      '{old_name}'")
        _LOGGER.debug(f"  [+] unique_id '{new_unique_id}'")
        _LOGGER.debug(f"  [+] name      '{new_name}'")


def _build_entity_unique_id_v1(config_entry: ConfigEntry, sensor_type: str):
    # "unique_id": "dc5088dfcf71e4a1096539c61d057299-accumulated",
    return f"{config_entry.entry_id}-{sensor_type}"
