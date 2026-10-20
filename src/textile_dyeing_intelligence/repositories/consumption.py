from __future__ import annotations

import sqlite3
from typing import Any

from ..filters import like_pattern
from .common import rows_to_dicts

_SELECT = (
    "SELECT c.*, b.batch_code, m.name AS material_name FROM consumption_records c "
    "JOIN batches b ON b.id = c.batch_id JOIN chemical_materials m ON m.id = c.material_id"
)


def insert(conn: sqlite3.Connection, d: dict[str, Any], material_id: int, now: str) -> int:
    cur = conn.execute(
        "INSERT INTO consumption_records (batch_id, material_id, category, quantity, unit, basis, "
        "recorded_at, created_at, notes) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            d["batch_id"],
            material_id,
            d["category"],
            d["quantity"],
            d["unit"],
            d["basis"] or "",
            d["recorded_at"],
            now,
            d["notes"],
        ),
    )
    return int(cur.lastrowid)


def list_records(
    conn: sqlite3.Connection,
    *,
    batch_id: int | None = None,
    material: str | None = None,
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    extra_where: str = "",
    extra_params: list[Any] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    clauses, params = [], []
    if batch_id:
        clauses.append("c.batch_id = ?")
        params.append(batch_id)
    if material:
        clauses.append("m.name LIKE ? ESCAPE '\\'")
        params.append(like_pattern(material))
    if category:
        clauses.append("c.category = ?")
        params.append(category)
    if start_date:
        clauses.append("substr(c.recorded_at, 1, 10) >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("substr(c.recorded_at, 1, 10) <= ?")
        params.append(end_date)
    if extra_where:
        clauses.append(extra_where)
        params.extend(extra_params or [])
    sql = _SELECT + (" WHERE " + " AND ".join(clauses) if clauses else "")
    sql += " ORDER BY c.recorded_at DESC, c.id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return rows_to_dicts(conn.execute(sql, params).fetchall())
