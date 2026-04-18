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

import contextlib
import enum
from collections.abc import Callable
from datetime import datetime, timedelta
from logging import getLogger

import ideenergy
from homeassistant.core import HomeAssistant, dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant_historical_sensor import HistoricalState

from .const import LOCAL_TZ, UPDATE_INTERVAL
from .store import IDeEnergyConfigEntryState

LOGGER = getLogger(__name__)

# Direct reading (accumulated consumption, instant demand)
DIRECT_READING_LAST_SUCCESS_STORED_STATE_KEY = "direct_reading_last_success"
DIRECT_READING_LAST_ATTEMPT_STORED_STATE_KEY = "direct_reading_last_attempt"
DIRECT_READING_LAST_SUCCESS_MAX_AGE = timedelta(hours=6)
DIRECT_READING_LAST_ATTEMPT_MAX_AGE = timedelta(minutes=5)

# Historical consumption
HISTORICAL_CONSUMPTION_LAST_SUCCESS_STORED_STATE_KEY = (
    "historical_consumption_last_success"
)
HISTORICAL_CONSUMPTION_LAST_ATTEMPT_STORED_STATE_KEY = (
    "historical_consumption_last_attempt"
)
HISTORICAL_CONSUMPTION_LAST_SUCCESS_MAX_AGE = timedelta(hours=12)
HISTORICAL_CONSUMPTION_LAST_ATTEMPT_MAX_AGE = timedelta(minutes=5)

# Historical Generation
HISTORICAL_GENERATION_LAST_SUCCESS_STORED_STATE_KEY = (
    "historical_generation_last_success"
)
HISTORICAL_GENERATION_LAST_ATTEMPT_STORED_STATE_KEY = (
    "historical_generation_last_attempt"
)
HISTORICAL_GENERATION_LAST_SUCCESS_MAX_AGE = timedelta(hours=12)
HISTORICAL_GENERATION_LAST_ATTEMPT_MAX_AGE = timedelta(minutes=5)

MEASURE_ACCUMULATED_KEY = "measure_accumulated"
MEASURE_INSTANT_KEY = "measure_instant"

HISTORICAL_PERIOD_LENGHT = timedelta(days=7)


##
# IDeEnergyCoordinatorDataSet: types of data that can be registered in the
# coordinator to be fetched
class IDeEnergyCoordinatorDataSet(enum.Enum):
    DIRECT_READING = enum.auto()
    HISTORICAL_CONSUMPTION = enum.auto()
    HISTORICAL_GENERATION = enum.auto()
    POWER_DEMAND_PEAKS = enum.auto()


##
# IDeEnergyDataCoordinatorData: data stored inside the coordinator
type IDeEnergyDataCoordinatorData = dict[
    IDeEnergyCoordinatorDataSet, list[HistoricalState] | None
]


class IDeEnergyDataCoordinator(DataUpdateCoordinator[IDeEnergyDataCoordinatorData]):
    def __init__(
        self,
        *,
        hass: HomeAssistant,
        client: ideenergy.Client,
        config_entry_state: IDeEnergyConfigEntryState,
        update_interval: timedelta = UPDATE_INTERVAL,
    ):
        name = f"{client} coordinator" if client else "i-de coordinator"
        super().__init__(hass, LOGGER, name=name, update_interval=update_interval)

        # Use dataset names as keys so all counter accesses are consistent.
        self.dataset_counter = {ds.name: 0 for ds in IDeEnergyCoordinatorDataSet}
        self.data = {k: None for k in IDeEnergyCoordinatorDataSet}

        self._client = client
        self._config_entry_state = config_entry_state

    def activate_dataset(self, dataset: IDeEnergyCoordinatorDataSet) -> None:
        self.dataset_counter[dataset.name] += 1
        if self.dataset_counter[dataset.name] == 1:
            LOGGER.info(f"[{self._client}] dataset {dataset.name} enabled")
            # Fix a better place for this call, it's sub-optimal
            self.hass.async_create_task(self.async_request_refresh())

        LOGGER.debug(
            f"[{self._client}] dataset {dataset.name} ref_count incremented"
            + f" (count={self.dataset_counter[dataset.name]})"
        )

    def deactivate_dataset(self, dataset: IDeEnergyCoordinatorDataSet) -> None:
        if self.dataset_counter[dataset.name] > 0:
            self.dataset_counter[dataset.name] -= 1

        LOGGER.debug(
            f"[{self._client}] dataset {dataset.name} ref_count decremented"
            + f" (count={self.dataset_counter[dataset.name]})"
        )
        if self.dataset_counter[dataset.name] == 0:
            LOGGER.info(f"[{self._client}] dataset {dataset.name} disabled")

    async def _async_setup(self) -> None:
        """Set up the coordinator

        This is the place to set up your coordinator,
        or to load data, that only needs to be loaded once.

        This method will be called automatically during
        coordinator.async_config_entry_first_refresh.
        """
        # await self._client.login()
        pass

    async def _async_update_data(self) -> IDeEnergyDataCoordinatorData:
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.

        See: https://developers.home-assistant.io/docs/integration_fetching_data/
        """

        # Raising 'asyncio.TimeoutError' or 'aiohttp.ClientError' are already
        # handled by the data update coordinator.

        # Raising ConfigEntryAuthFailed will cancel future updates
        # and start a config flow with SOURCE_REAUTH (async_step_reauth)

        # Raise UpdateFailed is something were wrong

        active_datasets = [k for k, v in self.dataset_counter.items() if v > 0]
        dsstr = ", ".join(active_datasets)
        LOGGER.debug(f"[{self._client}] datasets enabled: {dsstr}")

        updated_data = {}

        fns = {
            IDeEnergyCoordinatorDataSet.HISTORICAL_CONSUMPTION: self._async_get_historical_consumption,
            IDeEnergyCoordinatorDataSet.HISTORICAL_GENERATION: self._async_get_historical_generation,
            IDeEnergyCoordinatorDataSet.POWER_DEMAND_PEAKS: self._async_get_power_demand_peaks,
            IDeEnergyCoordinatorDataSet.DIRECT_READING: self._async_get_direct_reading_data,
        }
        await self._client.renew_session()
        LOGGER.info(f"[{self._client}] session renewed")

        for ds, fn in fns.items():
            if self.dataset_counter[ds.name] > 0:
                try:
                    updated_data[ds] = await fn()
                except ideenergy.ClientError:
                    LOGGER.exception(
                        f"[{self._client}] error updating dataset '{ds.name}'"
                    )
                    continue
                if updated_data[ds] is None:
                    LOGGER.info(
                        f"[{self._client}] {ds.name}: dataset was not refreshed"
                    )
                else:
                    LOGGER.info(f"[{self._client}] {ds.name}: dataset updated")

        data = self.data | {k: v for k, v in updated_data.items() if v is not None}
        return data

    async def _async_get_direct_reading_data(self) -> dict[str, int | float]:
        if self._state_is_too_recent_with_debug(
            key=DIRECT_READING_LAST_SUCCESS_STORED_STATE_KEY,
            max_age=DIRECT_READING_LAST_SUCCESS_MAX_AGE,
            label="DIRECT_READING success check",
        ):
            return None

        if self._state_is_too_recent_with_debug(
            key=DIRECT_READING_LAST_ATTEMPT_STORED_STATE_KEY,
            max_age=DIRECT_READING_LAST_ATTEMPT_MAX_AGE,
            label="DIRECT_READING attempt check",
        ):
            return None

        async with self._track_state_timestamps(
            success_key=DIRECT_READING_LAST_SUCCESS_STORED_STATE_KEY,
            attempt_key=DIRECT_READING_LAST_ATTEMPT_STORED_STATE_KEY,
        ):
            data = await self._client.get_measure()

        return {
            MEASURE_ACCUMULATED_KEY: data.accumulate,
            MEASURE_INSTANT_KEY: data.instant,
        }

    async def _async_get_historical_consumption(self) -> list[HistoricalState] | None:
        return await self._async_get_historical_generic(
            self._client.get_historical_consumption,
            dataset=IDeEnergyCoordinatorDataSet.HISTORICAL_CONSUMPTION,
            last_success_state_key=HISTORICAL_CONSUMPTION_LAST_SUCCESS_STORED_STATE_KEY,
            last_attempt_state_key=HISTORICAL_CONSUMPTION_LAST_ATTEMPT_STORED_STATE_KEY,
            last_attempt_max_age=HISTORICAL_CONSUMPTION_LAST_ATTEMPT_MAX_AGE,
            last_success_max_age=HISTORICAL_CONSUMPTION_LAST_SUCCESS_MAX_AGE,
        )

    async def _async_get_historical_generation(self) -> list[HistoricalState] | None:
        return await self._async_get_historical_generic(
            self._client.get_historical_generation,
            dataset=IDeEnergyCoordinatorDataSet.HISTORICAL_GENERATION,
            last_success_state_key=HISTORICAL_GENERATION_LAST_SUCCESS_STORED_STATE_KEY,
            last_success_max_age=HISTORICAL_GENERATION_LAST_SUCCESS_MAX_AGE,
            last_attempt_state_key=HISTORICAL_GENERATION_LAST_ATTEMPT_STORED_STATE_KEY,
            last_attempt_max_age=HISTORICAL_GENERATION_LAST_ATTEMPT_MAX_AGE,
        )

    async def _async_get_power_demand_peaks(self) -> list[HistoricalState] | None:
        def historical_power_demand_as_historical_state(
            dai: ideenergy.DemandAtInstant,
        ) -> HistoricalState | None:
            dt = dai.dt.replace(tzinfo=LOCAL_TZ)
            # last_reset = dai.start.replace(tzinfo=LOCAL_TZ)

            try:
                return HistoricalState(
                    state=dai.value / 1000,
                    timestamp=dt_util.as_timestamp(dt),
                    # attributes={"last_reset": last_reset},
                )
            except Exception:
                LOGGER.exception(f"[{self._client}] invalid DemandAtInstant '{dai!r}'")
                return None

        data = await self._client.get_historical_power_demand()
        hist_states = [
            historical_power_demand_as_historical_state(dai) for dai in data.demands
        ]
        hist_states = [hs for hs in hist_states if hs is not None]

        return hist_states

    async def _async_get_historical_generic(
        self,
        afn: Callable,
        *,
        dataset=IDeEnergyCoordinatorDataSet,
        last_attempt_max_age: timedelta,
        last_attempt_state_key: str,
        last_success_max_age: timedelta,
        last_success_state_key: str,
    ) -> list[HistoricalState] | None:
        if self._state_is_too_recent_with_debug(
            key=last_success_state_key,
            max_age=last_success_max_age,
            label=f"{dataset.name} success check",
        ):
            return None

        if self._state_is_too_recent_with_debug(
            key=last_attempt_state_key,
            max_age=last_attempt_max_age,
            label=f"{dataset.name} attempt check",
        ):
            return None

        end = datetime.today()
        start = end - HISTORICAL_PERIOD_LENGHT

        async with self._track_state_timestamps(
            success_key=last_success_state_key,
            attempt_key=last_attempt_state_key,
        ):
            data = await afn(start=start, end=end)

        def as_historical_state(
            pv: ideenergy.PeriodValue,
        ) -> HistoricalState | None:
            dt = pv.end.replace(tzinfo=LOCAL_TZ)
            last_reset = pv.start.replace(tzinfo=LOCAL_TZ)

            try:
                return HistoricalState(
                    state=pv.value / 1000,
                    timestamp=dt_util.as_timestamp(dt),
                    attributes={"last_reset": last_reset},
                )
            except Exception:
                LOGGER.error(f"[{self._client}] invalid PeriodValue '{pv!r}'")
                return None

        hist_states = [as_historical_state(pv) for pv in data.periods]
        hist_states = [hs for hs in hist_states if hs is not None]
        return hist_states

    async def _async_save_state_timestamp(
        self, key: str, timestamp: float | None = None
    ) -> None:
        ts = (
            dt_util.as_timestamp(dt_util.now())
            if timestamp is None
            else float(timestamp)
        )
        self._config_entry_state.data[key] = ts
        await self._config_entry_state.async_save()

    @contextlib.asynccontextmanager
    async def _track_state_timestamps(self, *, success_key: str, attempt_key: str):
        """Context manager to track state timestamps on success/failure."""
        try:
            yield
        except Exception:
            await self._async_save_state_timestamp(attempt_key)
            raise
        else:
            await self._async_save_state_timestamp(success_key)

    def _state_is_too_recent_with_debug(
        self, *, key: str, max_age: timedelta, label: str
    ) -> bool:
        """Check if max_age timedelta has passed since key was last updated.

        Args:
            key: The state key to check
            max_age: The maximum age timedelta
            label: Debug label for logging

        Returns:
            True if not enough time has passed (too recent), False if enough time has passed
        """
        now_ts = dt_util.as_timestamp(dt_util.now())
        now_dt = dt_util.as_local(dt_util.utc_from_timestamp(now_ts))
        max_age_seconds = max_age.total_seconds()

        try:
            prev_ts = float(self._config_entry_state.data[key])
        except TypeError, ValueError, KeyError:
            LOGGER.debug(f"[{self._client}] {label}: no previous timestamp found")
            return False

        elapsed_seconds = now_ts - prev_ts
        if elapsed_seconds < 0:
            prev_dt = dt_util.as_local(dt_util.utc_from_timestamp(prev_ts))
            skew_seconds = abs(elapsed_seconds)
            LOGGER.warning(
                f"[{self._client}] {label}: stored timestamp is in the future "
                + f"(key={key!r}, now={now_dt}, prev={prev_dt}); "
                + f"clock skew: {skew_seconds:.0f}s; allowing refresh"
            )
            return False

        prev_dt = dt_util.as_local(dt_util.utc_from_timestamp(prev_ts))
        is_too_recent = elapsed_seconds <= max_age_seconds

        if is_too_recent:
            fulfillment_dt = prev_dt + max_age
            remaining_seconds = max_age_seconds - elapsed_seconds

            LOGGER.debug(
                f"[{self._client}] {label}: too recent - "
                f"last check: {prev_dt}, "
                f"required interval: {max_age_seconds:.0f}s, "
                f"remaining time: {remaining_seconds:.0f}s "
                f"(will be ready at {fulfillment_dt})"
            )

        return is_too_recent


# def period_item_with_tz_info(item):
#     item.start = item.start.replace(tzinfo=LOCAL_TZ)
#     item.end = item.end.replace(tzinfo=LOCAL_TZ)
#
#     return item


# def dated_item_with_tz_info(item):
#     item.dt = item.dt.replace(tzinfo=LOCAL_TZ)
#
#     return item
