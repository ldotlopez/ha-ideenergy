import asyncio
import random
from datetime import timedelta

from homeassistant.util import dt as dt_util

from . import _LOGGER


class Barrier:
    def __init__(
        self,
        update_window_start_minute,
        update_window_end_minute,
        max_retries,
        max_age,
        delay_min_seconds,
        delay_max_seconds,
    ):
        self._logger = _LOGGER.getChild("barrier")

        self._max_age = max_age
        self._update_window_start_minute = update_window_start_minute
        self._update_window_end_minute = update_window_end_minute
        self._max_retries = max_retries
        self._delay_min_seconds = delay_min_seconds
        self._delay_max_seconds = delay_max_seconds

        zero_dt = dt_util.utc_from_timestamp(0)

        # state
        self._force_next = False
        self._failures = 0
        self._last_success = zero_dt
        self._cooldown = zero_dt

    def force_next(self):
        self._force_next = True

    def sucess(self, now=None):
        now = dt_util.as_utc(now or dt_util.utcnow())

        self._force_next = False
        self._failures = 0
        self._last_success = now

        self._logger.debug("Success registered")

    def fail(self, now=None):
        now = dt_util.as_utc(now or dt_util.utcnow())

        self._failures = self._failures + 1
        self._logger.debug(f"Fail registered ({self._failures}/{self._max_retries})")

        if self._failures >= self._max_retries:
            self._force_next = False
            self._cooldown = now + timedelta(seconds=self._max_age / 2)

            self._logger.debug(
                "Max failures reached, setup cooldown barrier until "
                f"{dt_util.as_local(self._cooldown)}"
            )

    def allowed(self, now=None):
        now = dt_util.as_utc(now or dt_util.utcnow())

        update_window_is_open = (
            self._update_window_start_minute
            <= dt_util.as_local(now).minute
            <= self._update_window_end_minute
        )
        last_success_age = (now - self._last_success).total_seconds()
        min_age = (
            self._update_window_end_minute - self._update_window_start_minute
        ) * 60

        # Check if cooldown has been reached
        if self._failures >= self._max_retries and now >= self._cooldown:
            self._logger.debug("cooldown barrier reached, resetting failures")
            self._failures = 0

        if self._force_next:
            self._logger.debug("Execution allowed: forced")
            return True

        if now < self._cooldown:
            self._logger.debug(
                "Execution denied: cooldown barrier is active "
                f"({dt_util.as_local(self._cooldown)})"
            )
            return False

        if self._failures > 0 and self._failures < self._max_retries:
            self._logger.debug("Execution allowed: retrying")
            return True

        if not update_window_is_open:
            self._logger.debug("Execution denied: update window is closed")
            return False

        if last_success_age <= min_age:
            self._logger.debug(
                "Execution denied: last success is too recent "
                f"({last_success_age} seconds, min: {min_age} seconds)"
            )
            return False

        self._logger.debug("Execution allowed: no blockers")
        return True

    async def delay(self):
        delay = (
            random.randint(self._delay_min_seconds * 10, self._delay_max_seconds * 10)
            / 10
        )
        self._logger.debug(f"Random delay: {delay} seconds")
        await asyncio.sleep(delay)
