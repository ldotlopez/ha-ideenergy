# Copyright (C) 2021-2026 Luis López <luis@cuarentaydos.com>
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


import itertools
from datetime import datetime
from functools import cached_property
from logging import getLogger
from math import ceil
from typing import cast

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback, dt_util
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant_historical_sensor import (
    HistoricalSensor,
    HistoricalState,
    hass_get_last_statistic,
)

from .coordinator import (
    MEASURE_ACCUMULATED_KEY,
    IDeEnergyCoordinatorDataSet,
    IDeEnergyDataCoordinator,
)
from .data import IntegrationIDeEnergyConfigEntry, build_entity_unique_id

PLATFORM = "sensor"

LOGGER = getLogger(__name__)


class IDeEnergySensor(CoordinatorEntity, HistoricalSensor, SensorEntity):
    I_DE_PLATFORM: str = PLATFORM
    I_DE_ENTITY_NAME: str
    I_DE_DATA_SET: set
    coordinator: IDeEnergyDataCoordinator

    def __init__(
        self,
        *args,
        device_info: DeviceInfo,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self._attr_has_entity_name = True
        self._attr_name = self.I_DE_ENTITY_NAME
        self._attr_device_info = device_info

        self._attr_unique_id = build_entity_unique_id(
            device_info, self.I_DE_ENTITY_NAME
        )

        self._attr_state_attributes = {}

    @cached_property
    def unique_id(self) -> str:
        return build_entity_unique_id(self.device_info, self.I_DE_ENTITY_NAME)

    # ==
    # Entity
    # ==
    async def async_added_to_hass(self) -> None:
        LOGGER.info(f"{self.entity_id} added to hass")
        await super().async_added_to_hass()

        for x in self.I_DE_DATA_SET:
            self.coordinator.activate_dataset(x)

        # await self.async_update_historical()
        await self.coordinator.async_request_refresh()
        # await self.async_write_historical()
        LOGGER.info(f"{self.entity_id} updated historical")

    async def async_will_remove_from_hass(self) -> None:
        for x in self.I_DE_DATA_SET:
            self.coordinator.deactivate_dataset(x)

        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.hass.async_create_task(self.async_write_historical())

    # It's a coordinator entity, do nothing
    async def async_update_historical(self) -> None:
        pass

    # ==
    # Historical sensor
    # ==
    @property
    def historical_states(self) -> list[HistoricalState]:
        return cast(
            list[HistoricalState],
            self.coordinator.data[IDeEnergyCoordinatorDataSet.HISTORICAL_CONSUMPTION],
        )

    def get_statistic_metadata(self) -> StatisticMetaData:
        meta = super().get_statistic_metadata()
        device_name = self.device_info.get("name") if self.device_info else None
        meta["name"] = (
            f"{device_name} {self.I_DE_ENTITY_NAME}"
            if device_name
            else self.I_DE_ENTITY_NAME
        )
        meta["has_sum"] = True
        return meta

    async def async_calculate_statistic_data(
        self, hist_states: list[HistoricalState], *, latest: dict | None = None
    ) -> list[StatisticData]:
        #
        # Filter out invalid states
        #

        n_original_hist_states = len(hist_states)
        hist_states = [x for x in hist_states if x.state not in (0, None)]
        if len(hist_states) != n_original_hist_states:
            LOGGER.warning(
                f"{self.entity_id}: "
                + "found some weird values in historical statistics"
            )

        #
        # Group historical states by hour block
        #

        def hour_block_for_hist_state(hist_state: HistoricalState) -> datetime:
            secs_per_hour = 60 * 60

            ts = ceil(hist_state.timestamp)
            block = ts // secs_per_hour
            leftover = ts % secs_per_hour

            if leftover == 0:
                block = block - 1

            return block * secs_per_hour

        latest = await hass_get_last_statistic(self.hass, self.get_statistic_metadata())

        #
        # Get last sum sum from latest
        #
        def extract_last_sum(latest) -> float:
            return float(latest["sum"]) if latest else 0

        try:
            total_accumulated = extract_last_sum(latest)
        except KeyError, ValueError:
            LOGGER.error(
                f"{self.entity_id}: [bug] statistics broken (lastest={latest!r})"
            )
            return []

        start_point_local_dt = dt_util.as_local(
            dt_util.utc_from_timestamp(latest.get("start", 0) if latest else 0)
        )

        LOGGER.debug(
            f"{self.entity_id}: "
            + f"calculating statistics using {total_accumulated:.2f} as base accumulated "
            + f"(registed at {start_point_local_dt})"
        )

        #
        # Calculate statistic data
        #

        ret = []

        for hour_block, collection_it in itertools.groupby(
            hist_states, key=hour_block_for_hist_state
        ):
            collection = list(collection_it)

            # hour_mean = statistics.mean([x.state for x in collection])
            hour_accumulated = sum([x.state for x in collection])
            total_accumulated = total_accumulated + hour_accumulated

            ret.append(
                StatisticData(
                    start=dt_util.utc_from_timestamp(hour_block),
                    state=hour_accumulated,
                    # mean=hour_mean,
                    sum=total_accumulated,
                )
            )

        return ret


class AccumulatedConsumption(RestoreSensor, CoordinatorEntity, SensorEntity):
    I_DE_PLATFORM = PLATFORM
    I_DE_ENTITY_NAME = "Accumulated Consumption"
    I_DE_DATA_SET = {IDeEnergyCoordinatorDataSet.DIRECT_READING}

    coordinator: IDeEnergyDataCoordinator

    def __init__(
        self,
        *args,
        device_info: DeviceInfo,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self._attr_has_entity_name = True
        self._attr_name = self.I_DE_ENTITY_NAME
        self._attr_unique_id = build_entity_unique_id(
            device_info, self.I_DE_ENTITY_NAME
        )
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_device_info = device_info
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_native_value = None
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        reading = self.coordinator.data.get(IDeEnergyCoordinatorDataSet.DIRECT_READING)
        if reading and MEASURE_ACCUMULATED_KEY in reading:
            self._attr_native_value = reading[MEASURE_ACCUMULATED_KEY]
            self.async_write_ha_state()

    # ==
    # Entity
    # ==
    async def async_added_to_hass(self) -> None:
        LOGGER.info(f"{self.entity_id} added to hass")
        await super().async_added_to_hass()

        for x in self.I_DE_DATA_SET:
            self.coordinator.activate_dataset(x)

        await self.coordinator.async_request_refresh()
        LOGGER.info(f"{self.entity_id} updated historical")

        prev = await self.async_get_last_sensor_data()
        LOGGER.debug(f"{self.entity_id} last sensor data: {prev!r}")
        if prev is not None and prev.native_value is not None:
            self._attr_native_value = prev.native_value
            LOGGER.debug(f"{self.entity_id} restored previous value of {self.state}")
        else:
            LOGGER.debug(f"{self.entity_id} no previous sensor data to restore")

    async def async_will_remove_from_hass(self) -> None:
        for x in self.I_DE_DATA_SET:
            self.coordinator.deactivate_dataset(x)

        await super().async_will_remove_from_hass()


class HistoricalConsumption(IDeEnergySensor):
    I_DE_PLATFORM = PLATFORM
    I_DE_ENTITY_NAME = "Historical Consumption"
    I_DE_DATA_SET = {IDeEnergyCoordinatorDataSet.HISTORICAL_CONSUMPTION}

    def get_statistic_metadata(self):
        meta = super().get_statistic_metadata()
        meta["unit_class"] = SensorDeviceClass.ENERGY
        meta["unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        return meta

    @property
    def historical_states(self) -> list[HistoricalState] | None:
        return self.coordinator.data[IDeEnergyCoordinatorDataSet.HISTORICAL_CONSUMPTION]


class HistoricalGeneration(IDeEnergySensor):
    I_DE_PLATFORM = PLATFORM
    I_DE_ENTITY_NAME = "Historical Generation"
    I_DE_DATA_SET = {IDeEnergyCoordinatorDataSet.HISTORICAL_GENERATION}

    _attr_entity_registry_enabled_default = False

    def get_statistic_metadata(self):
        meta = super().get_statistic_metadata()
        meta["unit_class"] = SensorDeviceClass.ENERGY
        meta["unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        return meta

    @property
    def historical_states(self) -> list[HistoricalState] | None:
        return self.coordinator.data[IDeEnergyCoordinatorDataSet.HISTORICAL_GENERATION]


##
# Migrate this to attributes in a general sensor
# Using statistics for the isolated points representing demand peaks has no sense

# class PowerDemandPeaks(IDeEnergySensor):
#     I_DE_PLATFORM = PLATFORM
#     I_DE_ENTITY_NAME = "Power Demand Peaks"
#     I_DE_DATA_SET = {IDeEnergyCoordinatorDataSet.POWER_DEMAND_PEAKS}

#     # def __init__(self, *args, **kwargs):
#     #     super().__init__(*args, **kwargs)
#     #     self._attr_device_class = SensorDeviceClass.ENERGY
#     #     self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
#     #
#     #     # TOTAL vs TOTAL_INCREASING:
#     #     #
#     #     # It's recommended to use state class total without last_reset whenever
#     #     # possible, state class total_increasing or total with last_reset should only be
#     #     # used when state class total without last_reset does not work for the sensor.
#     #     # https://developers.home-assistant.io/docs/core/entity/sensor/#how-to-choose-state_class-and-last_reset
#     #
#     #     # The sensor's value never resets, e.g. a lifetime total energy consumption or
#     #     # production: state_class total, last_reset not set or set to None
#     #
#     #     self._attr_state_class = SensorStateClass.TOTAL

#     def get_statistic_metadata(self):
#         meta = super().get_statistic_metadata()
#         meta["unit_class"] = SensorDeviceClass.POWER
#         meta["unit_of_measurement"] = UnitOfPower.KILO_WATT
#         return meta

#     @property
#     def historical_states(self) -> list[HistoricalState] | None:
#         return self.coordinator.data[
#             IDeEnergyCoordinatorDataSet.POWER_DEMAND_PEAKS
#         ]  # ty:ignore[non-subscriptable]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntegrationIDeEnergyConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    IDeClasses = [AccumulatedConsumption, HistoricalConsumption, HistoricalGeneration]
    async_add_entities(
        [
            IDeClass(
                coordinator=entry.runtime_data.coordinator,
                device_info=entry.runtime_data.device_info,
            )
            for IDeClass in IDeClasses
        ]
    )
