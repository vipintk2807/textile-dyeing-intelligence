from decimal import Decimal

from textile_dyeing_intelligence.calculations import InspectionOutcome as I
from textile_dyeing_intelligence.calculations import final_outcome, rate_percent


def test_no_inspections_has_no_final_outcome():
    assert final_outcome([]) is None


def test_pending_only_is_not_a_pass():
    assert final_outcome([I(1, "2026-03-01T10:00:00", "pending")]) is None


def test_latest_finalised_inspection_decides():
    items = [
        I(1, "2026-03-01T10:00:00", "failed"),
        I(2, "2026-03-02T10:00:00", "passed"),
        I(3, "2026-03-03T10:00:00", "pending"),
    ]
    assert final_outcome(items) == "passed"
    assert final_outcome(items[:1]) == "failed"


def test_tie_on_time_uses_record_order():
    items = [I(1, "2026-03-01T10:00:00", "passed"), I(2, "2026-03-01T10:00:00", "failed")]
    assert final_outcome(items) == "failed"


def test_rate_percent_and_zero_denominator():
    assert rate_percent(1, 4) == Decimal(25)
    assert rate_percent(0, 4) == Decimal(0)
    assert rate_percent(0, 0) is None
