"""Convert Canvas timestamps into the student's local calendar.

Canvas returns UTC. A deadline of ``2026-09-06T06:59:00Z`` is 11:59 PM on Friday
September 5th in Berkeley; printing the UTC date would move it to Saturday and make
"due tomorrow" wrong. Every date the server shows or reasons about goes through here.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

UTC: Final[timezone] = timezone.utc
FALLBACK_TZ: Final[str] = "America/Los_Angeles"


def zone(name: str) -> ZoneInfo:
    """Return a :class:`ZoneInfo`, falling back to Berkeley's zone when unknown."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        logger.warning("Unknown time zone %r; using %s", name, FALLBACK_TZ)
        try:
            return ZoneInfo(FALLBACK_TZ)
        except Exception:  # pragma: no cover - no tzdata at all
            raise


def parse_canvas_dt(value: object) -> datetime | None:
    """Parse a Canvas timestamp into an aware UTC datetime, or ``None``."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text == "None":
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("Skipping unparseable Canvas timestamp: %s", text[:40])
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def now(tz: str) -> datetime:
    """Return the current time in the student's zone."""
    return datetime.now(UTC).astimezone(zone(tz))


def to_local(value: object, tz: str) -> datetime | None:
    """Convert a Canvas timestamp to the student's zone."""
    parsed = parse_canvas_dt(value)
    if parsed is None:
        return None
    return parsed.astimezone(zone(tz))


def human(moment: datetime | None, *, reference: datetime | None = None) -> str:
    """Render a local datetime the way a student would say it.

    ``Fri Sep 5, 11:59 PM`` — no leading zeros, and no ``%-d``/``%-I`` which Windows
    rejects. When *reference* falls in a different year the year is included.
    """
    if moment is None:
        return "no due date"
    hour = moment.hour % 12 or 12
    meridiem = "AM" if moment.hour < 12 else "PM"
    stamp = f"{moment:%a} {moment:%b} {moment.day}, {hour}:{moment:%M} {meridiem}"
    if reference is not None and moment.year != reference.year:
        stamp = f"{moment:%a} {moment:%b} {moment.day}, {moment.year}, {hour}:{moment:%M} {meridiem}"
    return stamp


def human_date(day: date | None) -> str:
    """Render a local date as ``Fri Sep 5``."""
    if day is None:
        return "unknown"
    return f"{day:%a} {day:%b} {day.day}"


def cal_days(target: datetime | None, reference: datetime) -> int | None:
    """Return calendar days between two local datetimes.

    Calendar days, not 24-hour blocks: something due at 11:59 PM tomorrow is ``1``
    whether it is now 8 AM or 11 PM today. Past dates are negative.
    """
    if target is None:
        return None
    return (target.date() - reference.date()).days


def due_in(target: datetime | None, reference: datetime) -> str:
    """Describe how far away a deadline is in words."""
    days = cal_days(target, reference)
    if days is None:
        return "no due date"
    if days < -1:
        return f"{-days} days ago"
    if days == -1:
        return "yesterday"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def week_bounds(reference: datetime) -> tuple[date, date]:
    """Return this week as (Monday, Sunday) in the reference's zone."""
    today = reference.date()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def day_bounds(start: date, end: date, tz: str) -> tuple[datetime, datetime]:
    """Return UTC instants covering local ``start`` 00:00 through local ``end`` 23:59:59."""
    tzinfo = zone(tz)
    begin = datetime.combine(start, datetime.min.time(), tzinfo=tzinfo)
    finish = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=tzinfo)
    return begin.astimezone(UTC), finish.astimezone(UTC)


def iso(moment: datetime | None) -> str | None:
    """Serialize a datetime as ISO-8601, or ``None``."""
    return moment.isoformat() if moment is not None else None
