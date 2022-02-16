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

import math
from datetime import datetime, timedelta
from typing import Optional

import ideenergy
from homeassistant.components.sensor import (
    ATTR_LAST_RESET,
    ATTR_STATE_CLASS,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, DEVICE_CLASS_ENERGY, ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.util import dt as dt_util

from . import _LOGGER
from .const import (
    DELAY_MAX_SECONDS,
    DELAY_MIN_SECONDS,
    DOMAIN,
    HISTORICAL_MAX_AGE,
    MEASURE_MAX_AGE,
    MIN_SCAN_INTERVAL,
    UPDATE_WINDOW_START_MINUTE,
    UPDATE_WINDOW_END_MINUTE,
    MAX_RETRIES,
)
from .historical_state import HistoricalEntity
from .barrier import Barrier

# Adjust SCAN_INTERVAL to allow two updates within the update window
update_window_width = UPDATE_WINDOW_END_MINUTE * 60 - UPDATE_WINDOW_START_MINUTE * 60
scan_interval = math.floor(update_window_width / 2) - (DELAY_MAX_SECONDS * 2)
scan_interval = max([MIN_SCAN_INTERVAL, scan_interval])
SCAN_INTERVAL = timedelta(seconds=scan_interval)

_LOGGER.debug(f"update_window_width: {update_window_width} seconds")
_LOGGER.debug(f"scan_interval: {SCAN_INTERVAL.total_seconds()} seconds")


class Accumulated(RestoreEntity, SensorEntity):
    def __init__(self, unique_id, device_info, name, api, contract, logger=_LOGGER):
        self._logger = logger
        self._name = name
        self._unique_id = unique_id

        self._device_info = device_info
        self._api = api
        self._contact = contract

        self._state = None
        self.barrier = Barrier(
            update_window_start_minute=UPDATE_WINDOW_START_MINUTE,
            update_window_end_minute=UPDATE_WINDOW_END_MINUTE,
            max_retries=MAX_RETRIES,
            max_age=MEASURE_MAX_AGE,
            delay_min_seconds=DELAY_MIN_SECONDS,
            delay_max_seconds=DELAY_MAX_SECONDS,
        )

    @property
    def name(self):
        return self._name

    @property
    def unit_of_measurement(self):
        return ENERGY_KILO_WATT_HOUR

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return self._device_info

    @property
    def should_poll(self):
        return True

    @property
    def state(self):
        return self._state

    @property
    def device_class(self):
        return DEVICE_CLASS_ENERGY

    @property
    def extra_state_attributes(self):
        return {
            # ATTR_LAST_RESET: self.last_reset,
            ATTR_STATE_CLASS: self.state_class,
        }

    # @property
    # def last_reset(self):
    #     self._last_reset = dt_util.utc_from_timestamp(0)  # Deprecated

    @property
    def state_class(self):
        return STATE_CLASS_TOTAL_INCREASING

    async def async_added_to_hass(self) -> None:
        # Try to load previous state using RestoreEntity
        #
        # self.async_get_last_state().last_update is tricky and can't be trusted in our
        # scenario. last_updated can be the last time HA exited because state is saved
        # at exit with last_updated=exit_time, not last_updated=sensor_last_update
        #
        # It's easier to just load the value and schedule an update with
        # schedule_update_ha_state() (which is meant for push sensors but...)

        state = await self.async_get_last_state()

        if not state:
            self._logger.debug("No previous state")

        else:
            try:
                self._state = float(state.state)
                self._logger.debug(
                    f"Restored previous state: {self._state} {ENERGY_KILO_WATT_HOUR}"
                )

            except ValueError:
                self._logger.debug("Invalid previous state")
                return

        self.barrier.force_next()
        self.schedule_update_ha_state(force_refresh=True)

    async def async_update(self):
        # Delegate update window, forced updates, min/max age to the barrier
        # If barrier allows the execution just call the API to read measure

        if self.barrier.allowed():
            try:
                await self._api.select_contract(self._contact)
                measure = await self._api.get_measure()
                self._state = measure.accumulate
                self.barrier.sucess()

            except ideenergy.ClientError as e:
                self._logger.debug(f"Error reading measure: {e}.")
                self.barrier.fail()

        await self.barrier.delay()


class Historical(HistoricalEntity, SensorEntity):
    def __init__(self, unique_id, device_info, name, api, contract, logger=_LOGGER):
        self._logger = logger
        self._unique_id = unique_id
        self._name = name
        self._device_info = device_info
        self._api = api
        self._contact = contract

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def name(self):
        return self._name

    @property
    def unit_of_measurement(self):
        return ENERGY_KILO_WATT_HOUR

    @property
    def native_unit_of_measurement(self):
        return ENERGY_KILO_WATT_HOUR

    @property
    def state(self):
        return None

    @property
    def device_info(self):
        return self._device_info

    @property
    def device_class(self):
        return DEVICE_CLASS_ENERGY

    @property
    def extra_state_attributes(self):
        return {
            ATTR_LAST_RESET: self.last_reset,
            ATTR_STATE_CLASS: self.state_class,
        }

    @property
    def state_class(self):
        return STATE_CLASS_MEASUREMENT

    @property
    def last_reset(self):
        return None

    @property
    def entity_registry_enabled_default(self):
        return False

    async def async_update(self):
        now = datetime.now()

        # 00:00 of today
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 00:00 of the prev week
        start = end - timedelta(days=7)

        await self._api.select_contract(self._contact)
        data = await self._api.get_consumption_period(start, end)
        data = [
            (
                dt_util.as_utc(dt) + timedelta(hours=1),
                value / 1000,
                {"last_reset": dt_util.as_utc(dt)},
            )
            for (dt, value) in data["historical"]
        ]
        self.extend_historical_log(data)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,  # noqa DiscoveryInfoType | None
):
    api = hass.data[DOMAIN][config_entry.entry_id]
    details = await api.get_contract_details()

    device_info = DeviceInfo(
        # TODO: check serial as valid identifier
        identifiers={
            # (DOMAIN, self.unique_id),
            ("serial", str(details["listContador"][0]["numSerieEquipo"])),
        },
        name=details["cups"],
        # "name": sanitize_address(details["direccion"]),
        manufacturer=details["listContador"][0]["tipMarca"],
    )

    sensors = {
        subtype: Sensor(
            unique_id=f"{config_entry.entry_id}-{subtype}",
            name=config_entry.data[CONF_NAME].lower() + f"_{subtype}",
            device_info=device_info,
            api=api,
            contract=str(details["codContrato"]),
            logger=_LOGGER.getChild(subtype),
        )
        for (Sensor, subtype) in [
            (Accumulated, "accumulated"),
            (Historical, "historical"),
        ]
    }

    add_entities(sensors.values(), update_before_add=False)
