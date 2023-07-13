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


import enum
import functools
import logging
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import dt_util

_LOGGER = logging.getLogger(__name__)


ATTR_DELAY_INTERVAL = "delay_interval"
ATTR_MAX_AGE = "max_age"
ATTR_MAX_RETRIES = "max_retries"
ATTR_UPDATE_WINDOW_INTERVAL = "update_window_interval"
ATTR_COOLDOWN = "cooldown"
ATTR_FORCED = "forced"
ATTR_LAST_SUCCESS = "last_success"
ATTR_STATE = "state"
ATTR_RETRY = "retry"
ATTR_ALLOWED_WINDOW_MINUTES = "allowed_window_minutes"

DEFAULT_MAX_RETRIES = 3


def check_tzinfo(
    param: str | int,
    default_tzinfo: timezone = timezone.utc,
    optional: bool = False,
):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if isinstance(param, int):
                dt = args[param]
            elif isinstance(param, str):
                dt = kwargs.get(param)
            else:
                raise TypeError("Invalid argument for decorator")

            if dt is None:
                if optional:
                    return fn(*args, **kwargs)
                else:
                    raise TypeError(f"{param} is missing")

            if not isinstance(dt, datetime):
                raise TypeError(f"{param} must be a datetime object")

            if dt.tzinfo is None and default_tzinfo is None:
                raise ValueError(f"{param} lacks tzinfo")

            if default_tzinfo is not None:
                dt = dt.replace(tzinfo=default_tzinfo)

                if isinstance(param, int):
                    args[param] = dt
                if isinstance(param, str):
                    kwargs[param] = dt

            return fn(*args, **kwargs)

        return wrapper

    return decorator


class Barrier:
    @abstractmethod
    def check(self, **kwargs: Any) -> None:
        raise NotImplementedError()

    @abstractmethod
    def success(self, **kwargs: Any) -> None:
        raise NotImplementedError()

    @abstractmethod
    def fail(self, **kwargs: Any) -> None:
        raise NotImplementedError()

    @abstractmethod
    def dump(self) -> dict[str, Any]:
        return {}


class BarrierException(Exception):
    pass


class BarrierDeniedError(BarrierException):
    def __init__(self, code: Any, reason: str):
        self.reason = reason
        self.code = code


class TimeDeltaBarrier(Barrier):
    @check_tzinfo("last_success", optional=True)
    def __init__(
        self,
        delta: timedelta,
        last_success: datetime | None = None,
    ):
        self._delta = delta
        self._last_success = last_success or dt_util.utc_from_timestamp(0)

    @check_tzinfo("now", optional=True)
    def check(self, now: datetime | None = None) -> None:
        now = now or self.utcnow()

        diff = now - self._last_success
        if diff < self._delta:
            raise BarrierDeniedError(
                code=TimeDeltaBarrierDenyError.NO_MAX_AGE,
                reason=f"no max_age reached ({diff} <= {self._delta})",
            )

    @check_tzinfo("now", optional=True)
    def success(self, now: datetime | None = None) -> None:
        now = now or self.utcnow()
        self._last_success = now

    @check_tzinfo("now", optional=True)
    def fail(self, now: datetime | None = None) -> None:
        pass

    def utcnow(self) -> datetime:
        return dt_util.utcnow()

    @property
    def delta(self) -> timedelta:
        return self._delta

    @property
    def last_success(self) -> datetime:
        return self._last_success

    def dump(self) -> dict[str, Any]:
        return {ATTR_MAX_AGE: self.delta, ATTR_LAST_SUCCESS: self.last_success}


class TimeDeltaBarrierDenyError(enum.Enum):
    NO_MAX_AGE = enum.auto()


class RetryableBarrier:
    def __init__(self, max_retries: int = DEFAULT_MAX_RETRIES):
        self._max_retries = max_retries

    @property
    def attributes(self) -> dict[str, Any]:
        return {ATTR_MAX_RETRIES: self._max_retries}

    @property
    def max_retries(self) -> int:
        return self._max_retries


class TimeWindowBarrier(Barrier):
    def __init__(
        self,
        allowed_window_minutes: tuple[int, int],
        max_retries: int,
        max_age: timedelta,
    ):
        self._max_age = max_age
        self._allowed_window_minutes = allowed_window_minutes
        self._max_retries = max_retries

        zero_dt = dt_util.utc_from_timestamp(0)

        # state
        self._force_next = False
        self._failures = 0
        self._last_success = zero_dt
        self._cooldown = zero_dt

    def utcnow(self) -> datetime:
        return dt_util.utcnow()

    def dump(self) -> dict[str, Any]:
        ret = {
            # Configuration
            ATTR_MAX_AGE: self._max_age,
            ATTR_MAX_RETRIES: self._max_retries,
            ATTR_ALLOWED_WINDOW_MINUTES: self._allowed_window_minutes,
            # Internal state
            ATTR_COOLDOWN: self._cooldown,
            ATTR_FORCED: self._force_next,
            ATTR_LAST_SUCCESS: self._last_success,
            ATTR_RETRY: self._failures,
        }

        return ret

    @check_tzinfo("now", optional=True)
    def check(self, now: datetime | None = None) -> None:
        """
        Checks (in order), important for testing
        - forced
        - cooldown
        - retrying
        - update window
        - no delta
        """
        now = now or self.utcnow()

        update_window_is_open = (
            self._allowed_window_minutes[0]
            <= dt_util.as_local(now).minute
            <= self._allowed_window_minutes[1]
        )
        last_success_age = (now - self._last_success).total_seconds()
        min_age = (
            self._allowed_window_minutes[1] - self._allowed_window_minutes[0]
        ) * 60

        # Check if cooldown has been reached
        if self._failures >= self._max_retries and now >= self._cooldown:
            _LOGGER.debug("cooldown barrier reached, resetting failures")
            self._failures = 0

        if self._force_next:
            _LOGGER.debug("forced flag is set")
            return

        if now < self._cooldown:
            cooldown_until = dt_util.as_local(self._cooldown)
            raise BarrierDeniedError(
                code=TimeWindowBarrierDenyError.COOLDOWN,
                reason=f"barrier is in cooldown state until {cooldown_until}",
            )

        if self._failures > 0 and self._failures < self._max_retries:
            _LOGGER.debug("barrier is in retrying state")
            return

        if not update_window_is_open:
            raise BarrierDeniedError(
                code=TimeWindowBarrierDenyError.UPDATE_WINDOW_CLOSED,
                reason="update window is closed",
            )

        if last_success_age <= min_age:
            reason = (
                "last success is too recent "
                f"({last_success_age} seconds, min: {min_age} seconds)"
            )
            raise BarrierDeniedError(
                code=TimeWindowBarrierDenyError.NO_DELTA, reason=reason
            )

    def force_next(self) -> None:
        self._force_next = True

    @check_tzinfo("now", optional=True)
    def success(self, now: datetime | None = None) -> None:
        now = now or self.utcnow()

        self._force_next = False
        self._failures = 0
        self._last_success = now

        _LOGGER.debug("success registered")

    @check_tzinfo("now", optional=True)
    def fail(self, now: datetime | None = None) -> None:
        now = now or self.utcnow()

        self._failures = self._failures + 1
        _LOGGER.debug(f"fail registered ({self._failures}/{self._max_retries})")

        if self._failures >= self._max_retries:
            self._force_next = False
            self._cooldown = now + (self._max_age / 2)

            cooldown_until = dt_util.as_local(self._cooldown)
            _LOGGER.debug(
                f"max failures reached, setup cooldown barrier until {cooldown_until}"
            )


class TimeWindowBarrierDenyError(enum.Enum):
    UPDATE_WINDOW_CLOSED = enum.auto()
    COOLDOWN = enum.auto()
    NO_DELTA = enum.auto()


class NoopBarrier(Barrier):
    def check(self, **kwargs) -> None:
        pass

    def success(self):
        pass

    def fail(self):
        pass

    def dump(self) -> dict[str, Any]:
        return {}
