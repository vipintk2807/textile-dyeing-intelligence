from __future__ import annotations

import sqlite3
from typing import Any

from .. import constants as c
from ..database import transaction
from ..errors import Conflict, NotFound, ValidationFailure
from ..repositories import batches as batches_repo
from ..repositories import quality as quality_repo
from ..repositories import rework as repo
from ..repositories.common import next_code
from ..timeutil import now_iso
from ..validation import ReworkInput, check_status_transition, validate_model

CODE_PREFIX = "RW"


def get_rework(conn: sqlite3.Connection, rework_id: int) -> dict[str, Any]:
    row = repo.get(conn, rework_id)
    if row is None:
        raise NotFound("The selected rework record does not exist.")
    return row


def _check_links(conn: sqlite3.Connection, batch_id: int, inspection_id: int | None) -> None:
    if batches_repo.get(conn, batch_id) is None:
        raise ValidationFailure({"batch_id": "Selected batch does not exist. Select a valid batch."})
    if inspection_id is not None:
        inspection = quality_repo.get(conn, inspection_id)
        if inspection is None:
            raise ValidationFailure({"inspection_id": "Related inspection does not exist."})
        if inspection["batch_id"] != batch_id:
            raise ValidationFailure({"inspection_id": "The related inspection belongs to a different batch."})


def create_rework(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    """Record a rework event. It never changes the original inspection result."""
    rework = validate_model(ReworkInput, data)
    _check_links(conn, rework.batch_id, rework.inspection_id)
    with transaction(conn):
        code = next_code(conn, "rework_records", "rework_code", CODE_PREFIX)
        rework_id = repo.insert(conn, code, rework.model_dump(), now_iso())
    return get_rework(conn, rework_id)


def update_rework(conn: sqlite3.Connection, rework_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Update progress. Completed and cancelled rework is closed: only notes can change.
    Completing rework does not mark the batch as quality-approved."""
    existing = get_rework(conn, rework_id)
    merged = {
        "batch_id": existing["batch_id"],
        "inspection_id": existing["inspection_id"],
        "reason": existing["reason"],
        "corrective_description": existing["corrective_description"],
        "status": existing["status"],
        "started_at": existing["started_at"],
        "completed_at": existing["completed_at"],
        "notes": existing["notes"],
        **data,
    }
    merged["batch_id"], merged["inspection_id"] = existing["batch_id"], existing["inspection_id"]
    rework = validate_model(ReworkInput, merged)
    new = rework.model_dump()
    if existing["status"] in ("completed", "cancelled"):
        changed = [
            k
            for k in ("reason", "corrective_description", "status", "started_at", "completed_at")
            if (new[k] or None) != (existing[k] or None)
        ]
        if changed:
            raise Conflict(
                "Completed or cancelled rework is closed. Only its notes can be edited; "
                "record a new rework event if more work is needed."
            )
    else:
        check_status_transition(
            existing["status"], new["status"], c.REWORK_TRANSITIONS, c.REWORK_STATUS_LABELS, "rework record"
        )
    with transaction(conn):
        repo.update(conn, rework_id, new, now_iso())
    return get_rework(conn, rework_id)


def list_rework(conn: sqlite3.Connection, **filters: Any) -> list[dict[str, Any]]:
    return repo.list_records(conn, **filters)


def with_subsequent_inspection(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the first finalised inspection recorded after the linked inspection.

    Rework without a linked inspection has no anchor time, so its follow-up outcome is
    reported as unavailable rather than guessed.
    """
    for row in rows:
        anchor = row.get("related_inspected_at")
        row["subsequent_inspection"] = repo.subsequent_inspection(conn, row["batch_id"], anchor) if anchor else None
        row["subsequent_available"] = bool(anchor)
    return rows


__all__ = [
    "CODE_PREFIX",
    "Conflict",
    "create_rework",
    "get_rework",
    "list_rework",
    "update_rework",
    "with_subsequent_inspection",
]
