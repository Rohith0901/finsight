"""Date helpers. All day boundaries are Indian Standard Time (UTC+05:30, no DST)."""

from __future__ import annotations

import calendar as _cal
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def today_ist() -> date:
    return datetime.now(IST).date()


def local_date(ts: datetime) -> date:
    return (ts.replace(tzinfo=IST) if ts.tzinfo is None else ts.astimezone(IST)).date()


def days_in_month(d: date) -> int:
    return _cal.monthrange(d.year, d.month)[1]


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=days_in_month(d))


def days_left_including(d: date) -> int:
    """Days from d to the end of its month, counting d itself."""
    return (month_end(d) - d).days + 1


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def add_months(d: date, months: int, anchor_day: int | None = None) -> date:
    """Shift by whole months, clamping to the month's length (31 Jan + 1 = 28/29 Feb)."""
    index = d.year * 12 + (d.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    day = anchor_day if anchor_day is not None else d.day
    return date(year, month, min(day, _cal.monthrange(year, month)[1]))


def previous_month(d: date) -> date:
    """First day of the month before d's month."""
    return add_months(month_start(d), -1)
