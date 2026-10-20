from __future__ import annotations

import sqlite3
from typing import Any

from .common import row_to_dict, rows_to_dicts

_SELECT = (
    "SELECT q.*, b.batch_code, "
    "(SELECT COUNT(*) FROM quality_defects d WHERE d.inspection_id = q.id) AS defect_count, "
    "(SELECT COUNT(*) FROM quality_measurements m WHERE m.inspection_id = q.id) AS measurement_count "
    "FROM quality_inspections q JOIN batches b ON b.id = q.batch_id"
)


def insert_inspection(conn: sqlite3.Connection, code: str, d: dict[str, Any], now: str) -> int:
    cur = conn.execute(
        "INSERT INTO quality_inspections (inspection_code, batch_id, inspection_type, inspected_at, "
        "inspector, disposition, finalised_at, notes, created_at, updated_at) "
        "VALUES (?,?,?,?,?, 'pending', NULL, ?, ?, ?)",
        (code, d["batch_id"], d["inspection_type"], d["inspected_at"], d["inspector"], d["notes"], now, now),
    )
    return int(cur.lastrowid)


def insert_measurement(conn: sqlite3.Connection, inspection_id: int, d: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO quality_measurements (inspection_id, name, value, unit, context) VALUES (?,?,?,?,?)",
        (inspection_id, d["name"], d["value"], d["unit"], d["context"]),
    )


def insert_defect(conn: sqlite3.Connection, inspection_id: int, d: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO quality_defects (inspection_id, category, notes) VALUES (?,?,?)",
        (inspection_id, d["category"], d["notes"]),
    )


def get(conn: sqlite3.Connection, inspection_id: int) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(_SELECT + " WHERE q.id=?", (inspection_id,)).fetchone())


def list_inspections(
    conn: sqlite3.Connection,
    *,
    batch_id: int | None = None,
    outcome: str | None = None,
    inspection_type: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    extra_where: str = "",
    extra_params: list[Any] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    clauses, params = [], []
    if batch_id:
        clauses.append("q.batch_id = ?")
        params.append(batch_id)
    if outcome:
        clauses.append("q.disposition = ?")
        params.append(outcome)
    if inspection_type:
        clauses.append("q.inspection_type = ? COLLATE NOCASE")
        params.append(inspection_type)
    if start_date:
        clauses.append("substr(q.inspected_at, 1, 10) >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("substr(q.inspected_at, 1, 10) <= ?")
        params.append(end_date)
    if extra_where:
        clauses.append(extra_where)
        params.extend(extra_params or [])
    sql = _SELECT + (" WHERE " + " AND ".join(clauses) if clauses else "")
    sql += " ORDER BY q.inspected_at DESC, q.id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return rows_to_dicts(conn.execute(sql, params).fetchall())


def measurements(conn: sqlite3.Connection, inspection_id: int) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM quality_measurements WHERE inspection_id=? ORDER BY id", (inspection_id,)
        ).fetchall()
    )


def defects(conn: sqlite3.Connection, inspection_id: int) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute("SELECT * FROM quality_defects WHERE inspection_id=? ORDER BY id", (inspection_id,)).fetchall()
    )


def update_pending(conn: sqlite3.Connection, inspection_id: int, d: dict[str, Any], now: str) -> None:
    conn.execute(
        "UPDATE quality_inspections SET inspection_type=?, inspected_at=?, inspector=?, notes=?, "
        "updated_at=? WHERE id=?",
        (d["inspection_type"], d["inspected_at"], d["inspector"], d["notes"], now, inspection_id),
    )


def replace_children(conn: sqlite3.Connection, inspection_id: int) -> None:
    conn.execute("DELETE FROM quality_measurements WHERE inspection_id=?", (inspection_id,))
    conn.execute("DELETE FROM quality_defects WHERE inspection_id=?", (inspection_id,))


def finalise(conn: sqlite3.Connection, inspection_id: int, disposition: str, now: str) -> None:
    conn.execute(
        "UPDATE quality_inspections SET disposition=?, finalised_at=?, updated_at=? WHERE id=?",
        (disposition, now, now, inspection_id),
    )


def types_used(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT inspection_type FROM quality_inspections ORDER BY inspection_type COLLATE NOCASE"
    ).fetchall()
    return [r[0] for r in rows]
