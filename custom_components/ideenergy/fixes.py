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
from homeassistant.components.recorder import db_schema, statistics
from homeassistant.core import HomeAssistant, dt_util
from homeassistant_historical_sensor import recorderutil

_LOGGER = logging.getLogger(__name__)


async def async_fix_statistics(
    hass: HomeAssistant, statistic_metadata: statistics.StatisticMetaData
) -> None:
    def timestamp_as_local(timestamp):
        return dt_util.as_local(dt_util.utc_from_timestamp(timestamp))

    def fn():
        fixes_applied = False

        statistic_id = statistic_metadata["statistic_id"]
        statistic_metadata_has_mean = statistic_metadata.get("has_mean", False)
        statistic_metadata_has_sum = statistic_metadata.get("has_sum", False)

        with recorderutil.hass_recorder_session(hass) as session:
            #
            # Check and fix current metadata
            #

            current_metadata = session.execute(
                sa.select(db_schema.StatisticsMeta).where(
                    db_schema.StatisticsMeta.statistic_id == statistic_id
                )
            ).scalar()

            if current_metadata is None:
                _LOGGER.debug(f"{statistic_id}: no statistics found, nothing to fix")
                return

            statistics_base_stmt = sa.select(db_schema.Statistics).where(
                db_schema.Statistics.metadata_id == current_metadata.id
            )

            metadata_needs_fixes = (
                current_metadata.has_mean != statistic_metadata_has_mean
            ) or (current_metadata.has_sum != statistic_metadata_has_sum)

            if metadata_needs_fixes:
                _LOGGER.debug(
                    f"{statistic_id}: statistic metadata is outdated."
                    f" has_mean:{current_metadata.has_mean}→{statistic_metadata_has_mean}"
                    f" has_sum:{current_metadata.has_sum}→{statistic_metadata_has_sum}"
                )
                current_metadata.has_mean = statistic_metadata_has_mean
                current_metadata.has_sum = statistic_metadata_has_sum
                session.add(current_metadata)
                session.commit()
                fixes_applied = True

            #
            # Check for broken points and decreasings
            #
            broken_point = None

            prev_sum = 0
            statistics_iter_stmt = statistics_base_stmt.order_by(
                db_schema.Statistics.start_ts.asc()
            )

            for statistic in session.execute(statistics_iter_stmt).scalars():
                is_broken = False
                local_start_dt = timestamp_as_local(statistic.start_ts)

                # Check for NULL mean
                if statistic_metadata_has_mean and statistic.mean is None:
                    is_broken = True
                    _LOGGER.debug(
                        f"{statistic_id}: mean value at {local_start_dt} is NULL"
                    )

                # Check for NULL sum
                if statistic_metadata_has_sum and statistic.sum is None:
                    is_broken = True
                    _LOGGER.debug(
                        f"{statistic_id}: sum value at {local_start_dt} is NULL"
                    )

                # Check for decreasing values in sum
                if statistic_metadata_has_sum and statistic.sum:
                    if statistic.sum < prev_sum:
                        is_broken = True
                        _LOGGER.debug(
                            f"{statistic_id}: "
                            + f"decreasing sum at {local_start_dt} "
                            + f"{statistic.sum} < {prev_sum} ({statistic!r})"
                        )
                    else:
                        prev_sum = statistic.sum

                # Found anything broken?
                if is_broken:
                    broken_point = statistic.start_ts
                    break

            #
            # Check for broken points (search only for NULLs)
            #

            # clauses_for_additional_or_ = [db_schema.Statistics.state == None]
            # if statistic_metadata_has_mean:
            #     clauses_for_additional_or_.append(db_schema.Statistics.mean == None)
            # if statistic_metadata_has_sum:
            #     clauses_for_additional_or_.append(db_schema.Statistics.sum == None)

            # find_broken_point_stmt = (
            #     sa.select(sa.func.min(db_schema.Statistics.start_ts))
            #     .where(db_schema.Statistics.metadata_id == current_metadata.id)
            #     .where(sa.or_(*clauses_for_additional_or_))
            # )

            # broken_point = session.execute(find_broken_point_stmt).scalar()

            #
            # Delete everything after broken point
            #
            if broken_point:
                invalid_statistics_stmt = statistics_base_stmt.where(
                    db_schema.Statistics.start_ts >= broken_point
                )
                invalid_statistics = (
                    session.execute(invalid_statistics_stmt).scalars().fetchall()
                )

                for x in invalid_statistics:
                    session.delete(x)

                session.commit()
                fixes_applied = True

                _LOGGER.debug(
                    f"{statistic_id}: "
                    f"found broken point at {timestamp_as_local(broken_point)},"
                    f" deleted {len(invalid_statistics)} statistics"
                )

            #
            # Delete additional statistics
            #

            clauses_for_additional_or_ = [db_schema.Statistics.state == None]

            if statistic_metadata_has_mean:
                clauses_for_additional_or_.append(db_schema.Statistics.mean == None)

            if statistic_metadata_has_sum:
                clauses_for_additional_or_.append(db_schema.Statistics.sum == None)

            invalid_statistics_stmt = statistics_base_stmt.where(
                sa.or_(*clauses_for_additional_or_)
            )

            invalid_statistics = (
                session.execute(invalid_statistics_stmt).scalars().fetchall()
            )

            if invalid_statistics:
                for o in invalid_statistics:
                    session.delete(o)
                session.commit()
                fixes_applied = True

                _LOGGER.debug(
                    f"{statistic_id}: "
                    f"deleted {len(invalid_statistics)} statistics with invalid attributes"
                )

            if not fixes_applied:
                _LOGGER.debug(f"{statistic_id}: no problems found")

            #
            # Recalculate
            #

            # if not broken_point and not force_recalculate:
            #     return

            # if broken_point:
            #     _LOGGER.debug(
            #         f"{statistic_id}: found broken statistics since"
            #         f" {timestamp_as_local(broken_point.start_ts)},"
            #         f" recalculating everything from there"
            #     )

            #
            # Recalculate all stats
            #

            # accumulated = 0
            # for statistic in session.execute(
            #     sa.select(db_schema.Statistics)
            #     .where(db_schema.Statistics.metadata_id == statistic_id)
            #     .order_by(db_schema.Statistics.start_ts.asc)
            # ):
            #     accumulated = accumulated + statistic.state

            #     # fmt: off
            #     statistic.mean = statistic.state if statistic_metadata_has_mean else None
            #     statistic.sum = accumulated if statistic_metadata_has_sum else None
            #     statistic.min = None
            #     statistic.max = None
            #     # fmt: on

            #     session.add(statistic)
            #     _LOGGER.debug(
            #         f"{statistic_id}: "
            #         f"update {statistic.id} {timestamp_as_local(statistic.start_ts)} "
            #         f"value={statistic.value}\tsum={statistic.sum}"
            #     )
            # session.commit()

    return await recorder.get_instance(hass).async_add_executor_job(fn)
