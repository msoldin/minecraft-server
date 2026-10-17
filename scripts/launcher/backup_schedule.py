"""Calculate standard five-field cron occurrences in UTC."""

import re
from datetime import UTC, datetime
from typing import Protocol

from croniter import CroniterBadDateError, CroniterError, croniter


class BackupSchedule(Protocol):
    def next_after(self, instant: datetime) -> datetime:
        """Return a timezone-aware occurrence strictly after instant."""
        ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class CronSchedule:
    def __init__(self, expression: str):
        self._validate_standard_syntax(expression)
        if not croniter.is_valid(expression):
            raise ValueError(f"backup.period is not a valid cron expression: {expression!r}")
        self._expression = expression

    @staticmethod
    def _validate_standard_syntax(expression: str) -> None:
        fields = expression.split()
        if len(fields) != 5:
            raise ValueError("backup.period must contain five cron fields (minute hour day month weekday)")
        # Limit extensions without reimplementing cron range/list/step parsing.
        allowed_names = (
            set(), set(), set(),
            set('jan feb mar apr may jun jul aug sep oct nov dec'.split()),
            set('sun mon tue wed thu fri sat'.split()),
        )
        for field, names in zip(fields, allowed_names):
            words = set(re.findall(r'[a-z]+', field.lower()))
            if not re.fullmatch(r'[a-zA-Z0-9*,/\-]+', field) or not words <= names:
                raise ValueError(f"backup.period contains unsupported cron syntax: {field!r}")

    def next_after(self, instant: datetime) -> datetime:
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("Cron scheduling requires a timezone-aware datetime")
        try:
            return self._next_with_day_or(instant.astimezone(UTC))
        except (CroniterError, ValueError, OverflowError) as error:
            raise ValueError(
                f"backup.period has no resolvable next occurrence: {self._expression!r}"
            ) from error

    def _next_with_day_or(self, instant: datetime) -> datetime:
        try:
            return self._next_occurrence(self._expression, instant)
        except CroniterBadDateError:
            fields = self._expression.split()
            if fields[2] == '*' or fields[4] == '*':
                raise
            # croniter 6.2.4 abandons OR evaluation if the day-of-month
            # branch has no date (e.g. Feb 31), before trying weekdays.
            fields[2] = '*'
            return self._next_occurrence(' '.join(fields), instant)

    @staticmethod
    def _next_occurrence(expression: str, instant: datetime) -> datetime:
        return croniter(
            expression, instant, day_or=True, max_years_between_matches=50,
        ).get_next(datetime)
