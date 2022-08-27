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


import functools
import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from homeassistant.components import recorder
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from sqlalchemy import not_, or_

from .hack import _build_attributes, _stringify_state

_LOGGER = logging.getLogger(__name__)


@dataclass
class DatedState:
    state: Any
    when: datetime
    attributes: Dict[str, Any] = field(default_factory=dict)


# You must know:
# * DB keeps datetime object as utc
# * Each time hass is started a new record is created, that record can be 'unknow'
#   or 'unavailable'


class HistoricalEntityStandAlone:
    HISTORICAL_UPDATE_INTERVAL = timedelta(hours=12)

    async def async_update_history(self):
        _LOGGER.debug("You must override this method")
        return []

    @property
    def should_poll(self):
        # HistoricalEntities MUST NOT poll.
        # Polling creates incorrect states at intermediate time points.

        return False

    @property
    def state(self):
        # Better report unavailable than anything
        #
        # Another aproach is to return data from historical entity, but causes
        # wrong results. Keep here for reference.
        #
        # HistoricalEntities doesnt' pull but state is accessed only once when
        # the sensor is registered for the first time in the database
        #
        # if state := self.historical_state():
        #     return float(state)

        return None

    # @property
    # def available(self):
    #     # Leave us alone!
    #     return False

    async def _run_async_update_history(self, now=None) -> None:
        def _normalize_time_state(st):
            if not isinstance(st, DatedState):
                return None

            if st.when.tzinfo is None:
                st.when = dt_util.as_local(st.when)

            if st.when.tzinfo is not timezone.utc:
                st.when = dt_util.as_utc(st.when)

            return st

        #
        # Normalize and filter historical states
        #
        dated_states = await self.async_update_history()
        dated_states = [_normalize_time_state(x) for x in dated_states]
        dated_states = [x for x in dated_states if x is not None]
        dated_states = list(sorted(dated_states, key=lambda x: x.when))

        _LOGGER.debug(f"Got {len(dated_states)} measures from sensor")

        #
        # Setup recorder write
        #
        if dated_states:
            fn = functools.partial(self._recorder_write_states, dated_states)
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

        self.recorder = recorder.get_instance(self.hass)  # type: ignore[attr-defined]

        _LOGGER.debug(f"{self.entity_id}: added to hass")  # type: ignore[attr-defined]

        await self._run_async_update_history()
        async_track_time_interval(
            self.hass,  # type: ignore[attr-defined]
            self._run_async_update_history,
            self.HISTORICAL_UPDATE_INTERVAL,
        )
        _LOGGER.debug(
            f"{self.entity_id}: "  # type: ignore[attr-defined]
            f"updating each {self.HISTORICAL_UPDATE_INTERVAL.total_seconds()} seconds"
        )

    def _recorder_write_states(self, dated_states):
        _LOGGER.debug("Writing states on recorder")

        with recorder.util.session_scope(
            session=self.recorder.get_session()
        ) as session:
            #
            # Cleanup invalid states in database
            #
            invalid_states = (
                session.query(recorder.db_schema.States)
                .filter(recorder.db_schema.States.entity_id == self.entity_id)
                .filter(
                    or_(
                        recorder.db_schema.States.state == STATE_UNKNOWN,
                        recorder.db_schema.States.state == STATE_UNAVAILABLE,
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
                session.query(recorder.db_schema.States)
                .filter(recorder.db_schema.States.entity_id == self.entity_id)
                .filter(  # Just in case…
                    not_(
                        or_(
                            recorder.db_schema.States.state == STATE_UNKNOWN,
                            recorder.db_schema.States.state == STATE_UNAVAILABLE,
                        )
                    )
                )
                .order_by(recorder.db_schema.States.last_updated.desc())
                .first()
            )
            # first_run = latest_db_state is None

            #
            # Drop historical states older than lastest db state
            #
            dated_states = list(sorted(dated_states, key=lambda x: x.when))
            if latest_db_state:
                # Fix TZINFO from database
                cutoff = latest_db_state.last_updated.replace(tzinfo=timezone.utc)
                _LOGGER.debug(
                    "Found previous states in db, latest is dated at "
                    f"{cutoff} ({latest_db_state.state})"
                )
                dated_states = [x for x in dated_states if x.when > cutoff]

            if not dated_states:
                _LOGGER.debug("No new states detected")
                return

            _LOGGER.debug(
                f"Ready to save {len(dated_states)} states extending from "
                f"{dated_states[0].when} to {dated_states[-1].when}"
            )

            #
            # Build recorder State, StateAttributes and Event
            #

            db_states = []
            for idx, dt_st in enumerate(dated_states):
                attrs_as_dict = _build_attributes(self, dt_st.state)
                attrs_as_dict.update(dt_st.attributes)
                attrs_as_str = recorder.db_schema.JSON_DUMP(attrs_as_dict)

                attrs_as_bytes = (
                    b"{}" if dt_st.state is None else attrs_as_str.encode("utf-8")
                )

                attrs_hash = recorder.db_schema.StateAttributes.hash_shared_attrs_bytes(
                    attrs_as_bytes
                )

                state_attributes = recorder.db_schema.StateAttributes(
                    hash=attrs_hash, shared_attrs=attrs_as_str
                )

                state = recorder.db_schema.States(
                    entity_id=self.entity_id,
                    last_changed=dt_st.when,
                    last_updated=dt_st.when,
                    old_state=db_states[idx - 1] if idx else latest_db_state,
                    state=_stringify_state(self, dt_st.state),
                    state_attributes=state_attributes,
                )
                _LOGGER.debug(f" => {state.state} @ {state.last_changed}")
                db_states.append(state)

            session.add_all(db_states)
            session.commit()

            _LOGGER.debug(f"Added {len(db_states)} to database")


class HistoricalSensor:
    """The HistoricalSensor class provides:

    - should_poll
    - state

    Sensors based on HistoricalSensor must provide:
    - async_update_historical_states
    - historical_states property o self._historical_states
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._historical_states = []

    async def async_update_historical_states(self):
        """async_update_historical_states()

        Implement this async method to fetch historical data from provider and store
        into self._historical_states
        """
        _LOGGER.debug("You must override this method")

    @property
    def should_poll(self):
        # HistoricalEntities MUST NOT poll.
        # Polling creates incorrect states at intermediate time points.

        return False

    @property
    def state(self):
        # Better report unavailable than anything
        #
        # Another aproach is to return data from historical entity, but causes
        # wrong results. Keep here for reference.
        #
        # HistoricalEntities doesnt' pull but state is accessed only once when
        # the sensor is registered for the first time in the database
        #
        # if state := self.historical_state():
        #     return float(state)

        return None

    @property
    def historical_states(self):
        return self._historical_states

    # @property
    # def available(self):
    #     # Leave us alone!
    #     return False

    def async_write_ha_historical_states(self):
        def _normalize_time_state(st):
            if not isinstance(st, DatedState):
                return None

            if st.when.tzinfo is None:
                st.when = dt_util.as_local(st.when)

            if st.when.tzinfo is not timezone.utc:
                st.when = dt_util.as_utc(st.when)

            return st

        dated_states = self.historical_states
        dated_states = [_normalize_time_state(x) for x in dated_states]
        dated_states = [x for x in dated_states if x is not None]
        dated_states = list(sorted(dated_states, key=lambda x: x.when))

        _LOGGER.debug(f"Got {len(dated_states)} measures from sensor")

        if not dated_states:
            _LOGGER.debug("Nothing to write")
            return

        fn = functools.partial(self._save_states_into_recorder, dated_states)
        self._get_recorder_instance().async_add_executor_job(fn)

        _LOGGER.debug("Added job executor to save states")

    def _get_recorder_instance(self):
        return recorder.get_instance(self.hass)

    def _save_states_into_recorder(self, dated_states):
        _LOGGER.debug("Writing states on recorder")

        with recorder.util.session_scope(
            session=self._get_recorder_instance().get_session()
        ) as session:
            #
            # Cleanup invalid states in database
            #
            invalid_states = (
                session.query(recorder.db_schema.States)
                .filter(recorder.db_schema.States.entity_id == self.entity_id)
                .filter(
                    or_(
                        recorder.db_schema.States.state == "unknown",
                        recorder.db_schema.States.state == "unavailable",
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
                session.query(recorder.db_schema.States)
                .filter(recorder.db_schema.States.entity_id == self.entity_id)
                .filter(  # Just in case…
                    not_(
                        or_(
                            recorder.db_schema.States.state == "unknown",
                            recorder.db_schema.States.state == "unavailable",
                        )
                    )
                )
                .order_by(recorder.db_schema.States.last_updated.desc())
                .first()
            )
            # first_run = latest_db_state is None

            #
            # Drop historical states older than lastest db state
            #
            dated_states = list(sorted(dated_states, key=lambda x: x.when))
            if latest_db_state:
                # Fix TZINFO from database
                cutoff = latest_db_state.last_updated.replace(tzinfo=timezone.utc)
                _LOGGER.debug(
                    "Found previous states in db, latest is dated at "
                    f"{cutoff} ({latest_db_state.state})"
                )
                dated_states = [x for x in dated_states if x.when > cutoff]

            if not dated_states:
                _LOGGER.debug("No new states detected")
                return

            _LOGGER.debug(f"About to write {len(dated_states)} states to database")
            _LOGGER.debug(
                f"Extending from {dated_states[0].when} to {dated_states[-1].when}"
            )

            #
            # Build recorder State, StateAttributes and Event
            #

            db_states = []
            for idx, dt_st in enumerate(dated_states):
                attrs_as_dict = _build_attributes(self, dt_st.state)
                attrs_as_dict.update(dt_st.attributes)
                attrs_as_str = recorder.db_schema.JSON_DUMP(attrs_as_dict)

                attrs_as_bytes = (
                    b"{}" if dt_st.state is None else attrs_as_str.encode("utf-8")
                )

                attrs_hash = recorder.db_schema.StateAttributes.hash_shared_attrs_bytes(
                    attrs_as_bytes
                )

                state_attributes = recorder.db_schema.StateAttributes(
                    hash=attrs_hash, shared_attrs=attrs_as_str
                )

                state = recorder.db_schema.States(
                    entity_id=self.entity_id,
                    last_changed=dt_st.when,
                    last_updated=dt_st.when,
                    old_state=db_states[idx - 1] if idx else latest_db_state,
                    state=_stringify_state(self, dt_st.state),
                    state_attributes=state_attributes,
                )
                _LOGGER.debug(f" => {state.state} @ {state.last_changed}")
                db_states.append(state)

            session.add_all(db_states)
            session.commit()

            _LOGGER.debug(f"Added {len(db_states)} to database")


class CustomUpdateEntity(Entity):
    """
    CustomPolling provides:

      - UPDATE_INTERVAL: timedelta
      - async_added_to_hass(self)
      - async_custom_update(self)
    """

    UPDATE_INTERVAL: timedelta = timedelta(seconds=30)

    async def async_added_to_hass(self) -> None:
        """Once added to hass:
        - Setup internal stuff with the Store to hold internal state
        - Setup a peridioc call to update the entity
        """

        if self.should_poll:
            raise Exception("poll model is not supported")

        _LOGGER.debug(f"{self.entity_id}: added to hass")  # type: ignore[attr-defined]

        await self.async_custom_update()
        async_track_time_interval(
            self.hass,
            self.async_custom_update,
            self.UPDATE_INTERVAL,
        )
        _LOGGER.debug(
            f"{self.entity_id}: "
            f"updating each {self.UPDATE_INTERVAL.total_seconds()} seconds"
        )

    @abstractmethod
    async def async_custom_update(self) -> None:
        raise NotImplementedError()
