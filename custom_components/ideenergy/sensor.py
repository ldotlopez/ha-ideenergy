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

import logging
import math
from datetime import timedelta
from typing import Optional

from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, DEVICE_CLASS_ENERGY, ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
)  # DataUpdateCoordinator,; UpdateFailed,
from homeassistant.util import dt as dt_util

from .barrier import TimeDeltaBarrier, TimeWindowBarrier  # NoopBarrier,
from .const import (
    DELAY_MAX_SECONDS,
    DOMAIN,
    MAX_RETRIES,
    MEASURE_MAX_AGE,
    MIN_SCAN_INTERVAL,
    UPDATE_WINDOW_END_MINUTE,
    UPDATE_WINDOW_START_MINUTE,
)
from .datacoordinator import (
    DATA_ATTR_HISTORICAL_CONSUMPTION,
    DATA_ATTR_HISTORICAL_GENERATION,
    DATA_ATTR_MEASURE_ACCUMULATED,
    DATA_ATTR_MEASURE_INSTANT,
    DataSetType,
    IdeCoordinator,
)
from .historical_sensor import DatedState, HistoricalSensor

ATTR_LAST_POWER_READING = "Last Power Reading"
SCAN_INTERVAL = timedelta(seconds=5)
_LOGGER = logging.getLogger(__name__)


class IdeSensor(SensorEntity):
    """The IdeSensor class provides:
    __init__
    __repr__
    name
    unique_id
    device_info
    entity_registry_enabled_default
    """

    def __init__(self, *args, config_entry, device_info, **kwargs):
        self._unique_id = f"{config_entry.entry_id}-{self.IDE_SENSOR_TYPE}"
        self._name = config_entry.data[CONF_NAME].lower() + f"_{self.IDE_SENSOR_TYPE}"
        self._device_info = device_info

        super().__init__(*args, **kwargs)

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return self._device_info

    @property
    def entity_registry_enabled_default(self):
        return True

    def __repr__(self):
        clsname = self.__class__.__name__
        if hasattr(self, "coordinator"):
            api = self.coordinator.api.username
        else:
            api = self.api

        return f"<{clsname} {api.username}/{api._contract}>"

    # async def async_added_to_hass(self) -> None:
    #     # Try to load previous state using RestoreEntity
    #     #
    #     # self.async_get_last_state().last_update is tricky and can't be trusted in our
    #     # scenario. last_updated can be the last time HA exited because state is saved
    #     # at exit with last_updated=exit_time, not last_updated=sensor_last_update
    #     #
    #     # It's easier to just load the value and schedule an update with
    #     # schedule_update_ha_state() (which is meant for push sensors but...)

    #     await super().async_added_to_hass()

    #     state = await self.async_get_last_state()

    #     if (
    #         not state
    #         or state.state is None
    #         or state.state == STATE_UNKNOWN
    #         or state.state == STATE_UNAVAILABLE
    #     ):
    #         self._logger.debug("restore state: No previous state")

    #     else:
    #         try:
    #             self._state = float(state.state)
    #             self._logger.debug(
    #                 f"restore state: Got {self._state} {ENERGY_KILO_WATT_HOUR}"
    #             )

    #         except ValueError:
    #             self._logger.debug(
    #                 f"restore state: Discard invalid previous state {state!r}"
    #             )

    #     if self._state is None:
    #         self._logger.debug(
    #             "restore state: No previous state: scheduling force update"
    #         )
    #         self._barrier.force_next()
    #         self.schedule_update_ha_state(force_refresh=True)


class DumbSensor(IdeSensor, CoordinatorEntity):
    IDE_SENSOR_TYPE = "dumb"

    @property
    def state(self):
        return "running"

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class DirectReading(IdeSensor, CoordinatorEntity):
    """
    The IdeSensor class provides:
        __init__
        __repr__
        name
        unique_id
        device_info
        entity_registry_enabled_default

    The CoordinatorEntity class provides:
        should_poll
        async_update
        async_added_to_hass
        available
    """

    IDE_SENSOR_TYPE = "direct_reading"

    @property
    def device_class(self):
        return DEVICE_CLASS_ENERGY

    @property
    def state_class(self):
        return STATE_CLASS_TOTAL_INCREASING

    @property
    def unit_of_measurement(self):
        return ENERGY_KILO_WATT_HOUR

    @property
    def extra_state_attributes(self):
        last_power_reading = (
            self.coordinator.data[DATA_ATTR_MEASURE_INSTANT]
            if self.coordinator.data
            else None
        )

        return {
            ATTR_STATE_CLASS: self.state_class,
            ATTR_LAST_POWER_READING: last_power_reading,
        }

    @property
    def state(self):
        if self.coordinator.data is None:
            return None

        return self.coordinator.data[DATA_ATTR_MEASURE_ACCUMULATED]

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class HistoricalConsumption(HistoricalSensor, IdeSensor, CoordinatorEntity):
    """
    The IdeSensor class provides:
        __init__
        __repr__
        name
        unique_id
        device_info
        entity_registry_enabled_default

    The CoordinatorEntity class provides:
        should_poll
        async_update
        async_added_to_hass
        available
    """

    IDE_SENSOR_TYPE = "historical_consumption"

    @property  # Override IdeSensor.entity_registry_enabled_default
    def entity_registry_enabled_default(self):
        return False

    @property
    def device_class(self):
        return DEVICE_CLASS_ENERGY

    @property
    def state_class(self):
        return STATE_CLASS_MEASUREMENT

    @property
    def unit_of_measurement(self):
        return ENERGY_KILO_WATT_HOUR

    @property
    def extra_state_attributes(self):
        return {
            ATTR_STATE_CLASS: self.state_class,
        }

    @property
    def state(self):
        return None

    @property
    def historical_states(self):
        if not self.coordinator.data:
            return None

        data = self.coordinator.data[DATA_ATTR_HISTORICAL_CONSUMPTION]["historical"]
        data = [
            DatedState(
                state=value / 1000,
                when=dt_util.as_utc(dt) + timedelta(hours=1),
                attributes={"last_reset": dt_util.as_utc(dt)},
            )
            for (dt, value) in data
        ]

        return data

    async def async_update_historical_states(self):
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_historical_states()


class HistoricalGeneration(HistoricalSensor, IdeSensor, CoordinatorEntity):
    """
    The IdeSensor class provides:
        __init__
        __repr__
        name
        unique_id
        device_info
        entity_registry_enabled_default

    The CoordinatorEntity class provides:
        should_poll
        async_update
        async_added_to_hass
        available
    """

    IDE_SENSOR_TYPE = "historical_generation"

    @property  # Override IdeSensor.entity_registry_enabled_default
    def entity_registry_enabled_default(self):
        return False

    @property
    def device_class(self):
        return DEVICE_CLASS_ENERGY

    @property
    def state_class(self):
        return STATE_CLASS_MEASUREMENT

    @property
    def unit_of_measurement(self):
        return ENERGY_KILO_WATT_HOUR

    @property
    def extra_state_attributes(self):
        return {
            ATTR_STATE_CLASS: self.state_class,
        }

    @property
    def state(self):
        return None

    @property
    def historical_states(self):
        if not self.coordinator.data:
            return None

        data = self.coordinator.data[DATA_ATTR_HISTORICAL_GENERATION]
        data = [
            DatedState(
                state=value / 1000,
                when=dt_util.as_utc(dt) + timedelta(hours=1),
                attributes={"last_reset": dt_util.as_utc(dt)},
            )
            for (dt, value) in data["historical"]
        ]

        return data

    async def async_update_historical_states(self):
        pass

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_historical_states()


# class HistoricalPowerDemand(HistoricalSensor, IdeSensor, CoordinatorEntity):
#     """
#     The IdeSensor class provides:
#         __init__
#         __repr__
#         name
#         unique_id
#         device_info
#         entity_registry_enabled_default

#     The CoordinatorEntity class provides:
#         should_poll
#         async_update
#         async_added_to_hass
#         available
#     """

#     IDE_SENSOR_TYPE = "historical_power_demand"

#     @property  # Override IdeSensor.entity_registry_enabled_default
#     def entity_registry_enabled_default(self):
#         return False

#     @property
#     def device_class(self):
#         return DEVICE_CLASS_ENERGY

#     @property
#     def state_class(self):
#         return STATE_CLASS_MEASUREMENT

#     @property
#     def unit_of_measurement(self):
#         return ENERGY_KILO_WATT_HOUR

#     @property
#     def extra_state_attributes(self):
#         return {
#             ATTR_STATE_CLASS: self.state_class,
#         }

#     @property
#     def state(self):
#         return None

#     @property
#     def historical_states(self):
#         if not self.coordinator.data:
#             return None

#         data = self.coordinator.data[DATA_ATTR_HISTORICAL_POWER_DEMAND]
#         data = [
#             DatedState(
#                 state=value / 1000,
#                 when=dt_util.as_utc(dt) + timedelta(hours=1),
#                 attributes={"last_reset": dt_util.as_utc(dt)},
#             )
#             for (dt, value) in data["historical"]
#         ]

#         return data

#     async def async_update_historical_states(self):
#         pass

#     @callback
#     def _handle_coordinator_update(self) -> None:
#         self.async_write_ha_historical_states()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,  # noqa DiscoveryInfoType | None
):
    api = hass.data[DOMAIN][config_entry.entry_id]
    contract_details = await api.get_contract_details()

    device_info = DeviceInfo(
        # TODO: check serial as valid identifier
        identifiers={
            # (DOMAIN, self.unique_id),
            ("serial", str(contract_details["listContador"][0]["numSerieEquipo"])),
        },
        name=contract_details["cups"],
        # name=sanitize_address(details["direccion"]),
        manufacturer=contract_details["listContador"][0]["tipMarca"],
    )

    # Build coordinator
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
        },
        update_interval=_calculate_datacoordinator_update_interval(),
    )

    sensors = [
        DumbSensor(
            config_entry=config_entry,
            device_info=device_info,
            coordinator=coordinator,
        ),
        DirectReading(
            config_entry=config_entry, device_info=device_info, coordinator=coordinator
        ),
        HistoricalConsumption(
            config_entry=config_entry, device_info=device_info, coordinator=coordinator
        ),
        HistoricalGeneration(
            config_entry=config_entry, device_info=device_info, coordinator=coordinator
        ),
    ]

    add_entities(sensors, update_before_add=False)  # set update_before_add=False


def _calculate_datacoordinator_update_interval() -> timedelta:
    #
    # Calculate SCAN_INTERVAL to allow two updates within the update window
    #
    update_window_width = (
        UPDATE_WINDOW_END_MINUTE * 60 - UPDATE_WINDOW_START_MINUTE * 60
    )
    update_interval = math.floor(update_window_width / 2) - (DELAY_MAX_SECONDS * 2)
    update_interval = max([MIN_SCAN_INTERVAL, update_interval])

    return timedelta(seconds=update_interval)
