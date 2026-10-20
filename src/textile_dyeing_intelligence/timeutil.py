"""Timestamp and date handling.

Timestamp policy (documented in the README): operator-facing event times are stored as
**local time without a UTC offset**, formatted ``YYYY-MM-DDTHH:MM:SS``. Dates are stored as
``YYYY-MM-DD``. Fixed-width ISO text sorts chronologically, which the reports rely on.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

_now_func: Callable[[], datetime] = datetime.now


def now() -> datetime:
    return _now_func()


def now_iso() -> str:
    """Record-creation timestamp in storage format."""
    return now().replace(microsecond=0).isoformat(timespec="seconds")


def parse_timestamp(value: object) -> str:
    """Validate a date-and-time value and return it in storage format.

    Raises ``ValueError`` with a message that completes the sentence "<Label> ...".
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("is required.")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise ValueError("must be a valid date and time, for example 2026-03-05 14:30.") from None
        if len(text) <= 10:
            raise ValueError("must include a time, for example 2026-03-05 14:30.")
    else:
        raise ValueError("must be a valid date and time, for example 2026-03-05 14:30.")
    if parsed.tzinfo is not None:
        raise ValueError("must be local time without a UTC offset.")
    return parsed.replace(microsecond=0).isoformat(timespec="seconds")


def parse_date(value: object) -> str:
    """Validate a calendar date and return ``YYYY-MM-DD``."""
    if isinstance(value, datetime):
        raise ValueError("must be a date without a time, for example 2026-03-05.")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("is required.")
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise ValueError("must be a valid date, for example 2026-03-05.") from None
    raise ValueError("must be a valid date, for example 2026-03-05.")
