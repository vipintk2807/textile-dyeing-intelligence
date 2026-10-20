from decimal import Decimal

import pytest

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence.decimals import canonical_text, format_decimal, parse_decimal
from textile_dyeing_intelligence.errors import ValidationFailure
from textile_dyeing_intelligence.timeutil import parse_date, parse_timestamp
from textile_dyeing_intelligence.validation import (
    BatchInput,
    ConsumptionInput,
    MachineInput,
    ReworkInput,
    check_status_transition,
    validate_model,
)

BATCH = {"batch_code": "B-1", "material_description": "Fabric", "quantity": "10", "quantity_unit": "kg"}


@pytest.mark.parametrize(
    "text,expected",
    [("10", "10"), ("10.50", "10.50"), ("0", "0"), ("007.5", "7.5"), (".5", "0.5"), ("+3", "3"), ("-0", "0")],
)
def test_parse_decimal_valid(text, expected):
    assert canonical_text(parse_decimal(text)) == expected


@pytest.mark.parametrize("text", ["", "abc", "1,5", "1e3", "NaN", "Infinity", "12 kg", "--1", "1.1234567", "1" * 16])
def test_parse_decimal_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_decimal(text)


def test_parse_decimal_rejects_negative_and_zero_rules():
    with pytest.raises(ValueError, match="negative"):
        parse_decimal("-1")
    with pytest.raises(ValueError, match="greater than zero"):
        parse_decimal("0", allow_zero=False)
    assert parse_decimal("-1", allow_negative=True) == Decimal(-1)


def test_floats_and_bools_are_rejected():
    with pytest.raises(ValueError):
        parse_decimal(1.5)
    with pytest.raises(ValueError):
        parse_decimal(True)


def test_format_decimal_display_does_not_change_value():
    value = Decimal("2.005")
    assert format_decimal(value, 2) == "2.01"
    assert value == Decimal("2.005")
    assert format_decimal(Decimal("2"), signed=True) == "+2"
    assert format_decimal(None) == ""


def test_batch_valid_and_canonical_quantity():
    batch = validate_model(BatchInput, {**BATCH, "quantity": 12})
    assert batch.quantity == "12"


@pytest.mark.parametrize(
    "field,value,fragment",
    [
        ("batch_code", "", "required"),
        ("batch_code", "bad code", "letters"),
        ("batch_code", "x" * 41, "too long"),
        ("quantity", "0", "greater than zero"),
        ("quantity", "-5", "negative"),
        ("quantity", "abc", "plain number"),
        ("material_description", "   ", "required"),
        ("quantity_unit", "", "required"),
        ("planned_date", "2026-13-40", "valid date"),
        ("actual_start", "2026-03-01", "include a time"),
        ("recipe_revision_id", 0, "valid selection"),
    ],
)
def test_batch_field_errors(field, value, fragment):
    with pytest.raises(ValidationFailure) as exc:
        validate_model(BatchInput, {**BATCH, field: value})
    assert fragment in exc.value.errors[field]


def test_batch_cross_field_time_order():
    with pytest.raises(ValidationFailure) as exc:
        validate_model(BatchInput, {**BATCH, "actual_start": "2026-03-02 10:00", "actual_end": "2026-03-02 09:00"})
    assert "earlier" in exc.value.errors["__all__"]


def test_unicode_punctuation_and_sql_text_are_accepted_as_plain_text():
    text = "Café ‘test’; DROP TABLE batches;-- ✓"
    batch = validate_model(BatchInput, {**BATCH, "notes": text, "material_description": text})
    assert batch.notes == text


def test_consumption_zero_allowed_negative_rejected():
    base = {
        "batch_id": 1,
        "material_name": "Salt",
        "category": "planned",
        "unit": "kg",
        "recorded_at": "2026-03-01 08:00",
    }
    assert validate_model(ConsumptionInput, {**base, "quantity": "0"}).quantity == "0"
    with pytest.raises(ValidationFailure):
        validate_model(ConsumptionInput, {**base, "quantity": "-1"})
    with pytest.raises(ValidationFailure):
        validate_model(ConsumptionInput, {**base, "quantity": "1", "category": "issued"})


def test_machine_capacity_requires_unit():
    with pytest.raises(ValidationFailure):
        validate_model(MachineInput, {"machine_code": "M1", "name": "x", "capacity": "100"})
    assert validate_model(MachineInput, {"machine_code": "M1", "name": "x"}).capacity is None


def test_rework_completed_requires_description_and_time():
    base = {"batch_id": 1, "reason": "r", "status": "completed"}
    with pytest.raises(ValidationFailure):
        validate_model(ReworkInput, base)
    ok = validate_model(ReworkInput, {**base, "corrective_description": "done", "completed_at": "2026-03-01 10:00"})
    assert ok.status == "completed"


def test_timestamp_and_date_parsing():
    assert parse_timestamp("2026-03-05 14:30") == "2026-03-05T14:30:00"
    for bad in ("2026-03-05", "2026-03-05T14:30+05:30", "garbage", ""):
        with pytest.raises(ValueError):
            parse_timestamp(bad)
    assert parse_date("2026-03-05") == "2026-03-05"
    with pytest.raises(ValueError):
        parse_date("05/03/2026")


def test_status_transitions():
    check_status_transition("planned", "in_progress", c.BATCH_TRANSITIONS, c.BATCH_STATUS_LABELS, "batch")
    for current, new in (("cancelled", "completed"), ("completed", "planned"), ("planned", "completed")):
        with pytest.raises(ValidationFailure):
            check_status_transition(current, new, c.BATCH_TRANSITIONS, c.BATCH_STATUS_LABELS, "batch")
