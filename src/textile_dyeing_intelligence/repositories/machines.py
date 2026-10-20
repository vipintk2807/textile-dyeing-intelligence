from __future__ import annotations

import sqlite3
from typing import Any

from ..filters import like_pattern
from .common import row_to_dict, rows_to_dicts


def insert(conn: sqlite3.Connection, d: dict[str, Any], now: str) -> int:
    cur = conn.execute(
        "INSERT INTO machines (machine_code, name, machine_type, capacity, capacity_unit, "
        "status, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            d["machine_code"],
            d["name"],
            d["machine_type"],
            d["capacity"],
            d["capacity_unit"],
            d["status"],
            d["notes"],
            now,
            now,
        ),
    )
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, machine_id: int) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone())


def list_machines(
    conn: sqlite3.Connection, search: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    sql = "SELECT m.*, (SELECT COUNT(*) FROM batches b WHERE b.machine_id = m.id) AS batch_count FROM machines m"
    clauses, params = [], []
    if search:
        clauses.append("(m.machine_code LIKE ? ESCAPE '\\' OR m.name LIKE ? ESCAPE '\\')")
        params += [like_pattern(search)] * 2
    if status:
        clauses.append("m.status = ?")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return rows_to_dicts(conn.execute(sql + " ORDER BY m.machine_code", params).fetchall())


def update(conn: sqlite3.Connection, machine_id: int, d: dict[str, Any], now: str) -> None:
    conn.execute(
        "UPDATE machines SET name=?, machine_type=?, capacity=?, capacity_unit=?, status=?, "
        "notes=?, updated_at=? WHERE id=?",
        (d["name"], d["machine_type"], d["capacity"], d["capacity_unit"], d["status"], d["notes"], now, machine_id),
    )


def set_status(conn: sqlite3.Connection, machine_id: int, status: str, now: str) -> None:
    conn.execute("UPDATE machines SET status=?, updated_at=? WHERE id=?", (status, now, machine_id))


def batch_count(conn: sqlite3.Connection, machine_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM batches WHERE machine_id=?", (machine_id,)).fetchone()[0])


def delete(conn: sqlite3.Connection, machine_id: int) -> None:
    conn.execute("DELETE FROM machines WHERE id=?", (machine_id,))
