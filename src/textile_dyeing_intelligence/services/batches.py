from __future__ import annotations

import sqlite3
from typing import Any

from .. import constants as c
from ..database import transaction
from ..errors import Conflict, NotFound, ValidationFailure
from ..filters import ReportFilters
from ..repositories import batches as repo
from ..repositories import consumption as consumption_repo
from ..repositories import machines as machines_repo
from ..repositories import process_records as process_repo
from ..repositories import quality as quality_repo
from ..repositories import recipes as recipes_repo
from ..repositories import rework as rework_repo
from ..timeutil import now_iso, parse_timestamp
from ..validation import BatchInput, check_status_transition, validate_model


def quality_label(batch: dict[str, Any]) -> str:
    """Batch-level quality summary text. Absence of a result is never shown as a pass."""
    if batch["final_outcome"] == "passed":
        label = "Passed"
    elif batch["final_outcome"] == "failed":
        label = "Failed"
    elif batch["inspection_count"] == 0:
        return "Not inspected"
    else:
        return "Pending (no final outcome)"
    if batch["pending_inspection_count"]:
        label += " (follow-up pending)"
    return label


def _check_references(conn: sqlite3.Connection, data: BatchInput, existing: dict[str, Any] | None = None) -> None:
    errors: dict[str, str] = {}
    revision_id = data.recipe_revision_id
    if revision_id is not None:
        revision = recipes_repo.get_revision(conn, revision_id)
        unchanged = existing is not None and existing["recipe_revision_id"] == revision_id
        if revision is None:
            errors["recipe_revision_id"] = "Selected recipe revision is unavailable. Select a valid revision."
        elif not unchanged and (revision["status"] != "active" or revision["recipe_status"] != "active"):
            errors["recipe_revision_id"] = (
                "Selected recipe revision is archived and cannot be used for new work. Select an active revision."
            )
    if data.machine_id is not None and machines_repo.get(conn, data.machine_id) is None:
        errors["machine_id"] = "Selected machine does not exist. Select a registered machine."
    if errors:
        raise ValidationFailure(errors)


def create_batch(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    batch = validate_model(BatchInput, data)
    _check_references(conn, batch)
    with transaction(conn):
        batch_id = repo.insert(conn, batch.model_dump(), now_iso())
    return get_batch(conn, batch_id)


def get_batch(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any]:
    row = repo.get(conn, batch_id)
    if row is None:
        raise NotFound("The selected batch does not exist.")
    row["quality_label"] = quality_label(row)
    return row


def update_batch(conn: sqlite3.Connection, batch_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Update permitted fields. The identifier is permanent. Completed and cancelled batches
    keep their quantity, recipe revision and machine; only descriptive fields can change."""
    existing = get_batch(conn, batch_id)
    batch = validate_model(BatchInput, {**data, "batch_code": existing["batch_code"]})
    new = batch.model_dump()
    if existing["status"] in c.BATCH_LOCKED_STATUSES:
        locked = {
            "quantity": existing["quantity"],
            "quantity_unit": existing["quantity_unit"],
            "recipe_revision_id": existing["recipe_revision_id"],
            "machine_id": existing["machine_id"],
        }
        changed = [k for k, v in locked.items() if str(new[k] or "") != str(v or "")]
        if changed:
            raise ValidationFailure(
                f"A {c.BATCH_STATUS_LABELS[existing['status']].lower()} batch keeps its quantity, "
                "recipe revision and machine so its history stays reliable. "
                "Only notes, description, dates and the work-order reference can be edited."
            )
    _check_references(conn, batch, existing)
    with transaction(conn):
        repo.update(conn, batch_id, new, now_iso())
    return get_batch(conn, batch_id)


def change_status(
    conn: sqlite3.Connection,
    batch_id: int,
    new_status: str,
    *,
    actual_start: str | None = None,
    actual_end: str | None = None,
) -> dict[str, Any]:
    """Change production status through a permitted transition.

    Quality and rework records are never touched. Timestamps are only stored when the user
    supplies them; they are not invented.
    """
    existing = get_batch(conn, batch_id)
    check_status_transition(existing["status"], new_status, c.BATCH_TRANSITIONS, c.BATCH_STATUS_LABELS, "batch")
    errors: dict[str, str] = {}
    start, end = existing["actual_start"], existing["actual_end"]
    for key, label, value in (
        ("actual_start", "Actual start", actual_start),
        ("actual_end", "Actual completion", actual_end),
    ):
        if value:
            try:
                parsed = parse_timestamp(value)
            except ValueError as exc:
                errors[key] = f"{label} {exc}"
                continue
            if key == "actual_start":
                start = parsed
            else:
                end = parsed
    if errors:
        raise ValidationFailure(errors)
    if start and end and end < start:
        raise ValidationFailure({"actual_end": "Actual completion must not be earlier than actual start."})
    with transaction(conn):
        repo.set_status(conn, batch_id, new_status, start, end, now_iso())
    return get_batch(conn, batch_id)


def search_batches(
    conn: sqlite3.Connection, filters: ReportFilters, limit: int | None = None, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """Return ``(rows, total_matching)``."""
    filters = filters.validated()
    rows = repo.search(conn, filters, limit, offset)
    for row in rows:
        row["quality_label"] = quality_label(row)
    return rows, repo.count(conn, filters)


def batch_options(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return repo.list_options(conn)


def get_batch_detail(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any]:
    """Everything recorded for a batch: the single place to review its history."""
    from . import consumption as consumption_service

    batch = get_batch(conn, batch_id)
    inspections = quality_repo.list_inspections(conn, batch_id=batch_id)
    for inspection in inspections:
        inspection["measurements"] = quality_repo.measurements(conn, inspection["id"])
        inspection["defects"] = quality_repo.defects(conn, inspection["id"])
    revision = None
    if batch["recipe_revision_id"]:
        from . import recipes as recipes_service

        revision = recipes_service.get_revision(conn, batch["recipe_revision_id"])
    return {
        "batch": batch,
        "revision": revision,
        "machine": machines_repo.get(conn, batch["machine_id"]) if batch["machine_id"] else None,
        "process_records": process_repo.list_records(conn, batch_id=batch_id),
        "consumption_records": consumption_repo.list_records(conn, batch_id=batch_id),
        "consumption_comparison": consumption_service.compare_for_batch(conn, batch_id),
        "inspections": inspections,
        "rework": rework_repo.list_records(conn, batch_id=batch_id),
    }


__all__ = [
    "Conflict",
    "batch_options",
    "change_status",
    "create_batch",
    "get_batch",
    "get_batch_detail",
    "quality_label",
    "search_batches",
    "update_batch",
]
