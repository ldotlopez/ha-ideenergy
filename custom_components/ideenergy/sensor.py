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


import logging
from typing import Dict, List, Optional

from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEVICE_CLASS_ENERGY, ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType
from homeassistant.util import dt as dt_util

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
from .historical_sensor import DatedState, HistoricalSensor

ATTR_LAST_POWER_READING = "Last Power Reading"
PLATFORM = "sensor"
_LOGGER = logging.getLogger(__name__)


class Accumulated(IDeEntity, SensorEntity):
    """
    The IDeSensor class provides:
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

    I_DE_ENTITY_NAME = "accumulated"
    I_DE_DATA_SETS = [DataSetType.MEASURE]
    I_DE_PLATFORM = PLATFORM

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = DEVICE_CLASS_ENERGY
        self._attr_state_class = STATE_CLASS_TOTAL_INCREASING
        self._attr_unit_of_measurement = ENERGY_KILO_WATT_HOUR

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


class HistoricalConsumption(HistoricalSensor, IDeEntity, SensorEntity):
    """
    The IDeSensor class provides:
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

    I_DE_ENTITY_NAME = "historical-consumption"
    I_DE_PLATFORM = PLATFORM
    I_DE_DATA_SETS = [DataSetType.HISTORICAL_CONSUMPTION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = DEVICE_CLASS_ENERGY
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_entity_registry_enabled_default = False
        self._attr_extra_state_attributes = {
            ATTR_STATE_CLASS: self.state_class,
        }
        self._attr_state = None

    @property
    def historical_states(self):
        ret = _historical_data_to_date_states(
            self.coordinator.data[DATA_ATTR_HISTORICAL_CONSUMPTION]["historical"]
        )

        return ret

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_historical_states()


class HistoricalGeneration(HistoricalSensor, IDeEntity, SensorEntity):
    """
    The IDeSensor class provides:
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

    I_DE_ENTITY_NAME = "historical-generation"
    I_DE_PLATFORM = PLATFORM
    I_DE_DATA_SETS = [DataSetType.HISTORICAL_GENERATION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = DEVICE_CLASS_ENERGY
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_entity_registry_enabled_default = False
        self._attr_extra_state_attributes = {
            ATTR_STATE_CLASS: self.state_class,
        }
        self._attr_state = None

    @property
    def historical_states(self):
        ret = _historical_data_to_date_states(
            self.coordinator.data[DATA_ATTR_HISTORICAL_GENERATION]["historical"]
        )

        return ret

    # async def async_update_historical_states(self):
    #     pass

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_historical_states()


class HistoricalPowerDemand(HistoricalSensor, IDeEntity, SensorEntity):
    """
    The IDeSensor class provides:
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

    I_DE_ENTITY_NAME = "historical-power-demand"
    I_DE_DATA_SETS = [DataSetType.HISTORICAL_POWER_DEMAND]

    I_DE_PLATFORM = PLATFORM
    I_DE_DATA_SETS = [DataSetType.HISTORICAL_POWER_DEMAND]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_device_class = DEVICE_CLASS_ENERGY
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_unit_of_measurement = ENERGY_KILO_WATT_HOUR
        self._attr_entity_registry_enabled_default = False
        self._attr_extra_state_attributes = {
            ATTR_STATE_CLASS: self.state_class,
        }
        self._attr_state = None

    @property
    def historical_states(self):
        data = self.coordinator.data[DATA_ATTR_HISTORICAL_POWER_DEMAND]
        ret = [DatedState(when=item["dt"], state=item["value"]) for item in data]

        return ret

    # async def async_update_historical_states(self):
    #     pass

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_historical_states()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_devices: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,  # noqa DiscoveryInfoType | None
):
    coordinator, device_info = hass.data[DOMAIN][config_entry.entry_id]
    sensors = [
        # DumbSensor(
        #     config_entry=config_entry,
        #     device_info=device_info,
        #     coordinator=coordinator,
        # ),
        Accumulated(
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


def _historical_data_to_date_states(data: List[Dict] | None) -> List[DatedState]:
    def _convert_item(item):
        return DatedState(
            state=item["value"] / 1000,
            when=dt_util.as_utc(item["end"]),
            attributes={"last_reset": dt_util.as_utc(item["start"])},
        )

    return [_convert_item(item) for item in data or []]
