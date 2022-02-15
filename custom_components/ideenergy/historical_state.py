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

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Optional

from homeassistant.core import MappingProxyType
from homeassistant.components.sensor.recorder import compile_statistics
from homeassistant.core import MappingProxyType, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .hack import _build_attributes, _stringify_state, async_set

_LOGGER = logging.getLogger(__name__)
STORE_LAST_UPDATE = "last_update"
STORE_LAST_STATE = "last_state"


@dataclass
class HistoricalData:
    log: list[tuple[datetime, Any]]
    data: Mapping[str, Any]
    state: Store


class HistoricalEntity:
    @property
    def should_poll(self):
        """HistoricalEntities MUST NOT poll.
        Polling creates incorrect states at intermediate time points.
        """
        return False

    async def async_added_to_hass(self) -> None:
        """Once added to hass:
        - Setup internal stuff with the Store to hold internal state
        - Setup a peridioc call to update the entity
        """

        async def _execute_update(*args, **kwargs):
            _LOGGER.debug("Run update")
            await self.async_update()
            await self.flush_historical_log()

        if self.should_poll:
            raise Exception("poll model is not supported")

        self.historical.state = Store(hass=self.hass, version=1, key=self.entity_id)
        await self.load_state()

        if not self.should_poll:
            async_track_time_interval(
                self.hass, _execute_update, timedelta(seconds=60 * 60 * 6)
            )

        await self.flush_historical_log()

        _LOGGER.debug(f"HistoricalEntity ready, last entry: {self.historical.data!r}")

    def historical_state(self):
        """Just in case the entity needs to implement state property"""

        return self.historical.data[STORE_LAST_STATE]

    def extend_historical_log(
        self, data: Iterable[tuple[datetime, Any, Optional[Mapping]]]
    ) -> None:
        """Add historical states to the queue.
        The data is an iterable of tuples, each of one must be:
        - 1st element in the tuple represents the time when the state was
          generated
        - 2nd element is the value of the state
        - 3rd element are extra attributes that must be attached to the state
        """

        self.historical.log.extend(data)

    async def flush_historical_log(self):
        """Write internal log to the database."""

        if not self.hass or not self.historical.state:
            _LOGGER.warning("Entity not added to hass yet")
            return

        self.historical.log = list(sorted(self.historical.log, key=lambda x: x[0]))
        if not self.historical.log:
            return

        # stats_start = self.historical.log[0][2]["last_reset"]
        # stats_end = self.historical.log[-1][0]

        while True:
            try:
                pack = self.historical.log.pop(0)
            except IndexError:
                break

            if len(pack) == 2:
                dt, value = pack
                attributes = {}
            else:
                dt, value, attributes = pack

            if dt <= self.historical.data[STORE_LAST_UPDATE]:
                _LOGGER.debug(f"Skip update for {value} @ {dt}")
                continue

            if dt >= dt_util.now():
                _LOGGER.debug(f"Skip FUTURE for {value} @ {dt}")
                continue

            _LOGGER.debug(f"Write historical state: {value} @ {dt} {attributes!r}")
            self.write_state_at_time(
                value,
                dt=dt,
                attributes=attributes,
            )

            await self.save_state({STORE_LAST_UPDATE: dt, STORE_LAST_STATE: value})

        # self.hass.async_add_executor_job(self._stats, stats_start, stats_end)

    # @callback
    # def _stats(self, start, end):
    #     _LOGGER.debug(f"Similate from {start} to {end}")
    #     compile_statistics(self.hass, start, end)

    # @callback
    # def _statistics(self):

    #     _LOGGER.debug("Stats start")
    #     compile_statistics(
    #         self.hass,
    #         dt_util.as_local(datetime(year=2021, month=11, day=1)),
    #         dt_util.now(),
    #     )
    #     _LOGGER.debug("Stats done")

    async def save_state(self, params):
        """Convenient function to store internal state"""

        data = self.historical.data
        data.update(params)

        self.historical.data = data.copy()

        data[STORE_LAST_UPDATE] = dt_util.as_utc(data[STORE_LAST_UPDATE]).timestamp()

        await self.historical.state.async_save(data)
        return data

    async def load_state(self):
        """Convenient function to load internal state"""

        data = (await self.historical.state.async_load()) or {}
        data = {
            STORE_LAST_STATE: None,
            STORE_LAST_UPDATE: 0,
        } | data

        data[STORE_LAST_UPDATE] = dt_util.as_utc(
            datetime.fromtimestamp(data[STORE_LAST_UPDATE])
        )

        self.historical.data = data
        return data

    @property
    def historical(self):
        """The general trend in homeassistant helpers is to use them as mixins,
        without inheritance, so no super().__init__() is called.

        Because of that internal stuff is implemented internal data stuff as a
        property.
        """

        attr = getattr(self, "_historical", None)
        if not attr:
            attr = HistoricalData(log=[], data={}, state=None)
            setattr(self, "_historical", attr)

        return attr

    def write_state_at_time(
        self: Entity,
        state: str,
        dt: Optional[datetime],
        attributes: Optional[MappingProxyType] = None,
    ):
        """
        Wrapper for the modified version of
        homeassistant.core.StateMachine.async_set
        """
        state = _stringify_state(self, state)
        attrs = dict(_build_attributes(self, state))
        attrs.update(attributes or {})

        ret = async_set(
            self.hass.states,
            entity_id=self.entity_id,
            new_state=state,
            attributes=attrs,
            time_fired=dt,
        )

        return ret
