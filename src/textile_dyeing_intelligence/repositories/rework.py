from __future__ import annotations

import sqlite3
from typing import Any

from ..filters import like_pattern
from .common import row_to_dict, rows_to_dicts

_SELECT = (
    "SELECT w.*, b.batch_code, q.inspection_code AS related_inspection_code, "
    "q.disposition AS related_inspection_disposition, q.inspected_at AS related_inspected_at "
    "FROM rework_records w JOIN batches b ON b.id = w.batch_id "
    "LEFT JOIN quality_inspections q ON q.id = w.inspection_id"
)


def insert(conn: sqlite3.Connection, code: str, d: dict[str, Any], now: str) -> int:
    cur = conn.execute(
        "INSERT INTO rework_records (rework_code, batch_id, inspection_id, reason, "
        "corrective_description, status, started_at, completed_at, notes, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            code,
            d["batch_id"],
            d["inspection_id"],
            d["reason"],
            d["corrective_description"],
            d["status"],
            d["started_at"],
            d["completed_at"],
            d["notes"],
            now,
            now,
        ),
    )
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, rework_id: int) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(_SELECT + " WHERE w.id=?", (rework_id,)).fetchone())


def list_records(
    conn: sqlite3.Connection,
    *,
    batch_id: int | None = None,
    status: str | None = None,
    reason: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    extra_where: str = "",
    extra_params: list[Any] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    date_expr = "COALESCE(substr(w.started_at, 1, 10), substr(w.created_at, 1, 10))"
    clauses, params = [], []
    if batch_id:
        clauses.append("w.batch_id = ?")
        params.append(batch_id)
    if status:
        clauses.append("w.status = ?")
        params.append(status)
    if reason:
        clauses.append("w.reason LIKE ? ESCAPE '\\'")
        params.append(like_pattern(reason))
    if start_date:
        clauses.append(f"{date_expr} >= ?")
        params.append(start_date)
    if end_date:
        clauses.append(f"{date_expr} <= ?")
        params.append(end_date)
    if extra_where:
        clauses.append(extra_where)
        params.extend(extra_params or [])
    sql = _SELECT + (" WHERE " + " AND ".join(clauses) if clauses else "")
    sql += " ORDER BY w.created_at DESC, w.id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return rows_to_dicts(conn.execute(sql, params).fetchall())


def update(conn: sqlite3.Connection, rework_id: int, d: dict[str, Any], now: str) -> None:
    conn.execute(
        "UPDATE rework_records SET reason=?, corrective_description=?, status=?, started_at=?, "
        "completed_at=?, notes=?, updated_at=? WHERE id=?",
        (
            d["reason"],
            d["corrective_description"],
            d["status"],
            d["started_at"],
            d["completed_at"],
            d["notes"],
            now,
            rework_id,
        ),
    )


def subsequent_inspection(conn: sqlite3.Connection, batch_id: int, after: str) -> dict[str, Any] | None:
    """First finalised inspection of the batch recorded after the given inspection time."""
    return row_to_dict(
        conn.execute(
            "SELECT id, inspection_code, disposition, inspected_at FROM quality_inspections "
            "WHERE batch_id=? AND disposition IN ('passed','failed') AND inspected_at > ? "
            "ORDER BY inspected_at ASC, id ASC LIMIT 1",
            (batch_id, after),
        ).fetchone()
    )
