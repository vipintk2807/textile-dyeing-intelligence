from __future__ import annotations

import sqlite3
from typing import Any

from ..filters import like_pattern
from .common import row_to_dict, rows_to_dicts

_SELECT = "SELECT p.*, b.batch_code FROM process_records p JOIN batches b ON b.id = p.batch_id"


def insert(conn: sqlite3.Connection, d: dict[str, Any], now: str) -> int:
    cur = conn.execute(
        "INSERT INTO process_records (batch_id, parameter_name, value, unit, observed_at, "
        "recorded_at, updated_at, source, notes) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            d["batch_id"],
            d["parameter_name"],
            d["value"],
            d["unit"],
            d["observed_at"],
            now,
            now,
            d["source"],
            d["notes"],
        ),
    )
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, record_id: int) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(_SELECT + " WHERE p.id=?", (record_id,)).fetchone())


def list_records(
    conn: sqlite3.Connection,
    *,
    batch_id: int | None = None,
    parameter: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    clauses, params = [], []
    if batch_id:
        clauses.append("p.batch_id = ?")
        params.append(batch_id)
    if parameter:
        clauses.append("p.parameter_name LIKE ? ESCAPE '\\'")
        params.append(like_pattern(parameter))
    if start_date:
        clauses.append("substr(p.observed_at, 1, 10) >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("substr(p.observed_at, 1, 10) <= ?")
        params.append(end_date)
    sql = _SELECT + (" WHERE " + " AND ".join(clauses) if clauses else "")
    sql += " ORDER BY p.observed_at DESC, p.id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return rows_to_dicts(conn.execute(sql, params).fetchall())


def update(conn: sqlite3.Connection, record_id: int, d: dict[str, Any], now: str) -> None:
    conn.execute(
        "UPDATE process_records SET parameter_name=?, value=?, unit=?, observed_at=?, source=?, "
        "notes=?, updated_at=? WHERE id=?",
        (d["parameter_name"], d["value"], d["unit"], d["observed_at"], d["source"], d["notes"], now, record_id),
    )


def insert_history(conn: sqlite3.Connection, previous: dict[str, Any], now: str) -> None:
    conn.execute(
        "INSERT INTO process_record_history (process_record_id, changed_at, previous_parameter_name, "
        "previous_value, previous_unit, previous_observed_at, previous_source, previous_notes) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            previous["id"],
            now,
            previous["parameter_name"],
            previous["value"],
            previous["unit"],
            previous["observed_at"],
            previous["source"],
            previous["notes"],
        ),
    )


def list_history(conn: sqlite3.Connection, record_id: int) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT * FROM process_record_history WHERE process_record_id=? ORDER BY id DESC",
            (record_id,),
        ).fetchall()
    )
