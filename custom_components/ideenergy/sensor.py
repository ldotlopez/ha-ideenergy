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


# TODO
# Maybe we need to mark some function as callback but I'm not sure whose.
# from homeassistant.core import callback


# Check sensor.SensorEntityDescription
# https://github.com/home-assistant/core/blob/dev/homeassistant/components/sensor/__init__.py


import logging
from datetime import timedelta
from typing import Dict, List, Optional, Union

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.util import dt as dtutil
from homeassistant_historical_sensor import (
    HistoricalSensor,
    HistoricalState,
)

from .const import DOMAIN
from .datacoordinator import (
    DATA_ATTR_HISTORICAL_CONSUMPTION,
    DATA_ATTR_HISTORICAL_GENERATION,
    DATA_ATTR_HISTORICAL_POWER_DEMAND,
    DATA_ATTR_MEASURE_ACCUMULATED,
    DATA_ATTR_MEASURE_INSTANT,
    DataSetType,
)
from .entity import IDeEntity

ATTR_LAST_POWER_READING = "Last Power Reading"
PLATFORM = "sensor"

MAINLAND_SPAIN_ZONEINFO = dtutil.zoneinfo.ZoneInfo("Europe/Madrid")
_LOGGER = logging.getLogger(__name__)


# The IDeSensor class provides:
#     __init__
#     __repr__
#     name
#     unique_id
#     device_info
#     entity_registry_enabled_default
# The CoordinatorEntity class provides:
#     should_poll
#     async_update
#     async_added_to_hass
#     available


class HistoricalSensorMixin(HistoricalSensor):
    @callback
    def _handle_coordinator_update(self) -> None:
        self.hass.add_job(self.async_write_ha_historical_states())

    def async_update_historical(self) -> None:
        pass


class StatisticsMixin(HistoricalSensor):
    @property
    def statatistic_id(self):
        return self.entity_id

    def get_statatistic_metadata(self) -> StatisticMetaData:
        meta = super().get_statatistic_metadata()
        meta["has_sum"] = True
        return meta

    async def async_calculate_statistic_data(
        self, hist_states: List[HistoricalState], *, latest: Optional[dict]
    ) -> List[StatisticData]:
        if latest:
            cutoff = dtutil.utc_from_timestamp(latest.get("end") or 0)
            accumulated = latest.get("sum") or 0
            hist_states = [x for x in hist_states if x.dt >= cutoff]

        else:
            accumulated = 0

        def calculate_statistics_from_accumulated(accumulated):
            for x in hist_states:
                accumulated = accumulated + x.state
                # Shift start by 1 hour since DatedState.when represents the
                # end of the period
                yield StatisticData(
                    start=x.dt - timedelta(hours=1), state=x.state, sum=accumulated
                )

        return list(calculate_statistics_from_accumulated(accumulated))


class AccumulatedConsumption(RestoreEntity, IDeEntity, SensorEntity):
    I_DE_PLATFORM = PLATFORM
    I_DE_ENTITY_NAME = "Accumulated Consumption"
    I_DE_DATA_SETS = [DataSetType.MEASURE]

    # TOTAL vs TOTAL_INCREASING:
    #
    # It's recommended to use state class total without last_reset whenever possible,
    # state class total_increasing or total with last_reset should only be used when
    # state class total without last_reset does not work for the sensor.
    # https://developers.home-assistant.io/docs/core/entity/sensor/#how-to-choose-state_class-and-last_reset

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def state(self):
        if self.coordinator.data is None:
            return None

        return self.coordinator.data[DATA_ATTR_MEASURE_ACCUMULATED]

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        saved_data = await self.async_get_last_state()
        self.coordinator.update_internal_data(saved_data)

    async def async_get_last_state(self):
        # Try to load previous state using RestoreEntity
        #
        # self.async_get_last_state().last_update is tricky and can't be trusted in our
        # scenario. last_updated can be the last time HA exited because state is saved
        # at exit with last_updated=exit_time, not last_updated=sensor_last_update
        #
        # It's easier to just load the value and schedule an update with
        # schedule_update_ha_state() (which is meant for push sensors but...)

        state = await super().async_get_last_state()

        try:
            ret = {
                DATA_ATTR_MEASURE_ACCUMULATED: float(state.state),
                DATA_ATTR_MEASURE_INSTANT: float(
                    state.attributes[ATTR_LAST_POWER_READING]
                ),
            }
            _LOGGER.debug(f"restore state: restored as {ret}")
            return ret

        except (AttributeError, KeyError, TypeError, ValueError):
            _LOGGER.debug(f"restore state: discard state {state!r}")

        return {}


class InstantPowerDemand(RestoreEntity, IDeEntity, SensorEntity):
    I_DE_PLATFORM = PLATFORM
    I_DE_ENTITY_NAME = "Instant Power Demand"
    I_DE_DATA_SETS = [DataSetType.MEASURE]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT

    @property
    def state(self):
        if self.coordinator.data is None:
            return None

        return self.coordinator.data[DATA_ATTR_MEASURE_INSTANT]

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        saved_data = await self.async_get_last_state()
        self.coordinator.update_internal_data(saved_data)

    async def async_get_last_state(self):
        state = await super().async_get_last_state()

        try:
            ret = {
                DATA_ATTR_MEASURE_INSTANT: float(state.state),
            }
            _LOGGER.debug(f"restore state: restored as {ret}")
            return ret

        except (AttributeError, TypeError, ValueError):
            _LOGGER.debug(f"restore state: discard state {state!r}")

        return {}


class HistoricalConsumption(
    StatisticsMixin, HistoricalSensorMixin, IDeEntity, SensorEntity
):
    I_DE_PLATFORM = PLATFORM
    I_DE_ENTITY_NAME = "Historical Consumption"
    I_DE_DATA_SETS = [DataSetType.HISTORICAL_CONSUMPTION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_entity_registry_enabled_default = False
        self._attr_state = None

    @property
    def historical_states(self):
        ret = historical_states_from_historical_api_data(
            self.coordinator.data[DATA_ATTR_HISTORICAL_CONSUMPTION]["historical"]
        )

        return ret


class HistoricalGeneration(
    StatisticsMixin, HistoricalSensorMixin, IDeEntity, SensorEntity
):
    I_DE_PLATFORM = PLATFORM
    I_DE_ENTITY_NAME = "Historical Generation"
    I_DE_DATA_SETS = [DataSetType.HISTORICAL_GENERATION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_entity_registry_enabled_default = False
        self._attr_state = None

    @property
    def historical_states(self):
        ret = historical_states_from_historical_api_data(
            self.coordinator.data[DATA_ATTR_HISTORICAL_GENERATION]["historical"]
        )

        return ret


class HistoricalPowerDemand(HistoricalSensorMixin, IDeEntity, SensorEntity):
    I_DE_PLATFORM = PLATFORM
    I_DE_ENTITY_NAME = "Historical Power Demand"
    I_DE_DATA_SETS = [DataSetType.HISTORICAL_POWER_DEMAND]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_entity_registry_enabled_default = False
        self._attr_state = None
        self._attr_statistics_enabled = False

    @property
    def historical_states(self):
        def _convert_item(item):
            # [
            #     {
            #         "dt": datetime.datetime(2021, 4, 24, 13, 0),
            #         "value": 3012.0
            #     },
            #     ...
            # ]
            return HistoricalState(
                state=item["value"] / 1000,
                dt=item["dt"].replace(tzinfo=MAINLAND_SPAIN_ZONEINFO),
            )

        data = self.coordinator.data[DATA_ATTR_HISTORICAL_POWER_DEMAND]
        ret = [_convert_item(item) for item in data]

        return ret


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,  # noqa DiscoveryInfoType | None
):
    coordinator, device_info = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [
        AccumulatedConsumption(
            config_entry=config_entry, device_info=device_info, coordinator=coordinator
        ),
        InstantPowerDemand(
            config_entry=config_entry, device_info=device_info, coordinator=coordinator
        ),
        HistoricalConsumption(
            config_entry=config_entry, device_info=device_info, coordinator=coordinator
        ),
        HistoricalGeneration(
            config_entry=config_entry, device_info=device_info, coordinator=coordinator
        ),
        HistoricalPowerDemand(
            config_entry=config_entry, device_info=device_info, coordinator=coordinator
        ),
    ]
    async_add_devices(sensors)


def historical_states_from_historical_api_data(
    data: Optional[List[Dict]] = None,
) -> List[HistoricalState]:
    def _convert_item(item):
        # FIXME: What about canary islands?
        dt = item["end"].replace(tzinfo=MAINLAND_SPAIN_ZONEINFO)
        last_reset = item["start"].replace(tzinfo=MAINLAND_SPAIN_ZONEINFO)

        return HistoricalState(
            state=item["value"] / 1000,
            dt=dt,
            attributes={"last_reset": last_reset},
        )

    return [_convert_item(item) for item in data or []]
