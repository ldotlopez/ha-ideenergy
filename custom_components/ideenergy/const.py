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


from datetime import timedelta

DOMAIN = "ideenergy"

CONF_CONTRACT = "contract"

MEASURE_MAX_AGE = 60 * 50  # Fifty minutes
MAX_RETRIES = 3
MIN_SCAN_INTERVAL = 60
UPDATE_WINDOW_START_MINUTE = 50
UPDATE_WINDOW_END_MINUTE = 59
API_USER_SESSION_TIMEOUT = 60


DATA_ATTR_MEASURE_ACCUMULATED = "measure_accumulated"
DATA_ATTR_MEASURE_INSTANT = "measure_instant"
DATA_ATTR_HISTORICAL_CONSUMPTION = "historical_consumption"
DATA_ATTR_HISTORICAL_GENERATION = "historical_generation"
DATA_ATTR_HISTORICAL_POWER_DEMAND = "historical_power_demand"

HISTORICAL_PERIOD_LENGHT = timedelta(days=7)
CONFIG_ENTRY_VERSION = 3
