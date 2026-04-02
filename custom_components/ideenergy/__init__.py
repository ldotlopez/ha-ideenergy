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


import asyncio
import logging
import math
import sys
from datetime import timedelta
from typing import Any

import ideenergy
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ATTRIBUTION,
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_PICTURE,
    ATTR_FRIENDLY_NAME,
    ATTR_ICON,
    ATTR_SUPPORTED_FEATURES,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_PASSWORD,
    CONF_USERNAME,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo, Entity

from .barrier import TimeDeltaBarrier, TimeWindowBarrier  # NoopBarrier,
from .const import (
    API_USER_SESSION_TIMEOUT,
    CONF_CONTRACT,
    DOMAIN,
    MAX_RETRIES,
    MEASURE_MAX_AGE,
    MIN_SCAN_INTERVAL,
    UPDATE_WINDOW_END_MINUTE,
    UPDATE_WINDOW_START_MINUTE,
)
from .datacoordinator import DataSetType, IDeCoordinator
from .updates import update_integration

# --- Monkey-patch homeassistant_historical_sensor for modern HA compatibility ---
# The installed version uses _friendly_name_internal() and device_state_attributes
# which have been removed in recent HA versions.

_FLOAT_PRECISION = abs(int(math.floor(math.log10(abs(sys.float_info.epsilon))))) - 1


def _patched_stringify_state(self: Entity, state: Any) -> str:
    if not self.available:
        return STATE_UNAVAILABLE
    if state is None:
        return STATE_UNKNOWN
    if isinstance(state, float):
        return f"{state:.{_FLOAT_PRECISION}}"
    return str(state)


def _patched_build_attributes(self: Entity, state: Any) -> dict[str, str]:
    attr = self.capability_attributes
    attr = dict(attr) if attr else {}

    state = _patched_stringify_state(self, state)
    if self.available:
        attr.update(self.state_attributes or {})
        attr.update(self.extra_state_attributes or {})

    unit_of_measurement = self.unit_of_measurement
    if unit_of_measurement is not None:
        attr[ATTR_UNIT_OF_MEASUREMENT] = unit_of_measurement

    entry = self.registry_entry
    if (name := (entry and entry.name) or self.name) is not None:
        attr[ATTR_FRIENDLY_NAME] = name

    if (icon := (entry and entry.icon) or self.icon) is not None:
        attr[ATTR_ICON] = icon

    if (entity_picture := self.entity_picture) is not None:
        attr[ATTR_ENTITY_PICTURE] = entity_picture

    if assumed_state := self.assumed_state:
        attr[ATTR_ASSUMED_STATE] = assumed_state

    if (supported_features := self.supported_features) is not None:
        attr[ATTR_SUPPORTED_FEATURES] = supported_features

    if (device_class := self.device_class) is not None:
        attr[ATTR_DEVICE_CLASS] = str(device_class)

    if (attribution := self.attribution) is not None:
        attr[ATTR_ATTRIBUTION] = attribution

    return attr


try:
    import homeassistant_historical_sensor.patches as _hhs_patches
    import homeassistant_historical_sensor.sensor as _hhs_sensor

    _hhs_patches._build_attributes = _patched_build_attributes
    _hhs_patches._stringify_state = _patched_stringify_state
    # Also patch the already-imported reference in sensor.py
    _hhs_sensor._build_attributes = _patched_build_attributes
except Exception:
    pass

PLATFORMS: list[str] = [Platform.SENSOR, Platform.BUTTON]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = IDeEnergyAPI(hass, entry)

    try:
        contract_details = await api.get_contract_details()
    except ideenergy.client.ClientError as e:
        try:
            err_msg = f"{e.response.status} - {e.response.reason}" if hasattr(e, "response") else repr(e)
        except Exception:
            err_msg = repr(e)
        _LOGGER.warning(f"Unable to initialize integration: {err_msg}")
        raise ConfigEntryNotReady(f"i-DE API unavailable: {err_msg}") from e
    except Exception as e:
        _LOGGER.warning(f"Unexpected error initializing integration: {e!r}")
        raise ConfigEntryNotReady(f"Unexpected error: {e!r}") from e

    device_info = IDeEnergyDeviceInfo(contract_details)

    coordinator = IDeCoordinator(
        hass=hass,
        api=api,
        barriers={
            DataSetType.MEASURE: TimeWindowBarrier(
                allowed_window_minutes=(
                    UPDATE_WINDOW_START_MINUTE,
                    UPDATE_WINDOW_END_MINUTE,
                ),
                max_retries=MAX_RETRIES,
                max_age=timedelta(seconds=MEASURE_MAX_AGE),
            ),
            DataSetType.HISTORICAL_CONSUMPTION: TimeDeltaBarrier(
                delta=timedelta(hours=6)
            ),
            DataSetType.HISTORICAL_GENERATION: TimeDeltaBarrier(
                delta=timedelta(hours=6)
            ),
            DataSetType.HISTORICAL_POWER_DEMAND: TimeDeltaBarrier(
                delta=timedelta(hours=36)
            ),
        },
        # Use default update_interval and relay on barriers for now
        # MEASURE barrier should deny if last attempt (success or not) is too recent to
        # prevent api smashing or subsequent baning
        update_interval=_calculate_datacoordinator_update_interval(),
        # update_interval=timedelta(seconds=30),
    )

    # Don't refresh coordinator yet since there isn't any sensor registered
    # await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN] = hass.data.get(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = (coordinator, device_info)

    for platform in PLATFORMS:
        if entry.options.get(platform, True):
            coordinator.platforms.append(platform)
    await hass.config_entries.async_forward_entry_setups(entry,coordinator.platforms)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator, _ = hass.data[DOMAIN][entry.entry_id]
    unloaded = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
                if platform in coordinator.platforms
            ]
        )
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


def _calculate_datacoordinator_update_interval() -> timedelta:
    #
    # Calculate SCAN_INTERVAL to allow two updates within the update window
    #
    update_window_width = (
        UPDATE_WINDOW_END_MINUTE * 60 - UPDATE_WINDOW_START_MINUTE * 60
    )
    update_interval = math.floor(update_window_width / 2)
    update_interval = max([MIN_SCAN_INTERVAL, update_interval])

    return timedelta(seconds=update_interval)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry):
    api = IDeEnergyAPI(hass, entry)

    try:
        contract_details = await api.get_contract_details()
    except ideenergy.client.ClientError as e:
        try:
            err_msg = f"{e.response.status} - {e.response.reason}" if hasattr(e, "response") else repr(e)
        except Exception:
            err_msg = repr(e)
        _LOGGER.warning(f"Unable to migrate integration: {err_msg}")
        return False

    update_integration(hass, entry, IDeEnergyDeviceInfo(contract_details))
    return True


def IDeEnergyDeviceInfo(contract_details):
    return DeviceInfo(
        identifiers={
            ("cups", contract_details["cups"]),
        },
        name=contract_details["cups"],
        manufacturer=contract_details["listContador"][0]["tipMarca"],
    )


def IDeEnergyAPI(hass: HomeAssistant, entry: ConfigEntry):
    return ideenergy.Client(
        session=async_get_clientsession(hass),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        contract=entry.data[CONF_CONTRACT],
        user_session_timeout=API_USER_SESSION_TIMEOUT,
    )
