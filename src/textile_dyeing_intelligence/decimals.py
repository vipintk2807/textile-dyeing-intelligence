"""Exact decimal handling. Quantities are stored as canonical decimal text.

Binary floating point is never used for authoritative quantities or variances.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .config import MAX_DECIMAL_PLACES, MAX_INTEGER_DIGITS

_NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d+)?|\.\d+)$")


def parse_decimal(
    value: object,
    *,
    allow_zero: bool = True,
    allow_negative: bool = False,
) -> Decimal:
    """Parse user input into a ``Decimal``.

    Raises ``ValueError`` with a message that completes "<Label> ...".
    Floats and booleans are rejected on purpose (binary floating point is inexact).
    """
    if isinstance(value, (bool, float)):
        raise ValueError("must be entered as a decimal number such as 12 or 12.5.")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("must be a finite number.")
        text = format(value, "f")
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise ValueError("must be a valid number such as 12 or 12.5.")

    if text == "":
        raise ValueError("is required.")
    if not _NUMBER_RE.match(text):
        raise ValueError(
            "must be a plain number such as 12 or 12.5 (use a period for decimals; no commas, exponents or units)."
        )

    unsigned = text.lstrip("+-")
    int_part, _, frac_part = unsigned.partition(".")
    if len(int_part.lstrip("0")) > MAX_INTEGER_DIGITS:
        raise ValueError(f"has too many digits (at most {MAX_INTEGER_DIGITS} before the point).")
    if len(frac_part) > MAX_DECIMAL_PLACES:
        raise ValueError(f"has too many decimal places (at most {MAX_DECIMAL_PLACES}).")

    try:
        number = Decimal(text)
    except InvalidOperation:  # pragma: no cover - guarded by the regex
        raise ValueError("must be a valid number such as 12 or 12.5.") from None

    if number == 0:
        number = abs(number)  # normalise negative zero
        if not allow_zero:
            raise ValueError("must be greater than zero.")
    elif number < 0 and not allow_negative:
        raise ValueError("cannot be negative.")
    return number


def canonical_text(number: Decimal) -> str:
    """Plain (non-exponent) text for storage; preserves entered precision."""
    return format(number, "f")


def to_decimal(text: str | None) -> Decimal | None:
    """Convert stored decimal text back to ``Decimal`` (``None`` stays ``None``)."""
    if text is None:
        return None
    return Decimal(text)


def round_for_display(number: Decimal, places: int = 2) -> Decimal:
    """Round half-up for display only. Never use the result for further calculation."""
    quantum = Decimal(1).scaleb(-places)
    return number.quantize(quantum, rounding=ROUND_HALF_UP)


def format_decimal(number: Decimal | None, places: int | None = None, *, signed: bool = False) -> str:
    """Format for display. ``None`` yields an empty string (callers choose the label)."""
    if number is None:
        return ""
    shown = round_for_display(number, places) if places is not None else number
    text = format(shown, "f")
    if signed and shown > 0:
        text = "+" + text
    return text
