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


from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import slugify

if TYPE_CHECKING:
    # from ideenergy import Client
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .coordinator import IDeEnergyDataCoordinator

    # from .store import IDeEnergyConfigEntryState

type IntegrationIDeEnergyConfigEntry = ConfigEntry[IntegrationIDeEnergyRunTimeData]


@dataclass
class IntegrationIDeEnergyRunTimeData:
    """Data for the IDeEnergy integration."""

    # client: Client
    # config_entry_state: IDeEnergyConfigEntryState
    coordinator: IDeEnergyDataCoordinator
    device_info: DeviceInfo
    integration: Integration


def build_entity_unique_id(device_info: DeviceInfo, entity_unique_name: str) -> str:
    cups = dict(device_info["identifiers"])["cups"]
    return slugify(f"{cups}-{entity_unique_name}", separator="-")
