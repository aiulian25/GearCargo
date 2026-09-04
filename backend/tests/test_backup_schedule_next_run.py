"""Tests for BackupSchedule.calculate_next_run (R4-38 coverage, R4-22 bug).

The quarterly branch had two defects: `month += 3 - 3` is a no-op, and the
`qm > month` search is strictly greater — so a schedule sitting in a quarter
month whose day has NOT yet passed skipped a whole quarter. A schedule set for
the 15th, checked on 3 October, reported January instead of 15 October.

`next_run_at` is informational (it feeds `to_dict`); the scheduler matches
day/hour itself, so this misled the UI rather than skipping a backup.
"""

import calendar
from datetime import datetime, timezone

import pytest

from app.models.backup import BackupSchedule


class _FrozenDatetime(datetime):
    """datetime subclass whose now() is pinned — calculate_next_run calls
    datetime.now(timezone.utc) directly."""

    frozen = None

    @classmethod
    def now(cls, tz=None):
        return cls.frozen


@pytest.fixture
def frozen_now(monkeypatch):
    def _freeze(moment):
        _FrozenDatetime.frozen = moment
        monkeypatch.setattr('app.models.backup.datetime', _FrozenDatetime)
    return _freeze


def _schedule(frequency, **kwargs):
    schedule = BackupSchedule(user_id=1, frequency=frequency, hour=3)
    for name, value in kwargs.items():
        setattr(schedule, name, value)
    return schedule


# --- weekly ----------------------------------------------------------------

@pytest.mark.parametrize('today, day_of_week, expected', [
    # 2026-09-03 is a Thursday (weekday 3).
    (datetime(2026, 9, 3, 10, tzinfo=timezone.utc), 4, datetime(2026, 9, 4, 3)),   # tomorrow
    (datetime(2026, 9, 3, 10, tzinfo=timezone.utc), 0, datetime(2026, 9, 7, 3)),   # next Monday
    # Target day is today -> next week, not today (the hour may already be past).
    (datetime(2026, 9, 3, 10, tzinfo=timezone.utc), 3, datetime(2026, 9, 10, 3)),
])
def test_weekly_next_run(frozen_now, today, day_of_week, expected):
    frozen_now(today)
    schedule = _schedule('weekly', day_of_week=day_of_week)

    assert schedule.calculate_next_run() == expected


# --- monthly ---------------------------------------------------------------

@pytest.mark.parametrize('today, day_of_month, expected', [
    (datetime(2026, 9, 3, 10, tzinfo=timezone.utc), 15, datetime(2026, 9, 15, 3)),
    (datetime(2026, 9, 20, 10, tzinfo=timezone.utc), 15, datetime(2026, 10, 15, 3)),
    # Day already reached today -> next month.
    (datetime(2026, 9, 15, 10, tzinfo=timezone.utc), 15, datetime(2026, 10, 15, 3)),
    # December rolls the year over.
    (datetime(2026, 12, 20, 10, tzinfo=timezone.utc), 15, datetime(2027, 1, 15, 3)),
    # The 31st is clamped to the length of the target month.
    (datetime(2026, 1, 31, 10, tzinfo=timezone.utc), 31, datetime(2026, 2, 28, 3)),
])
def test_monthly_next_run(frozen_now, today, day_of_month, expected):
    frozen_now(today)
    schedule = _schedule('monthly', day_of_month=day_of_month)

    assert schedule.calculate_next_run() == expected


# --- quarterly (R4-22) -----------------------------------------------------

@pytest.mark.parametrize('today, day_of_month, expected', [
    # Sitting IN a quarter month, day not yet passed -> THIS month.
    (datetime(2026, 10, 3, 10, tzinfo=timezone.utc), 15, datetime(2026, 10, 15, 3)),
    (datetime(2026, 1, 1, 10, tzinfo=timezone.utc), 15, datetime(2026, 1, 15, 3)),
    # Day already reached -> the next quarter month.
    (datetime(2026, 10, 20, 10, tzinfo=timezone.utc), 15, datetime(2027, 1, 15, 3)),
    (datetime(2026, 1, 15, 10, tzinfo=timezone.utc), 15, datetime(2026, 4, 15, 3)),
    # Between quarter months -> the next one.
    (datetime(2026, 9, 3, 10, tzinfo=timezone.utc), 15, datetime(2026, 10, 15, 3)),
    (datetime(2026, 2, 20, 10, tzinfo=timezone.utc), 15, datetime(2026, 4, 15, 3)),
    # Past the last quarter month of the year -> January, year rolled over.
    (datetime(2026, 11, 20, 10, tzinfo=timezone.utc), 15, datetime(2027, 1, 15, 3)),
    (datetime(2026, 12, 1, 10, tzinfo=timezone.utc), 15, datetime(2027, 1, 15, 3)),
])
def test_quarterly_next_run(frozen_now, today, day_of_month, expected):
    frozen_now(today)
    schedule = _schedule('quarterly', day_of_month=day_of_month)

    assert schedule.calculate_next_run() == expected


def test_quarterly_never_skips_more_than_one_quarter(frozen_now):
    """The old `qm > month` search could land two quarters out."""
    for month in range(1, 13):
        frozen_now(datetime(2026, month, 3, 10, tzinfo=timezone.utc))
        schedule = _schedule('quarterly', day_of_month=15)

        next_run = schedule.calculate_next_run()
        months_ahead = (next_run.year - 2026) * 12 + next_run.month - month

        assert 0 <= months_ahead <= 3, f'from month {month} it jumped {months_ahead} months'
        assert next_run.month in (1, 4, 7, 10)


def test_quarterly_clamps_the_day_to_the_target_month(frozen_now):
    frozen_now(datetime(2026, 12, 20, 10, tzinfo=timezone.utc))
    schedule = _schedule('quarterly', day_of_month=31)

    next_run = schedule.calculate_next_run()

    assert next_run == datetime(2027, 1, 31, 3)
    assert next_run.day <= calendar.monthrange(next_run.year, next_run.month)[1]


def test_calculate_next_run_persists_on_the_row(frozen_now):
    frozen_now(datetime(2026, 9, 3, 10, tzinfo=timezone.utc))
    schedule = _schedule('monthly', day_of_month=15)

    returned = schedule.calculate_next_run()

    assert schedule.next_run_at == returned
