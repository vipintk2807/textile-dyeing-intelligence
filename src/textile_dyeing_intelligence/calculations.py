"""Pure domain calculations (no database, no Streamlit).

Definitions (also documented in the README):

* Consumption variance:  V = A - P,   V% = (A - P) / P * 100  (unavailable when P = 0).
* Batch-based rate:      rate% = numerator / denominator * 100 (unavailable when the
  denominator is 0). Numerator and denominator count *distinct batches*.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

VarianceStatus = Literal["ok", "incomplete", "incompatible"]


def normalise_unit(unit: str | None) -> str:
    """Unit comparison key. No unit conversion is attempted (kg and g are incompatible)."""
    return (unit or "").strip().casefold()


@dataclass(frozen=True)
class Variance:
    status: VarianceStatus
    absolute: Decimal | None
    percent: Decimal | None
    unit: str | None
    message: str


def compute_variance(
    planned: Decimal | None,
    actual: Decimal | None,
    *,
    planned_unit: str | None,
    actual_unit: str | None,
    planned_basis: str | None = None,
    actual_basis: str | None = None,
) -> Variance:
    """Compare a planned and an actual quantity of the *same material*.

    Missing data is never converted to zero. Different units or measurement bases are
    reported as incompatible rather than compared.
    """
    if planned is None or actual is None:
        missing = "planned" if planned is None else "actual"
        return Variance(
            "incomplete",
            None,
            None,
            None,
            f"Comparison unavailable: the {missing} quantity is not recorded.",
        )
    if normalise_unit(planned_unit) != normalise_unit(actual_unit):
        return Variance(
            "incompatible",
            None,
            None,
            None,
            f"Comparison unavailable: planned ({planned_unit}) and actual ({actual_unit}) "
            "use different units and no conversion rule is defined.",
        )
    if (planned_basis or "").strip().casefold() != (actual_basis or "").strip().casefold():
        return Variance(
            "incompatible",
            None,
            None,
            None,
            "Comparison unavailable: planned and actual use different measurement bases.",
        )
    absolute = actual - planned
    if planned == 0:
        return Variance(
            "ok",
            absolute,
            None,
            planned_unit,
            "Percentage variance is unavailable because the planned quantity is zero.",
        )
    percent = absolute / planned * Decimal(100)
    return Variance("ok", absolute, percent, planned_unit, "")


def rate_percent(numerator: int, denominator: int) -> Decimal | None:
    """Percentage of ``numerator`` in ``denominator``; ``None`` when ``denominator`` is 0."""
    if denominator <= 0:
        return None
    return Decimal(numerator) / Decimal(denominator) * Decimal(100)


@dataclass(frozen=True)
class InspectionOutcome:
    """Minimal inspection facts needed to decide a batch's final quality outcome."""

    inspection_id: int
    inspected_at: str
    disposition: str


def final_outcome(inspections: Iterable[InspectionOutcome]) -> str | None:
    """Final quality outcome of a batch under the documented rule.

    The final outcome is the disposition of the most recent *finalised* (passed or failed)
    inspection, ordered by inspection time then record order. Pending inspections are
    ignored. ``None`` means no final outcome exists; it is never treated as a pass.
    """
    finalised = [i for i in inspections if i.disposition in ("passed", "failed")]
    if not finalised:
        return None
    return max(finalised, key=lambda i: (i.inspected_at, i.inspection_id)).disposition
