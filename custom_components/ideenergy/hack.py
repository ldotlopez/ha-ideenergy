# -*- coding: utf-8 -*-
#
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

from homeassistant.core import HomeAssistant
from homeassistant.core import (
    EVENT_STATE_CHANGED,
    Any,
    Optional,
    Context,
    EventOrigin,
    Mapping,
    MappingProxyType,
    State,
    callback,
    datetime,
    dt_util,
)


def write_state_at_time(
    hass: HomeAssistant,
    entity_id: str,
    state: str,
    dt: Optional[datetime.datetime],
    attributes: Optional[MappingProxyType] = None,
):
    if attributes is None:
        old_state = hass.states.get(entity_id)
        if old_state:
            attributes = hass.states.get(entity_id).attributes
        else:
            attributes = None

    return async_set(
        hass.states,
        entity_id=entity_id,
        new_state=state,
        attributes=attributes,
        force_update=False,
        context=None,
        now=dt,
    )


@callback
def async_set(
    state_machine,
    entity_id: str,
    new_state: str,
    attributes: Optional[Mapping[str, Any]] = None,
    force_update: bool = False,
    context: Optional[Context] = None,
    now: Optional[datetime.datetime] = None,
) -> None:
    """Set the state of an entity, add entity if it does not exist.

    Attributes is an optional dict to specify attributes of this state.

    If you just update the attributes and not the state, last changed will
    not be affected.

    This method must be run in the event loop.
    """
    entity_id = entity_id.lower()
    new_state = str(new_state)
    attributes = attributes or {}
    if (old_state := state_machine._states.get(entity_id)) is None:
        same_state = False
        same_attr = False
        last_changed = None
    else:
        same_state = old_state.state == new_state and not force_update
        same_attr = old_state.attributes == MappingProxyType(attributes)
        last_changed = old_state.last_changed if same_state else None

    if same_state and same_attr:
        return

    if context is None:
        context = Context()

    now = now or dt_util.utcnow()
    state = State(
        entity_id,
        new_state,
        attributes,
        last_changed,
        now,
        context,
        old_state is None,
    )
    state_machine._states[entity_id] = state
    state_machine._bus.async_fire(
        EVENT_STATE_CHANGED,
        {"entity_id": entity_id, "old_state": old_state, "new_state": state},
        EventOrigin.local,
        context,
        time_fired=now,
    )
