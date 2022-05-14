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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from homeassistant import core
from homeassistant.components import recorder
from homeassistant.components.recorder import models
from homeassistant.components.recorder.util import session_scope
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from sqlalchemy import or_, not_

from .hack import _build_attributes, _stringify_state

_LOGGER = logging.getLogger(__name__)


@dataclass
class DatedState:
    state: Any
    when: datetime
    attributes: Dict[str, Any]


# You must know:
# * DB keeps datetime object as utc
# * Each time hass is started a new record is created, that record can be 'unknow'
#   or 'unavailable'


class HistoricalEntity:
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
