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


#
#
# Working code from ha-ideenergy (bus-based method) generates this data:
#

# state_id=17768045
# domain=
# entity_id=sensor.icp_es0021000002618134yh_historical
# state=0.166
# attributes=
# event_id=
#     event_id=18133720
#     event_type=state_changed
#     event_data=
#     origin=LOCAL
#     time_fired=2022-05-02 22:00:00.000000
#     created=
#     context_id=fcc29a6db8c26bc77893729f5dfa8305
#     context_user_id=
#     context_parent_id=
# last_changed=2022-05-02 22:00:00.000000
# last_updated=2022-05-02 22:00:00.000000
# created=
# context_id=
# context_user_id=
# old_state_id=17768044   # References similar stuff at 2022-05-02 22:00:00.000000
# attributes_id=685157
#     attributes_id=685157
#     hash=994929976
#     shared_attrs:str={"state_class":"measurement","last_reset":"2022-05-02T21:00:00+00:00","unit_of_measurement":"kWh","friendly_name":"icp_es0021000002618134yh_historical","device_class":"energy"}


# Current code creates this data
# state_id=50
# entity_id=sensor.mcfly
# state=106.8
# attributes=
# event_id=493
#     event_id=493
#     event_type=state_changed
#     event_data={"new_state":{"entity_id":"sensor.mcfly","state":"106.8","attributes":{},"last_changed":"2022-05-03T15:22:00+00:00","last_updated":"2022-05-03T15:22:00+00:00","context":{"id":"c5c354e2ff37df5d798bacc319430ee5","parent_id":null,"user_id":null}},"entity_id":"sensor.mcfly"}
#     origin=LOCAL
#     time_fired=2022-05-03 15:22:00.000000,
#     context_id=26998505e7597b1ce8a919dd3453937e
#     context_user_id=
#     context_parent_id=
# last_changed=2022-05-03 15:20:00.000000
# last_updated=2022-05-03 15:22:00.000000
# old_state_id=49 # Similar stuff but for 2022-05-03 15:20:00.000000
# attributes_id=

"""
select * from
    states as st
    inner join events as ev
        on states.event_id = events.event_id
    inner join state_attributes as sa
        on states.attributes_id = state_attributes.attributes_id
    where
        state_id = (select max(state_id) from states where entity_id in ('sensor.mcfly','sensor.icp_es0021000002618134yh_accumulated') and state not in ('unknown', 'unavailable'));
"""

# state_id    domain      entity_id     state   attributes  event_id    last_changed                last_updated                created     context_id  context_user_id  old_state_id  attributes_id  event_id    event_type     event_data  origin      time_fired                  created     context_id                        context_user_id  context_parent_id  attributes_id  hash        shared_attrs
# ----------  ----------  -------------------------------------------  ----------  ----------  ----------  --------------------------  --------------------------  ----------  ----------  ---------------  ------------  -------------  ----------  -------------  ----------  ----------  --------------------------  ----------  --------------------------------  ---------------  -----------------  -------------  ----------  --------------------------------------------------------------------------------------------------------------------
# 17767877                sensor.mcfly  45825.0             18133551    2022-05-03 14:05:03.489654  2022-05-03 14:05:03.489654                                           17767875      144            18133551    state_changed              LOCAL       2022-05-03 14:05:03.489654              a315f2f229180984fdea1d081814b839                                      144            1502492789  {"state_class":"total_increasing","unit_of_measurement":"kWh","device_class":"energy","friendly_name":"icp_es0021000002618134yh_accumulated"}


# state_id                entity_id     state   attributes  event_id   last_changed                last_updated                old_state_id  attributes_id  event_id  event_type     event_data  origin  time_fired                  context_id  context_user_id  context_parent_id  attributes_id  hash        shared_attrs
# --------                ------------  ------  ----------  --------  --------------------------  --------------------------  ------------  -------------  --------  -------------  ----------  ------  --------------------------  ----------  ---------------  -----------------  -------------  ----------  --------------------------------------------------------------------------------------------------------------------------------------------------
# 862                     sensor.mcfly  3348.0              3468        2022-05-04 07:00:00.000000  2022-05-04 07:00:00.000000  861           529            3468      state_changed                      2022-05-04 07:00:00.000000                                                  529            3236127255  {"state_class":"measurement","unit_of_measurement":"kWh","friendly_name":"mcfly","device_class":"energy","last_reset":"2022-05-04T06:00:00+00:00"}

import functools
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional

from homeassistant import core
from homeassistant.components import recorder
from homeassistant.components.recorder import models
from homeassistant.components.recorder.util import session_scope
from homeassistant.components.sensor.recorder import compile_statistics
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from sqlalchemy import func as sql_func
from sqlalchemy import or_, not_

from .hack import _build_attributes, _stringify_state, async_set

_LOGGER = logging.getLogger(__name__)

# STORE_LAST_UPDATE = "last_update"
# STORE_LAST_STATE = "last_state"


# @dataclass
# class HistoricalData:
#     log: list[tuple[datetime, Any]]
#     data: Mapping[str, Any]
#     state: Store

HISTORICAL_UPDATE_INTERVAL = timedelta(minutes=6)


@dataclass
class StateAtTimePoint:
    state: Any
    when: datetime
    attributes: Dict[str, Any]


class HistoricalEntity:
    # You must know:
    # * DB keeps datetime object as utc
    # * Each time hass is started a new record is created
    # * That record can be 'unknow' or 'unavailable'

    async def async_update_history(self):
        _LOGGER.debug("You must override this method")
        return []

    @property
    def should_poll(self):
        """HistoricalEntities MUST NOT poll.
        Polling creates incorrect states at intermediate time points.
        """
        return False

    # @property
    # def last_reset(self):
    #     """Returning any else will cause discontinuities in history IDKW"""
    #     return None

    #     # Another aproach is to return data from historical entity, but causes
    #     # wrong results. Keep here for reference
    #     # FIXME: Write a proper method to access HistoricalEntity internal
    #     # state
    #     #
    #     # try:
    #     #     return self.historical.data[STORE_LAST_UPDATE]
    #     # except KeyError:
    #     #     return None

    @property
    def state(self):
        # Better report unavailable than anything
        return None

        # Another aproach is to return data from historical entity, but causes
        # wrong results. Keep here for reference.
        #
        # HistoricalEntities doesnt' pull but state is accessed only once when
        # the sensor is registered for the first time in the database
        #
        # if state := self.historical_state():
        #     return float(state)

    # @property
    # def available(self):
    #     # Leave us alone!
    #     return False

    async def _run_async_update_history(self, now=None) -> None:
        def _normalize_time_state(st):
            if not isinstance(st, StateAtTimePoint):
                return None

            if st.when.tzinfo is None:
                st.when = dt_util.as_local(st.when)

            if st.when.tzinfo is not timezone.utc:
                st.when = dt_util.as_utc(st.when)

            return st

        #
        # Normalize and filter historical states
        #
        states_at_dt = await self.async_update_history()
        states_at_dt = [_normalize_time_state(x) for x in states_at_dt]
        states_at_dt = [x for x in states_at_dt if x is not None]
        states_at_dt = list(sorted(states_at_dt, key=lambda x: x.when))

        _LOGGER.debug(f"Got {len(states_at_dt)} measures from sensor")

        #
        # Setup recorder write
        #
        if states_at_dt:
            fn = functools.partial(self._recorder_write_states, states_at_dt)
            self.recorder.async_add_executor_job(fn)

            _LOGGER.debug("Executor job set to write them")
        else:
            _LOGGER.debug("Nothing to write")

    async def async_added_to_hass(self) -> None:
        """Once added to hass:
        - Setup internal stuff with the Store to hold internal state
        - Setup a peridioc call to update the entity
        """

        if self.should_poll:
            raise Exception("poll model is not supported")

        _LOGGER.debug(f"{self.entity_id} ready")  # type: ignore[attr-defined]

        self.recorder = recorder.get_instance(self.hass)  # type: ignore[attr-defined]
        self.recorder.async_add_executor_job(self._recorder_cleanup)

        await self._run_async_update_history()
        async_track_time_interval(
            self.hass,  # type: ignore[attr-defined]
            self._run_async_update_history,
            HISTORICAL_UPDATE_INTERVAL,
        )
        _LOGGER.debug(f"{self.entity_id} ready")  # type: ignore[attr-defined]

    def _recorder_cleanup(self):
        pass
        # with session_scope(session=self.recorder.get_session()) as session:
        #     invalid_states = (
        #         session.query(models.States)
        #         .filter(models.States.entity_id == self.entity_id)
        #         .filter(
        #             or_(
        #                 models.States.state == "unknown",
        #                 models.States.state == "unavailable",
        #             )
        #         )
        #     )

        #     if invalid_states.count():
        #         _LOGGER.debug(
        #             f"Deleted {invalid_states.count()} invalid states from recorder"
        #         )
        #         invalid_states.delete()
        #         session.commit()

    def _recorder_write_states(self, states_at_dt):
        _LOGGER.debug("Writing states on recorder")

        with session_scope(session=self.recorder.get_session()) as session:
            #
            # Cleanup invalid states in database
            #
            invalid_states = (
                session.query(models.States)
                .filter(models.States.entity_id == self.entity_id)
                .filter(
                    or_(
                        models.States.state == "unknown",
                        models.States.state == "unavailable",
                    )
                )
            )
            for st in invalid_states:
                # session.delete(st.event)
                # session.delete(st.state_attributes)
                session.delete(st)

            session.commit()

            #
            # Check latest state in the database
            #
            latest_db_state = (
                session.query(models.States)
                .filter(models.States.entity_id == self.entity_id)
                .filter(  # Just in case…
                    not_(
                        or_(
                            models.States.state == "unknown",
                            models.States.state == "unavailable",
                        )
                    )
                )
                .order_by(models.States.last_updated.desc())
                .first()
            )
            # first_run = latest_db_state is None

            #
            # Drop historical states older than lastest db state
            #
            states_at_dt = list(sorted(states_at_dt, key=lambda x: x.when))
            if latest_db_state:
                # Fix TZINFO from database
                cutoff = latest_db_state.last_updated.replace(tzinfo=timezone.utc)
                _LOGGER.debug(
                    "Found previous states in db, latest is dated at "
                    f"{cutoff} ({latest_db_state.state})"
                )
                states_at_dt = [x for x in states_at_dt if x.when > cutoff]

            if not states_at_dt:
                _LOGGER.debug("No new states detected")
                return

            _LOGGER.debug(f"About to write {len(states_at_dt)} states to database")
            _LOGGER.debug(
                f"Extending from {states_at_dt[0].when} to {states_at_dt[-1].when}"
            )

            # Hack to force stats
            # if first_run:
            #     states_at_dt = [states_at_dt[0]]

            #
            # Build recorder State, StateAttributes and Event
            #
            db_states = []
            for idx, st_dt in enumerate(states_at_dt):
                event = models.Events(
                    event_type=core.EVENT_STATE_CHANGED,
                    time_fired=st_dt.when,
                )

                attrs_as_dict = _build_attributes(self, st_dt.state)
                attrs_as_dict.update(st_dt.attributes)
                attrs_as_str = models.JSON_DUMP(attrs_as_dict)
                attrs_hash = models.StateAttributes.hash_shared_attrs(attrs_as_str)
                state_attributes = models.StateAttributes(
                    hash=attrs_hash, shared_attrs=attrs_as_str
                )

                state = models.States(
                    entity_id=self.entity_id,
                    event=event,
                    last_changed=st_dt.when,
                    last_updated=st_dt.when,
                    old_state=db_states[idx - 1] if idx else latest_db_state,
                    state=_stringify_state(self, st_dt.state),
                    state_attributes=state_attributes,
                )
                _LOGGER.debug(f" => {state.state} @ {state.last_changed}")
                db_states.append(state)

            session.add_all(db_states)
            session.commit()

            _LOGGER.debug(f"Added {len(db_states)} to database")

            # if first_run:
            #     from homeassistant.components.recorder import statistics

            #     statistics.compile_statistics(self.recorder, db_states[0].last_updated)
