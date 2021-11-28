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
from homeassistant.const import (
    CONF_NAME,
    DEVICE_CLASS_ENERGY,
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import HomeAssistant
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
from .hack import write_state_at_time


class IDEEnergyAccumulatedSensor(RestoreEntity, SensorEntity):
    def __init__(self, name, api, unique_id, details, logger=_LOGGER):
        self._logger = logger
        self._name = name + "_consumed"
        self._unique_id = unique_id

        # TODO: check serial as valid identifier
        self._device_info = {
            "identifiers": {
                (DOMAIN, self.unique_id),
                ("serial", str(details["listContador"][0]["numSerieEquipo"])),
            },
            "manufacturer": details["listContador"][0]["tipMarca"],
            "name": self._name,
        }

        self._api = api
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
            measure = await self._api.get_measure()
        except ideenergy.ClientError as e:
            self._logger.error(f"Error reading measure: {e}")
            return

        self._state = measure.accumulate
        self._logger.info(
            f"State updated: {self.state} {ENERGY_KILO_WATT_HOUR}"
        )


class IDEEnergyHistoricalSensor(SensorEntity):
    def __init__(self, hass, name, api, unique_id, details, logger=_LOGGER):
        self._logger = logger
        self._name = name + "_historical"
        self._unique_id = unique_id

        # TODO: check serial as valid identifier
        self._device_info = {
            "identifiers": {
                (DOMAIN, self.unique_id),
                ("serial", str(details["listContador"][0]["numSerieEquipo"])),
            },
            "manufacturer": details["listContador"][0]["tipMarca"],
            "name": self._name,
        }

        self._hass = hass
        self._api = api
        self._states = []
        self._hass_state_initialized = False
        self._last_api_update = dt_util.as_local(datetime.fromtimestamp(0))

    # async def async_added_to_hass(self) -> None:
    #     state = await self.async_get_last_state()

    #     try:
    #         self._states = [(state.last_changed, float(state.state))]
    #     except (AttributeError, TypeError):
    #         self._logger.debug(f"Invalid previous state: {state!r}")
    #         self._states = []

    #     self._last_api_update = state.last_updated
    #     self._logger.debug(
    #         "Restored state: {(state.last_changed, state.state)!r}, "
    #         "API update: {state.last_updated}",
    #     )

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
    def unique_id(self):
        return self._unique_id

    @property
    def available(self):
        return len(self._states) > 0

    @property
    def state(self):
        if self._hass_state_initialized is False:
            self._logger.debug("HASS state initalized")
        self._hass_state_initialized = True
        return self._states[-1][1]

    @property
    def should_poll(self):
        return True

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
        entity_id = f"sensor.{self.name}"
        now = dt_util.now()

        refresh_api_data = (
            not self._states
            or (now - self._last_api_update).total_seconds()
            >= HISTORICAL_MAX_AGE
        )

        # Update data from API
        if refresh_api_data:
            self._logger.debug("API data is too old, updating")
            try:
                data = await self._api.get_consumption_period(
                    now.replace(day=1), now
                )
                data["historical"] = list(
                    sorted(data["historical"], key=lambda x: x[0])
                )
                self._states = data["historical"]
                self._last_api_update = now

            except ideenergy.RequestFailedError as e:
                self._logger.error(f"Error getting data from API: {e}")
                refresh_api_data = False

        else:
            self._logger.debug("Skip API data update")

        # Writing historical data before first state has been generate leads to
        # entity duplication (adding second entity with '_2' suffix)
        if not self._hass_state_initialized:
            self._logger.debug(
                "state has not been initialized yet, " "skip history rewrite"
            )
            return

        if len(self._states) <= 1:
            self._logger.debug("No historical states to write")
            return

        try:
            attributes = self._hass.states.get(entity_id).attributes
        except AttributeError:
            attributes = None

        for (dt, state) in self._states:
            write_state_at_time(
                self._hass, entity_id, state, dt, attributes=attributes
            )
            diff = int((now - dt).total_seconds())
            mins = int(diff // 60)
            secs = diff % 60

            self._logger.debug(
                f"{entity_id} set to {state} at "
                f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d} "
                f"({mins:02d} min {secs:02d} secs ago)"
            )
        self._states = [self._states[-1]]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
    discovery_info: Optional[
        DiscoveryInfoType
    ] = None,  # noqa DiscoveryInfoType | None
):
    api = hass.data[DOMAIN][config_entry.entry_id]
    details = await api.get_contract_details()

    sensors = [
        IDEEnergyHistoricalSensor(
            hass=hass,
            api=api,
            name=config_entry.data[CONF_NAME].lower(),
            unique_id=f"{config_entry.entry_id}-historical",
            details=details,
            logger=_LOGGER.getChild("historical"),
        )
    ]

    # Shouldn't this option be already set?
    if config_entry.options.get(CONF_ENABLE_DIRECT_MEASURE, False):
        sensors.append(
            IDEEnergyAccumulatedSensor(
                api=api,
                name=config_entry.data[CONF_NAME].lower(),
                unique_id=f"{config_entry.entry_id}-accumulated",
                details=details,
                logger=_LOGGER.getChild("accumulated"),
            )
        )

    add_entities(sensors, update_before_add=True)
