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

import random
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
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.util import dt as dt_util

from . import _LOGGER
from .const import (
    CONF_ENABLE_DIRECT_MEASURE,
    DOMAIN,
    HISTORICAL_MAX_AGE,
    MEASURE_MAX_AGE,
    UPDATE_BARRIER_MINUTE_MAX,
    UPDATE_BARRIER_MINUTE_MIN,
)
from .historical_state import HistoricalEntity


class Accumulated(RestoreEntity, SensorEntity):
    def __init__(self, unique_id, device_info, name, api, contract, logger=_LOGGER):
        self._logger = logger
        self._name = name
        self._unique_id = unique_id

        self._device_info = device_info
        self._api = api
        self._contact = contract
        self._state = None
        self._unsub_sched_update = None

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
        return False

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
        state = await self.async_get_last_state()

        force_update = False
        update_reason = None

        if not state:
            force_update = True
            update_reason = "No previous state"

        else:
            try:
                self._state = float(state.state)
                self._logger.debug(
                    f"Restored previous state: "
                    f"{self._state} {ENERGY_KILO_WATT_HOUR}"
                )

                if (
                    dt_util.now() - state.last_updated
                ).total_seconds() > MEASURE_MAX_AGE:
                    force_update = True
                    update_reason = "Previous state is too old"

            except ValueError:
                force_update = True
                update_reason = "Invalid previous state"
                self.async_schedule_update_ha_state(force_refresh=True)

        if force_update:
            self._logger.debug(f"Force state refresh: {update_reason}")
            self.async_schedule_update_ha_state(force_refresh=True)

        self.schedule_next_update()

    def schedule_next_update(self):
        if self._unsub_sched_update:
            self._unsub_sched_update()
            self._unsub_sched_update = None
            self._logger.debug("Previous task cleaned")

        now = dt_util.now()
        update_min = random.randrange(
            UPDATE_BARRIER_MINUTE_MIN, UPDATE_BARRIER_MINUTE_MAX
        )
        update_sec = random.randrange(0, 60)

        next_update = now.replace(minute=update_min, second=update_sec)
        if now.minute >= UPDATE_BARRIER_MINUTE_MIN:
            next_update = next_update + timedelta(hours=1)

        self._logger.info(
            f"Next update in {(next_update - now).total_seconds()} secs "
            f"({next_update})"
        )

        self._unsub_sched_update = async_track_time_change(
            self.hass,
            self.do_scheduled_update,
            hour=[next_update.hour],
            minute=[next_update.minute],
            second=[next_update.second],
        )

    async def do_scheduled_update(self, now):
        self.async_schedule_update_ha_state(force_refresh=True)
        self.schedule_next_update()

    async def async_update(self):
        try:
            await self._api.select_contract(self._contact)
            measure = await self._api.get_measure()
        except ideenergy.ClientError as e:
            self._logger.error(f"Error reading measure: {e}")
            return

        self._state = measure.accumulate
        self._logger.info(f"State updated: {self.state} {ENERGY_KILO_WATT_HOUR}")


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
            (Historical, "historical"),
            (Accumulated, "accumulated"),
        ]
    }

    add_entities(sensors.values(), update_before_add=True)