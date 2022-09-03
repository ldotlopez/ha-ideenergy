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

import logging
import math
from datetime import timedelta

import ideenergy
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo

from .updates import update_integration
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
from .datacoordinator import DataSetType, IdeCoordinator

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

    update_integration(hass, entry, device_info)

    coordinator = IdeCoordinator(
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
        update_interval=_calculate_datacoordinator_update_interval(),
    )

    hass.data[DOMAIN] = hass.data.get(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = (coordinator, device_info)

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


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
