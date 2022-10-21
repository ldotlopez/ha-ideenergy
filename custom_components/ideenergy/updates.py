import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.entity import DeviceInfo

from .entity import _build_entity_entity_id, _build_entity_name, _build_entity_unique_id
from .sensor import Accumulated, HistoricalConsumption

_LOGGER = logging.getLogger(__name__)


def update_integration(
    hass: HomeAssistant, config_entry: ConfigEntry, device_info: DeviceInfo
) -> None:
    if config_entry.version < 2:
        _update_config_entry_v1(hass, config_entry)
        _update_device_registry_v1(hass, config_entry, device_info)
        _update_entity_registry_v1(hass, config_entry, device_info)


def _update_config_entry_v1(hass: HomeAssistant, config_entry: ConfigEntry):
    if "name" in config_entry.data:
        data = dict(config_entry.data)
        data["name"]
        hass.config_entries.async_update_entry(config_entry, data=data)
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
    migrate = (("accumulated", Accumulated), ("historical", HistoricalConsumption))

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
        new_entity_id = _build_entity_entity_id(
            config_entry, device_info, new_sensor_cls
        )
        new_name = _build_entity_name(config_entry, device_info, new_sensor_cls)

        er.async_update_entity(
            entity.entity_id,
            new_unique_id=new_unique_id,
            new_entity_id=new_entity_id,
            original_name=new_name,
        )
        _LOGGER.debug(
            f"Updated Entity '{entity_id}' ({old_unique_id}' → '{new_unique_id}')"
        )


def _build_entity_unique_id_v1(config_entry: ConfigEntry, sensor_type: str):
    # "unique_id": "dc5088dfcf71e4a1096539c61d057299-accumulated",
    return f"{config_entry.entry_id}-{sensor_type}"
