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


from __future__ import annotations

import math
import sys
from datetime import datetime
from typing import Any, Mapping, Optional

from homeassistant.config import DATA_CUSTOMIZE
from homeassistant.const import (
    ATTR_ASSUMED_STATE,
    ATTR_ATTRIBUTION,
    ATTR_DEVICE_CLASS,
    ATTR_ENTITY_PICTURE,
    ATTR_FRIENDLY_NAME,
    ATTR_ICON,
    ATTR_SUPPORTED_FEATURES,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
)
from homeassistant.core import (
    EVENT_STATE_CHANGED,
    Context,
    EventOrigin,
    State,
    StateMachine,
    callback,
    dt_util,
)
from homeassistant.helpers.entity import Entity

FLOAT_PRECISION = abs(int(math.floor(math.log10(abs(sys.float_info.epsilon))))) - 1


# Modified version of
# homeassistant.core.StateMachine.async_set
# https://github.com/home-assistant/core/blob/dev/homeassistant/core.py


@callback
def async_set(
    self: StateMachine,
    entity_id: str,
    new_state: str,
    attributes: Optional[Mapping[str, Any]] = None,
    force_update: bool = False,
    context: Optional[Context] = None,
    time_fired: Optional[datetime] = None,
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
    if (old_state := self._states.get(entity_id)) is None:
        same_state = False
        same_attr = False
        last_changed = None
    else:
        same_state = old_state.state == new_state and not force_update
        same_attr = old_state.attributes == attributes
        last_changed = old_state.last_changed if same_state else None

    if same_state and same_attr:
        return

    if context is None:
        context = Context()

    time_fired = time_fired or dt_util.utcnow()
    state = State(
        entity_id,
        new_state,
        attributes,
        last_changed,
        time_fired,
        context,
        old_state is None,
    )
    self._states[entity_id] = state
    self._bus.async_fire(
        EVENT_STATE_CHANGED,
        {"entity_id": entity_id, "old_state": old_state, "new_state": state},
        EventOrigin.local,
        context,
        time_fired=time_fired,
    )


# Modified version of
# homeassistant.helpers.entity.Entity._stringify_state
# https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/entity.py


def _stringify_state(self: Entity, state: Any) -> str:
    """Convert state to string."""
    if not self.available:
        return STATE_UNAVAILABLE
    if state is None:
        return STATE_UNKNOWN
    if isinstance(state, float):
        # If the entity's state is a float, limit precision according to machine
        # epsilon to make the string representation readable
        return f"{state:.{FLOAT_PRECISION}}"
    return str(state)


# Code extracted and modified from
# homeassistant.helpers.entity.Entity._async_write_ha_state
# https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/entity.py


def _build_attributes(self: Entity, state: Any) -> Mapping[str, str]:
    attr = self.capability_attributes
    attr = dict(attr) if attr else {}

    state = _stringify_state(self, state)
    if self.available:
        attr.update(self.state_attributes or {})
        extra_state_attributes = self.extra_state_attributes
        # Backwards compatibility for "device_state_attributes" deprecated in 2021.4
        # Add warning in 2021.6, remove in 2021.10
        if extra_state_attributes is None:
            extra_state_attributes = self.device_state_attributes
        attr.update(extra_state_attributes or {})

    unit_of_measurement = self.unit_of_measurement
    if unit_of_measurement is not None:
        attr[ATTR_UNIT_OF_MEASUREMENT] = unit_of_measurement

    entry = self.registry_entry
    # pylint: disable=consider-using-ternary
    if (name := (entry and entry.name) or self.name) is not None:
        attr[ATTR_FRIENDLY_NAME] = name

    if (icon := (entry and entry.icon) or self.icon) is not None:
        attr[ATTR_ICON] = icon

    if (entity_picture := self.entity_picture) is not None:
        attr[ATTR_ENTITY_PICTURE] = entity_picture

    if assumed_state := self.assumed_state:
        attr[ATTR_ASSUMED_STATE] = assumed_state

    if (supported_features := self.supported_features) is not None:
        attr[ATTR_SUPPORTED_FEATURES] = supported_features

    if (device_class := self.device_class) is not None:
        attr[ATTR_DEVICE_CLASS] = str(device_class)

    if (attribution := self.attribution) is not None:
        attr[ATTR_ATTRIBUTION] = attribution

    # Overwrite properties that have been set in the config file.
    if DATA_CUSTOMIZE in self.hass.data:
        attr.update(self.hass.data[DATA_CUSTOMIZE].get(self.entity_id))

    # Convert temperature if we detect one
    try:
        unit_of_measure = attr.get(ATTR_UNIT_OF_MEASUREMENT)
        units = self.hass.config.units
        if (
            unit_of_measure in (TEMP_CELSIUS, TEMP_FAHRENHEIT)
            and unit_of_measure != units.temperature_unit
        ):
            prec = len(state) - state.index(".") - 1 if "." in state else 0
            temp = units.temperature(float(state), unit_of_measure)
            state = str(round(temp) if prec == 0 else round(temp, prec))
            attr[ATTR_UNIT_OF_MEASUREMENT] = units.temperature_unit
    except ValueError:
        # Could not convert state to float
        pass

    return attr
