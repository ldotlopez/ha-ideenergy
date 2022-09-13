# -*- coding: utf-8 -*-
#
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

import asyncio
import logging
import math
from datetime import timedelta

import ideenergy
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo

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

PLATFORMS: list[str] = ["sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = ideenergy.Client(
        session=async_get_clientsession(hass),
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        contract=entry.data[CONF_CONTRACT],
        user_session_timeout=API_USER_SESSION_TIMEOUT,
    )

    try:
        contract_details = await api.get_contract_details()
    except ideenergy.client.ClientError as e:
        _LOGGER.debug(f"Unable to initialize integration: {e}")

    device_identifiers = {
        ("cups", contract_details["cups"]),
    }

    device_info = DeviceInfo(
        identifiers=device_identifiers,
        name=f"CUPS {contract_details['cups']}",
        # name=sanitize_address(details["direccion"]),
        manufacturer=contract_details["listContador"][0]["tipMarca"],
    )

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
        # Use default update_interval and relay on barriers
        # update_interval=_calculate_datacoordinator_update_interval(),
        update_interval=timedelta(seconds=30),
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
            hass.async_add_job(
                hass.config_entries.async_forward_entry_setup(entry, platform)
            )

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


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    api = ideenergy.Client(
        session=async_get_clientsession(hass),
        username=config_entry.data[CONF_USERNAME],
        password=config_entry.data[CONF_PASSWORD],
        contract=config_entry.data[CONF_CONTRACT],
        user_session_timeout=API_USER_SESSION_TIMEOUT,
    )

    try:
        contract_details = await api.get_contract_details()
    except ideenergy.client.ClientError as e:
        _LOGGER.debug(f"Unable to initialize integration: {e}")

    device_identifiers = {
        ("cups", contract_details["cups"]),
    }

    device_info = DeviceInfo(
        identifiers=device_identifiers,
        name=f"CUPS {contract_details['cups']}",
        # name=sanitize_address(details["direccion"]),
        manufacturer=contract_details["listContador"][0]["tipMarca"],
    )

    update_integration(hass, config_entry, device_info)
    return True
