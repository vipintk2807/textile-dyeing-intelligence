from __future__ import annotations

import sqlite3
from typing import Any

from .. import constants as c
from ..database import transaction
from ..errors import Conflict, NotFound
from ..repositories import machines as repo
from ..timeutil import now_iso
from ..validation import MachineInput, validate_model


def get_machine(conn: sqlite3.Connection, machine_id: int) -> dict[str, Any]:
    row = repo.get(conn, machine_id)
    if row is None:
        raise NotFound("The selected machine does not exist.")
    return row


def list_machines(
    conn: sqlite3.Connection, search: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    return repo.list_machines(conn, search, status)


def create_machine(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    machine = validate_model(MachineInput, data)
    with transaction(conn):
        machine_id = repo.insert(conn, machine.model_dump(), now_iso())
    return get_machine(conn, machine_id)


def update_machine(conn: sqlite3.Connection, machine_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Update descriptive fields. The machine identifier is permanent."""
    existing = get_machine(conn, machine_id)
    machine = validate_model(MachineInput, {**data, "machine_code": existing["machine_code"]})
    with transaction(conn):
        repo.update(conn, machine_id, machine.model_dump(), now_iso())
    return get_machine(conn, machine_id)


def set_machine_status(conn: sqlite3.Connection, machine_id: int, status: str) -> dict[str, Any]:
    existing = get_machine(conn, machine_id)
    if status not in c.MACHINE_STATUSES:
        from ..errors import ValidationFailure

        raise ValidationFailure({"status": "Select a valid machine status."})
    with transaction(conn):
        repo.set_status(conn, existing["id"], status, now_iso())
    return get_machine(conn, machine_id)


def delete_machine(conn: sqlite3.Connection, machine_id: int) -> None:
    """Delete a machine that has never been used. Referenced machines must be marked
    unavailable instead so batch history stays intact."""
    get_machine(conn, machine_id)
    if repo.batch_count(conn, machine_id):
        raise Conflict(
            "This machine is referenced by existing batches and cannot be deleted. "
            "Change its status to Unavailable instead."
        )
    with transaction(conn):
        repo.delete(conn, machine_id)
