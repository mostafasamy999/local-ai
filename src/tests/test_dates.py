from datetime import date

import pytest

from app.dates import resolve, week_start

TODAY = date(2026, 11, 12)   # a Thursday


def test_default_is_last_7_days():
    assert resolve(today=TODAY) == ("2026-11-06T00:00:00", "2026-11-12T23:59:59")
    assert resolve("last_7_days", today=TODAY) == ("2026-11-06T00:00:00", "2026-11-12T23:59:59")


def test_today_yesterday():
    assert resolve("today", today=TODAY) == ("2026-11-12T00:00:00", "2026-11-12T23:59:59")
    assert resolve("yesterday", today=TODAY) == ("2026-11-11T00:00:00", "2026-11-11T23:59:59")


def test_week_starts_saturday():
    assert week_start(TODAY) == date(2026, 11, 7)
    assert week_start(date(2026, 11, 7)) == date(2026, 11, 7)
    assert resolve("this_week", today=TODAY) == ("2026-11-07T00:00:00", "2026-11-13T23:59:59")
    assert resolve("last_week", today=TODAY) == ("2026-10-31T00:00:00", "2026-11-06T23:59:59")


def test_this_month_including_december():
    assert resolve("this_month", today=TODAY) == ("2026-11-01T00:00:00", "2026-11-30T23:59:59")
    assert resolve("this_month", today=date(2026, 12, 5)) == ("2026-12-01T00:00:00", "2026-12-31T23:59:59")


def test_current_and_previous_are_open_ended():
    assert resolve("current", today=TODAY) == ("2026-11-12T00:00:00", None)
    # agreed rule "before today 00:00", Q14 fallback: end inclusive, today 00:00 minus 1 s
    assert resolve("previous", today=TODAY) == (None, "2026-11-11T23:59:59")


def test_explicit_dates_win():
    assert resolve(None, "2026-10-01", "2026-10-15", today=TODAY) == ("2026-10-01T00:00:00", "2026-10-15T23:59:59")
    assert resolve(None, "2026-10-01", None, today=TODAY) == ("2026-10-01T00:00:00", None)
    assert resolve(None, None, "2026-10-15", today=TODAY) == (None, "2026-10-15T23:59:59")


def test_unknown_range_raises():
    with pytest.raises(ValueError):
        resolve("next_year", today=TODAY)
