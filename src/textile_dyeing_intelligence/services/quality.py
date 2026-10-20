from __future__ import annotations

import sqlite3
from typing import Any

from .. import constants as c
from ..database import transaction
from ..errors import Conflict, NotFound, ValidationFailure
from ..repositories import batches as batches_repo
from ..repositories import quality as repo
from ..repositories.common import next_code
from ..timeutil import now_iso
from ..validation import InspectionInput, validate_model

CODE_PREFIX = "QI"


def get_inspection(conn: sqlite3.Connection, inspection_id: int) -> dict[str, Any]:
    row = repo.get(conn, inspection_id)
    if row is None:
        raise NotFound("The selected inspection does not exist.")
    row["measurements"] = repo.measurements(conn, inspection_id)
    row["defects"] = repo.defects(conn, inspection_id)
    return row


def _write_children(conn: sqlite3.Connection, inspection_id: int, data: InspectionInput) -> None:
    for measurement in data.measurements:
        repo.insert_measurement(conn, inspection_id, measurement.model_dump())
    for defect in data.defects:
        repo.insert_defect(conn, inspection_id, defect.model_dump())


def create_inspection(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    """Record an inspection. It is stored as its own record and never overwrites an earlier
    inspection of the same batch; a follow-up inspection is just another call.

    With ``disposition`` pending the inspection stays open; passed/failed finalises it.
    """
    inspection = validate_model(InspectionInput, data)
    if batches_repo.get(conn, inspection.batch_id) is None:
        raise ValidationFailure({"batch_id": "Selected batch does not exist. Select a valid batch."})
    with transaction(conn):
        now = now_iso()
        code = next_code(conn, "quality_inspections", "inspection_code", CODE_PREFIX)
        inspection_id = repo.insert_inspection(conn, code, inspection.model_dump(), now)
        _write_children(conn, inspection_id, inspection)
        if inspection.disposition != "pending":
            repo.finalise(conn, inspection_id, inspection.disposition, now)
    return get_inspection(conn, inspection_id)


def update_pending_inspection(conn: sqlite3.Connection, inspection_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Complete or correct an inspection that is still pending."""
    existing = get_inspection(conn, inspection_id)
    if existing["disposition"] != "pending":
        raise Conflict("A finalised inspection cannot be changed. Record a follow-up inspection instead.")
    inspection = validate_model(InspectionInput, {**data, "batch_id": existing["batch_id"]})
    with transaction(conn):
        now = now_iso()
        repo.update_pending(conn, inspection_id, inspection.model_dump(), now)
        repo.replace_children(conn, inspection_id)
        _write_children(conn, inspection_id, inspection)
        if inspection.disposition != "pending":
            repo.finalise(conn, inspection_id, inspection.disposition, now)
    return get_inspection(conn, inspection_id)


def finalise_inspection(conn: sqlite3.Connection, inspection_id: int, disposition: str) -> dict[str, Any]:
    existing = get_inspection(conn, inspection_id)
    if existing["disposition"] != "pending":
        raise Conflict("This inspection is already finalised and cannot be changed.")
    if disposition not in c.FINAL_DISPOSITIONS:
        raise ValidationFailure({"disposition": "Select Passed or Failed to finalise an inspection."})
    with transaction(conn):
        repo.finalise(conn, inspection_id, disposition, now_iso())
    return get_inspection(conn, inspection_id)


def list_inspections(conn: sqlite3.Connection, **filters: Any) -> list[dict[str, Any]]:
    return repo.list_inspections(conn, **filters)


def inspection_types(conn: sqlite3.Connection) -> list[str]:
    return repo.types_used(conn)
