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


import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.entity import DeviceInfo

from .entity import _build_entity_entity_id, _build_entity_unique_id
from .sensor import AccumulatedConsumption, HistoricalConsumption
from homeassistant.components import recorder

_LOGGER = logging.getLogger(__name__)


def update_integration(
    hass: HomeAssistant, config_entry: ConfigEntry, device_info: DeviceInfo
) -> None:
    if config_entry.version < 2:
        _update_config_entry_v1(hass, config_entry)
        _update_device_registry_v1(hass, config_entry, device_info)
        _update_entity_registry_v1(hass, config_entry, device_info)

        v2_data = dict(config_entry.data)
        name = v2_data.pop("name")

        config_entry.version = 2
        config_entry.title = name.lstrip("ICP_")

        hass.config_entries.async_update_entry(config_entry, data=v2_data)

        _LOGGER.debug(
            f"Updated ConfigEntry to '{config_entry.version}'"
            f" with {config_entry.data!r}"
        )


def _update_config_entry_v1(hass: HomeAssistant, config_entry: ConfigEntry):
    if "name" in config_entry.data:

        _LOGGER.debug(f"Updated ConfigEntry '{config_entry.entry_id}'")


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
        _LOGGER.debug(f"Updated DeviceEntry '{dev.id}' ({old_ids} → {new_ids})")


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

    for (old_sensor_type, new_sensor_cls) in migrate:
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
        new_unique_id = _build_entity_unique_id(
            config_entry, device_info, new_sensor_cls
        )

        # new_entity_id = _build_entity_entity_id(
        #     config_entry, device_info, new_sensor_cls
        # )

        new_name = new_sensor_cls.I_DE_ENTITY_NAME

        er.async_update_entity(
            entity.entity_id,
            new_unique_id=new_unique_id,
            # new_entity_id=new_entity_id,
            original_name=new_name,
        )
        _LOGGER.debug(
            f"Updated Entity '{entity_id}' ({old_unique_id}' → '{new_unique_id}')"
        )


def _update_database_v1(hass, old_entity_id, new_entity_id):
    with recorder.util.session_scope(
        session=recorder.get_instance(hass).get_session()
    ) as session:
        session.query(recorder.db_schema.States).filter(
            recorder.db_schema.States.entity_id == old_entity_id
        ).update({recorder.db_schema.States.entity_id: new_entity_id})

        session.query(recorder.db_schema.StatisticMetaData).filter(
            recorder.db_schema.StatisticMetaData.statistic_id == old_entity_id
        ).update({recorder.db_schema.StatisticMetaData.statistic_id: new_entity_id})

        session.commit()


def _build_entity_unique_id_v1(config_entry: ConfigEntry, sensor_type: str):
    # "unique_id": "dc5088dfcf71e4a1096539c61d057299-accumulated",
    return f"{config_entry.entry_id}-{sensor_type}"
