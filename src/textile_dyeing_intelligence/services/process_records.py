from __future__ import annotations

import sqlite3
from typing import Any

from ..database import transaction
from ..errors import NotFound, ValidationFailure
from ..repositories import batches as batches_repo
from ..repositories import process_records as repo
from ..timeutil import now_iso
from ..validation import ProcessRecordInput, validate_model


def _require_batch(conn: sqlite3.Connection, batch_id: int) -> None:
    if batches_repo.get(conn, batch_id) is None:
        raise ValidationFailure({"batch_id": "Selected batch does not exist. Select a valid batch."})


def create_process_record(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    record = validate_model(ProcessRecordInput, data)
    _require_batch(conn, record.batch_id)
    with transaction(conn):
        record_id = repo.insert(conn, record.model_dump(), now_iso())
    return get_record(conn, record_id)


def get_record(conn: sqlite3.Connection, record_id: int) -> dict[str, Any]:
    row = repo.get(conn, record_id)
    if row is None:
        raise NotFound("The selected process record does not exist.")
    return row


def update_process_record(conn: sqlite3.Connection, record_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Correct an entry. The previous values are kept in the change history, and the batch
    association cannot be changed."""
    existing = get_record(conn, record_id)
    record = validate_model(ProcessRecordInput, {**data, "batch_id": existing["batch_id"]})
    with transaction(conn):
        now = now_iso()
        repo.insert_history(conn, existing, now)
        repo.update(conn, record_id, record.model_dump(), now)
    return get_record(conn, record_id)


def list_process_records(conn: sqlite3.Connection, **filters: Any) -> list[dict[str, Any]]:
    return repo.list_records(conn, **filters)


def record_history(conn: sqlite3.Connection, record_id: int) -> list[dict[str, Any]]:
    return repo.list_history(conn, record_id)
