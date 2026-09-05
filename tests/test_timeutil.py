"""The local-calendar rules that keep deadlines on the right day."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from openmind import timeutil

BERKELEY = "America/Los_Angeles"


def test_utc_midnight_deadline_renders_on_the_previous_local_day():
    """The bug this module exists for: 06:59 UTC Saturday is 11:59 PM Friday in Berkeley."""
    due = timeutil.to_local("2026-09-05T06:59:00Z", BERKELEY)
    assert due is not None
    assert due.strftime("%Y-%m-%d %H:%M") == "2026-09-04 23:59"
    assert timeutil.human(due) == "Fri Sep 4, 11:59 PM"


def test_human_has_no_leading_zeros_and_no_platform_specific_codes():
    """`%-I` is not portable to Windows, so the hour is formatted by hand."""
    moment = datetime(2026, 9, 5, 9, 5, tzinfo=ZoneInfo(BERKELEY))
    assert timeutil.human(moment) == "Sat Sep 5, 9:05 AM"
    assert timeutil.human(moment.replace(hour=0, minute=30)) == "Sat Sep 5, 12:30 AM"
    assert timeutil.human(moment.replace(hour=12, minute=0)) == "Sat Sep 5, 12:00 PM"


def test_human_includes_the_year_when_it_differs_from_the_reference():
    reference = datetime(2026, 12, 20, tzinfo=ZoneInfo(BERKELEY))
    moment = datetime(2027, 1, 5, 23, 59, tzinfo=ZoneInfo(BERKELEY))
    assert "2027" in timeutil.human(moment, reference=reference)


@pytest.mark.parametrize("tz", ["America/Los_Angeles", "America/New_York", "Asia/Almaty"])
def test_calendar_days_count_dates_not_durations(tz: str):
    """Due at 11:59 PM tomorrow is 1 day away whether it is now 8 AM or 11 PM."""
    zone = ZoneInfo(tz)
    for hour in (8, 23):
        reference = datetime(2026, 9, 4, hour, 0, tzinfo=zone)
        target = datetime(2026, 9, 5, 23, 59, tzinfo=zone)
        assert timeutil.cal_days(target, reference) == 1


def test_calendar_days_are_negative_in_the_past():
    zone = ZoneInfo(BERKELEY)
    reference = datetime(2026, 9, 4, 15, 0, tzinfo=zone)
    assert timeutil.cal_days(datetime(2026, 9, 1, 23, 59, tzinfo=zone), reference) == -3
    assert timeutil.due_in(datetime(2026, 9, 3, 23, 59, tzinfo=zone), reference) == "yesterday"
    assert timeutil.due_in(datetime(2026, 9, 4, 1, 0, tzinfo=zone), reference) == "today"


def test_dst_fallback_keeps_the_local_date():
    """US DST ends 2026-11-01; a deadline late on Nov 1 must stay on Nov 1."""
    due = timeutil.to_local("2026-11-02T06:59:00Z", BERKELEY)
    assert due is not None
    assert due.date().isoformat() == "2026-11-01"
    assert due.strftime("%H:%M") == "22:59"

    spring = timeutil.to_local("2026-03-09T06:59:00Z", BERKELEY)
    assert spring is not None
    assert spring.date().isoformat() == "2026-03-08"


def test_week_bounds_run_monday_to_sunday():
    friday = datetime(2026, 9, 4, 15, 0, tzinfo=ZoneInfo(BERKELEY))
    monday, sunday = timeutil.week_bounds(friday)
    assert monday.isoformat() == "2026-08-31"
    assert sunday.isoformat() == "2026-09-06"
    assert monday.weekday() == 0 and sunday.weekday() == 6


def test_unparseable_and_missing_timestamps_return_none():
    for value in ("", "None", "not a date", None, 42, "2026-13-45T00:00:00Z"):
        assert timeutil.parse_canvas_dt(value) is None


def test_naive_timestamps_are_treated_as_utc():
    parsed = timeutil.parse_canvas_dt("2026-09-05T06:59:00")
    assert parsed is not None and parsed.tzinfo is UTC


def test_unknown_zone_falls_back_to_berkeley():
    assert timeutil.zone("Mars/Olympus_Mons").key == "America/Los_Angeles"


def test_day_bounds_cover_the_whole_local_day():
    from datetime import date

    start, end = timeutil.day_bounds(date(2026, 9, 4), date(2026, 9, 4), BERKELEY)
    assert start.isoformat() == "2026-09-04T07:00:00+00:00"
    assert end.isoformat() == "2026-09-05T07:00:00+00:00"


@given(
    st.datetimes(
        min_value=datetime(2020, 1, 1), max_value=datetime(2035, 12, 31)
    ).map(lambda d: d.replace(tzinfo=UTC)),
    st.sampled_from(["America/Los_Angeles", "America/New_York", "Europe/Berlin", "Asia/Almaty", "UTC"]),
)
def test_parse_and_localise_round_trip(moment: datetime, tz: str):
    """Converting to local and back must land on the same instant."""
    stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    local = timeutil.to_local(stamp, tz)
    assert local is not None
    assert local.astimezone(UTC).replace(microsecond=0) == moment.replace(microsecond=0)


@given(st.integers(min_value=-400, max_value=400))
def test_calendar_days_matches_date_arithmetic(offset: int):
    zone = ZoneInfo(BERKELEY)
    reference = datetime(2026, 6, 15, 13, 0, tzinfo=zone)
    target = reference + timedelta(days=offset)
    assert timeutil.cal_days(target, reference) == (target.date() - reference.date()).days
