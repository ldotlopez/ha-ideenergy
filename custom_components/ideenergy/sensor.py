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
from typing import Dict, List, Optional, Set, Tuple

import ideenergy
from homeassistant.components.sensor import (
    ATTR_STATE_CLASS,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import DEVICE_CLASS_ENERGY, ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry
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
    DEFAULT_NAME_PREFIX,
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
    DATA_ATTR_HISTORICAL_POWER_DEMAND,
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
        super().__init__(*args, **kwargs)

        cups = dict(device_info["identifiers"])["cups"].lower()

        self.entity_id = f"sensor.{DEFAULT_NAME_PREFIX}_{cups}_{self.IDE_SENSOR_TYPE}"
        self._attr_name = f"{device_info['name']} {self.IDE_SENSOR_NAME}"
        self._attr_unique_id = f"{DEFAULT_NAME_PREFIX}-{cups}-{self.IDE_SENSOR_TYPE}"
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_device_info = device_info
        self._attr_entity_registry_enabled_default = True
        self._attr_entity_registry_visible_default = True

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
    IDE_SENSOR_NAME = "Dumb"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._attr_entity_registry_visible_default = False
        self._attr_state = "running"

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

    IDE_SENSOR_NAME = "Accumulated"
    IDE_SENSOR_TYPE = "accumulated"

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

    IDE_SENSOR_NAME = "Historical consumption"
    IDE_SENSOR_TYPE = "historical_consumption"

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

    IDE_SENSOR_NAME = "Historical generation"
    IDE_SENSOR_TYPE = "historical_generation"

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


class HistoricalPowerDemand(HistoricalSensor, IdeSensor, CoordinatorEntity):
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

    IDE_SENSOR_NAME = "Historical power demand"
    IDE_SENSOR_TYPE = "historical_power_demand"

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
    add_entities: AddEntitiesCallback,
    discovery_info: Optional[DiscoveryInfoType] = None,  # noqa DiscoveryInfoType | None
):
    api = hass.data[DOMAIN][config_entry.entry_id]
    try:
        contract_details = await api.get_contract_details()
    except ideenergy.client.ClientError as e:
        _LOGGER.debug(f"Unable to initialize integration: {e}")

    device_identifiers = {
        ("cups", contract_details["cups"]),
    }

    # Update previous devices
    _update_device_registry(
        hass,
        device_identifiers,
        old_serial=str(contract_details["listContador"][0]["numSerieEquipo"]),
    )

    device_info = DeviceInfo(
        identifiers=device_identifiers,
        name=f"CUPS {contract_details['cups']}",
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
            DataSetType.HISTORICAL_POWER_DEMAND: TimeDeltaBarrier(
                delta=timedelta(hours=36)
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
        HistoricalPowerDemand(
            config_entry=config_entry, device_info=device_info, coordinator=coordinator
        ),
    ]

    add_entities(sensors, update_before_add=True)


def _update_device_registry(
    hass: HomeAssistant,
    identifiers: Set[Tuple[str, str]],
    old_serial: str | None = None,
):
    dr = device_registry.async_get(hass)

    # Check devices registered with CUPS as serial
    if old_serial:
        old_identifiers = {("serial", old_serial)}
        old_device = dr.async_get_device(identifiers=old_identifiers)

        if old_device:
            _LOGGER.debug(f"Update device registry {old_identifiers} → {identifiers} ")
            dr.async_update_device(old_device.id, new_identifiers=identifiers)


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


def _historical_data_to_date_states(data: List[Dict] | None) -> List[DatedState]:
    def _convert_item(item):
        return DatedState(
            state=item["value"] / 1000,
            when=dt_util.as_utc(item["end"]),
            attributes={"last_reset": dt_util.as_utc(item["start"])},
        )

    return [_convert_item(item) for item in data or []]
