"""dateRange / fromDate / toDate -> fromDateTime / endDateTime (yyyy-MM-ddTHH:mm:ss).

Rules from specs/001-activities (api-contracts.md §4, user-scenarios-rules.md SC-10):
- Default (nothing given): 6 days ago 00:00 -> today 23:59:59.
- current:  today 00:00 -> open (None).
- previous: open -> before today 00:00. Q14 (inclusive end?) is unanswered, so we use the documented
            fallback: end inclusive, today 00:00 minus 1 s = yesterday 23:59:59.
- A week starts on Saturday (the app's week days run 1 = Saturday ... 7 = Friday).
"""
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

FMT = "%Y-%m-%dT%H:%M:%S"
Range = Tuple[Optional[str], Optional[str]]


def _start(d: date) -> str:
    return datetime(d.year, d.month, d.day, 0, 0, 0).strftime(FMT)


def _end(d: date) -> str:
    return datetime(d.year, d.month, d.day, 23, 59, 59).strftime(FMT)


def week_start(d: date) -> date:
    """The Saturday on or before d. Python weekday(): Mon=0 ... Sat=5, Sun=6."""
    return d - timedelta(days=(d.weekday() - 5) % 7)


def resolve(date_range: Optional[str] = None, from_date: Optional[str] = None,
            to_date: Optional[str] = None, today: Optional[date] = None) -> Range:
    """Return (fromDateTime, endDateTime). Either side may be None (open)."""
    today = today or date.today()

    if from_date or to_date:
        start = _start(date.fromisoformat(from_date)) if from_date else None
        end = _end(date.fromisoformat(to_date)) if to_date else None
        return start, end

    if date_range is None or date_range == "last_7_days":
        return _start(today - timedelta(days=6)), _end(today)
    if date_range == "today":
        return _start(today), _end(today)
    if date_range == "yesterday":
        y = today - timedelta(days=1)
        return _start(y), _end(y)
    if date_range == "this_week":
        s = week_start(today)
        return _start(s), _end(s + timedelta(days=6))
    if date_range == "last_week":
        s = week_start(today) - timedelta(days=7)
        return _start(s), _end(s + timedelta(days=6))
    if date_range == "this_month":
        first = today.replace(day=1)
        nxt = first.replace(year=first.year + 1, month=1) if first.month == 12 else first.replace(month=first.month + 1)
        return _start(first), _end(nxt - timedelta(days=1))
    if date_range == "current":
        return _start(today), None
    if date_range == "previous":
        return None, _end(today - timedelta(days=1))
    raise ValueError("unknown dateRange %r" % date_range)
