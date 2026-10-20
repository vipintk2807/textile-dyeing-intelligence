"""Input models and validation (Pydantic 2.x).

Messages written by validators are *tails* that complete the sentence "<Field label> ...".
:func:`validate_model` prefixes the label and returns a ``ValidationFailure`` whose
``errors`` map field keys to complete messages. Model-level (cross-field) messages are
complete sentences stored under ``"__all__"``.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Annotated, Any, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from .decimals import canonical_text, parse_decimal
from .errors import ValidationFailure
from .timeutil import parse_date, parse_timestamp

# --------------------------------------------------------------------------------------
# Reusable field types
# --------------------------------------------------------------------------------------

CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,39}$")


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _number_to_text(value: Any) -> Any:
    """Allow int/Decimal input; reject floats and bools (binary floating point is inexact)."""
    if isinstance(value, bool | float):
        raise ValueError("must be entered as a decimal number such as 12 or 12.5.")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _check_code(value: str) -> str:
    if not CODE_RE.match(value):
        raise ValueError(
            "may contain only letters, digits, '.', '_', '-' and '/', must start with a "
            "letter or digit, and can be at most 40 characters."
        )
    return value


def _positive_decimal(value: str) -> str:
    return canonical_text(parse_decimal(value, allow_zero=False))


def _non_negative_decimal(value: str) -> str:
    return canonical_text(parse_decimal(value, allow_zero=True))


def _opt(func):
    def inner(value: str | None) -> str | None:
        return None if value is None else func(value)

    return inner


def _check_unit(value: str) -> str:
    if len(value) > 20:
        raise ValueError("is too long (maximum 20 characters).")
    return value


def _timestamp(value: Any) -> str:
    return parse_timestamp(value)


def _date(value: Any) -> str:
    return parse_date(value)


Code = Annotated[str, Field(min_length=1, max_length=40), AfterValidator(_check_code)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
ShortText = Annotated[Annotated[str, Field(max_length=200)] | None, BeforeValidator(_blank_to_none)]
Notes = Annotated[Annotated[str, Field(max_length=2000)] | None, BeforeValidator(_blank_to_none)]
Unit = Annotated[str, Field(min_length=1, max_length=20), AfterValidator(_check_unit)]
OptUnit = Annotated[Annotated[str, Field(max_length=20)] | None, BeforeValidator(_blank_to_none)]
PositiveDecimal = Annotated[str, BeforeValidator(_number_to_text), AfterValidator(_positive_decimal)]
NonNegativeDecimal = Annotated[str, BeforeValidator(_number_to_text), AfterValidator(_non_negative_decimal)]
OptPositiveDecimal = Annotated[
    str | None,
    BeforeValidator(lambda v: _blank_to_none(_number_to_text(v))),
    AfterValidator(_opt(_positive_decimal)),
]
Timestamp = Annotated[str, BeforeValidator(_blank_to_none), AfterValidator(_timestamp)]
OptTimestamp = Annotated[str | None, BeforeValidator(_blank_to_none), AfterValidator(_opt(_timestamp))]
OptDate = Annotated[str | None, BeforeValidator(_blank_to_none), AfterValidator(_opt(_date))]
RecordId = Annotated[int, Field(ge=1)]
OptRecordId = Annotated[Annotated[int, Field(ge=1)] | None, BeforeValidator(_blank_to_none)]


class _Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


# --------------------------------------------------------------------------------------
# Input models
# --------------------------------------------------------------------------------------


class MachineInput(_Model):
    machine_code: Code
    name: Name
    machine_type: ShortText = None
    capacity: OptPositiveDecimal = None
    capacity_unit: OptUnit = None
    status: Literal["available", "unavailable", "maintenance"] = "available"
    notes: Notes = None

    @model_validator(mode="after")
    def _capacity_pair(self) -> MachineInput:
        if (self.capacity is None) != (self.capacity_unit is None):
            raise ValueError("Capacity and capacity unit must be entered together, or both left blank.")
        return self


class RecipeInput(_Model):
    recipe_code: Code
    name: Name
    description: Notes = None
    applicable_material: ShortText = None


class IngredientInput(_Model):
    material_name: Name
    quantity: PositiveDecimal
    unit: Unit
    dosing_basis: ShortText = None
    notes: Notes = None


class RevisionInput(_Model):
    revision_code: Code
    description: Notes = None
    effective_date: OptDate = None
    notes: Notes = None
    ingredients: list[IngredientInput] = Field(min_length=1, max_length=100)


class BatchInput(_Model):
    batch_code: Code
    work_order_ref: ShortText = None
    material_description: Name
    quantity: PositiveDecimal
    quantity_unit: Unit
    recipe_revision_id: OptRecordId = None
    machine_id: OptRecordId = None
    planned_date: OptDate = None
    actual_start: OptTimestamp = None
    actual_end: OptTimestamp = None
    notes: Notes = None

    @model_validator(mode="after")
    def _times_in_order(self) -> BatchInput:
        if self.actual_start and self.actual_end and self.actual_end < self.actual_start:
            raise ValueError("Actual completion must not be earlier than actual start.")
        return self


class ProcessRecordInput(_Model):
    batch_id: RecordId
    parameter_name: Name
    value: NonNegativeDecimal
    unit: OptUnit = None
    observed_at: Timestamp
    source: Literal["operator_entry", "document_transcription", "other_documented"] = "operator_entry"
    notes: Notes = None


class ConsumptionInput(_Model):
    batch_id: RecordId
    material_name: Name
    category: Literal["planned", "actual"]
    quantity: NonNegativeDecimal
    unit: Unit
    basis: ShortText = None
    recorded_at: Timestamp
    notes: Notes = None


class MeasurementInput(_Model):
    name: Name
    value: NonNegativeDecimal
    unit: OptUnit = None
    context: ShortText = None


class DefectInput(_Model):
    category: Name
    notes: Notes = None


class InspectionInput(_Model):
    batch_id: RecordId
    inspection_type: Name
    inspected_at: Timestamp
    inspector: ShortText = None
    disposition: Literal["pending", "passed", "failed"] = "pending"
    measurements: list[MeasurementInput] = Field(default_factory=list, max_length=50)
    defects: list[DefectInput] = Field(default_factory=list, max_length=50)
    notes: Notes = None


class ReworkInput(_Model):
    batch_id: RecordId
    inspection_id: OptRecordId = None
    reason: Name
    corrective_description: Notes = None
    status: Literal["required", "in_progress", "completed", "cancelled"] = "required"
    started_at: OptTimestamp = None
    completed_at: OptTimestamp = None
    notes: Notes = None

    @model_validator(mode="after")
    def _rules(self) -> ReworkInput:
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValueError("Rework completion must not be earlier than its start.")
        if self.status == "completed":
            if not self.corrective_description:
                raise ValueError("A description of the corrective work is required when rework is completed.")
            if not self.completed_at:
                raise ValueError("A completion date and time is required when rework is completed.")
        return self


# --------------------------------------------------------------------------------------
# Error translation
# --------------------------------------------------------------------------------------

FIELD_LABELS = {
    "machine_code": "Machine identifier",
    "name": "Name",
    "machine_type": "Machine type",
    "capacity": "Capacity",
    "capacity_unit": "Capacity unit",
    "status": "Status",
    "notes": "Notes",
    "recipe_code": "Recipe identifier",
    "description": "Description",
    "applicable_material": "Applicable material",
    "material_name": "Material",
    "quantity": "Quantity",
    "unit": "Unit",
    "dosing_basis": "Dosing basis",
    "revision_code": "Revision identifier",
    "effective_date": "Effective date",
    "ingredients": "Ingredients",
    "batch_code": "Batch identifier",
    "work_order_ref": "Work-order reference",
    "material_description": "Fabric or material description",
    "quantity_unit": "Quantity unit",
    "recipe_revision_id": "Recipe revision",
    "machine_id": "Machine",
    "planned_date": "Planned production date",
    "actual_start": "Actual start",
    "actual_end": "Actual completion",
    "batch_id": "Batch",
    "parameter_name": "Parameter name",
    "value": "Value",
    "observed_at": "Observation time",
    "source": "Source",
    "category": "Category",
    "basis": "Measurement basis",
    "recorded_at": "Recording time",
    "inspection_type": "Inspection type",
    "inspected_at": "Inspection time",
    "inspector": "Inspector",
    "disposition": "Outcome",
    "measurements": "Measurements",
    "defects": "Defects",
    "context": "Context",
    "inspection_id": "Related inspection",
    "reason": "Reason",
    "corrective_description": "Corrective work description",
    "started_at": "Start time",
    "completed_at": "Completion time",
}

_ITEM_LABELS = {"ingredients": "Ingredient", "measurements": "Measurement", "defects": "Defect"}


def _label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").capitalize())


def _tail(error: dict[str, Any]) -> str:
    kind = error["type"]
    ctx = error.get("ctx", {})
    if kind == "value_error":
        message = str(error["msg"])
        return message.removeprefix("Value error, ")
    if kind in ("missing", "string_too_short", "string_type", "none_required"):
        return "is required."
    if kind == "string_too_long":
        return f"is too long (maximum {ctx.get('max_length')} characters)."
    if kind in ("int_type", "int_parsing", "greater_than_equal", "int_from_float"):
        return "must be a valid selection."
    if kind == "literal_error":
        return "has an unsupported value."
    if kind == "too_short":
        return "must contain at least one entry."
    if kind == "too_long":
        return f"has too many entries (maximum {ctx.get('max_length')})."
    return str(error["msg"]).rstrip(".") + "."


def _key_and_label(loc: tuple[Any, ...]) -> tuple[str, str]:
    """Return the error key (``ingredients[0].quantity``) and a readable label."""
    if not loc:
        return "__all__", ""
    parts: list[str] = []
    labels: list[str] = []
    i = 0
    while i < len(loc):
        part = loc[i]
        if isinstance(part, str) and i + 1 < len(loc) and isinstance(loc[i + 1], int):
            index = loc[i + 1]
            parts.append(f"{part}[{index}]")
            labels.append(f"{_ITEM_LABELS.get(part, _label(part))} {index + 1}")
            i += 2
        else:
            parts.append(str(part))
            labels.append(_label(str(part)))
            i += 1
    return ".".join(parts), " - ".join(labels)


ModelT = TypeVar("ModelT", bound=BaseModel)


def validate_model(model: type[ModelT], data: dict[str, Any]) -> ModelT:
    """Validate ``data`` or raise ``ValidationFailure`` with friendly messages."""
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for err in exc.errors():
            key, label = _key_and_label(tuple(err["loc"]))
            if err["type"] == "extra_forbidden":
                errors[f"{key}"] = f"Unexpected field '{key}'."
                continue
            message = _tail(err)
            errors.setdefault(key, message if key == "__all__" else f"{label} {message}")
        raise ValidationFailure(errors) from None


def check_status_transition(
    current: str, new: str, transitions: dict[str, tuple[str, ...]], labels: dict[str, str], noun: str
) -> None:
    """Raise ``ValidationFailure`` unless ``current -> new`` is a permitted transition."""
    if new == current:
        return
    if new not in transitions:
        raise ValidationFailure(f"Unknown {noun} status.")
    if new not in transitions.get(current, ()):
        allowed = ", ".join(labels[s] for s in transitions.get(current, ())) or "none"
        raise ValidationFailure(
            f"A {noun} cannot change from {labels[current]} to {labels[new]}. Permitted next statuses: {allowed}."
        )
