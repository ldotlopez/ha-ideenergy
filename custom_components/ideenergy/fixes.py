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


import logging

import sqlalchemy as sa
from homeassistant.components import recorder
from homeassistant.components.recorder import db_schema
from homeassistant.core import HomeAssistant
from homeassistant_historical_sensor import recorderutil

_LOGGER = logging.getLogger(__name__)


async def hass_fix_statistics(hass: HomeAssistant, *, statistic_id: str):
    """
    v1.0.4 -> 2.0.x ()
    Upgrade failed to manage a migration for statistics.

    """

    def fn():
        with recorderutil.hass_recorder_session(hass) as session:
            statistics_meta = session.execute(
                sa.select(db_schema.StatisticsMeta).where(
                    db_schema.StatisticsMeta.statistic_id == statistic_id
                )
            ).scalar()

            if statistics_meta is None:
                _LOGGER.debug(f"{statistic_id}: no statistics")
                return

            #
            # Fix statistics_meta
            #

            if statistics_meta.has_sum is not True:
                _LOGGER.debug(
                    f"{statistic_id}: has_sum is {statistics_meta.has_sum}, "
                    "should be True"
                )
                # statistics_meta.has_sum = True

            if statistics_meta.has_mean is not True:
                _LOGGER.debug(
                    f"{statistic_id}: has_mean is {statistics_meta.has_mean}, "
                    "should be True"
                )
                # statistics_meta.has_mean = True

            # session.add(statistics_meta)
            # session.commit()

            #
            # Delete invalid statistics
            #
            invalid_statistics_stmt = (
                sa.select(db_schema.Statistics)
                .where(db_schema.Statistics.metadata_id == statistics_meta.id)
                .where(
                    sa.or_(
                        db_schema.Statistics.sum == None,  # noqa: E711
                        db_schema.Statistics.mean == None,  # noqa: E711
                        db_schema.Statistics.state == None,  # noqa: E711
                    )
                )
            )
            invalid_statistics = (
                session.execute(invalid_statistics_stmt).scalars().fetchall()
            )

            _LOGGER.debug(
                f"{statistic_id}: found {len(invalid_statistics)} invalid stats"
            )

            # for o in invalid_statistics:
            #     session.delete(o)
            # session.commit()

    return await recorder.get_instance(hass).async_add_executor_job(fn)
