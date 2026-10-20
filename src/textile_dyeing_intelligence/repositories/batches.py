from __future__ import annotations

import sqlite3
from typing import Any

from ..filters import ReportFilters, Where, batch_conditions, batch_date_sql, final_outcome_sql
from .common import row_to_dict, rows_to_dicts

BATCH_SELECT = f"""
SELECT b.*,
       rr.revision_code AS revision_code, r.recipe_code AS recipe_code, r.name AS recipe_name,
       m.machine_code AS machine_code, m.name AS machine_name, m.status AS machine_status,
       {batch_date_sql("b")} AS reporting_date,
       {final_outcome_sql("b")} AS final_outcome,
       (SELECT COUNT(*) FROM quality_inspections q WHERE q.batch_id = b.id) AS inspection_count,
       (SELECT COUNT(*) FROM quality_inspections q
         WHERE q.batch_id = b.id AND q.disposition = 'pending') AS pending_inspection_count,
       (SELECT COUNT(*) FROM rework_records w
         WHERE w.batch_id = b.id AND w.status <> 'cancelled') AS rework_events,
       (SELECT COUNT(*) FROM rework_records w
         WHERE w.batch_id = b.id AND w.status IN ('required','in_progress')) AS open_rework
FROM batches b
LEFT JOIN recipe_revisions rr ON rr.id = b.recipe_revision_id
LEFT JOIN recipes r ON r.id = rr.recipe_id
LEFT JOIN machines m ON m.id = b.machine_id
"""


def insert(conn: sqlite3.Connection, d: dict[str, Any], now: str) -> int:
    cur = conn.execute(
        "INSERT INTO batches (batch_code, work_order_ref, material_description, quantity, "
        "quantity_unit, recipe_revision_id, machine_id, status, planned_date, actual_start, "
        "actual_end, notes, created_at, updated_at) VALUES (?,?,?,?,?,?,?, 'planned', ?,?,?,?,?,?)",
        (
            d["batch_code"],
            d["work_order_ref"],
            d["material_description"],
            d["quantity"],
            d["quantity_unit"],
            d["recipe_revision_id"],
            d["machine_id"],
            d["planned_date"],
            d["actual_start"],
            d["actual_end"],
            d["notes"],
            now,
            now,
        ),
    )
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(BATCH_SELECT + " WHERE b.id = ?", (batch_id,)).fetchone())


def get_by_code(conn: sqlite3.Connection, code: str) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(BATCH_SELECT + " WHERE b.batch_code = ? COLLATE NOCASE", (code,)).fetchone())


def search(
    conn: sqlite3.Connection, filters: ReportFilters, limit: int | None = None, offset: int = 0
) -> list[dict[str, Any]]:
    where = Where()
    batch_conditions(filters, where, "b")
    sql = BATCH_SELECT + where.sql() + " ORDER BY b.created_at DESC, b.id DESC"
    params = list(where.params)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]
    return rows_to_dicts(conn.execute(sql, params).fetchall())


def count(conn: sqlite3.Connection, filters: ReportFilters) -> int:
    where = Where()
    batch_conditions(filters, where, "b")
    return int(conn.execute("SELECT COUNT(*) FROM batches b" + where.sql(), where.params).fetchone()[0])


def update(conn: sqlite3.Connection, batch_id: int, d: dict[str, Any], now: str) -> None:
    conn.execute(
        "UPDATE batches SET work_order_ref=?, material_description=?, quantity=?, quantity_unit=?, "
        "recipe_revision_id=?, machine_id=?, planned_date=?, actual_start=?, actual_end=?, "
        "notes=?, updated_at=? WHERE id=?",
        (
            d["work_order_ref"],
            d["material_description"],
            d["quantity"],
            d["quantity_unit"],
            d["recipe_revision_id"],
            d["machine_id"],
            d["planned_date"],
            d["actual_start"],
            d["actual_end"],
            d["notes"],
            now,
            batch_id,
        ),
    )


def set_status(
    conn: sqlite3.Connection, batch_id: int, status: str, actual_start: str | None, actual_end: str | None, now: str
) -> None:
    conn.execute(
        "UPDATE batches SET status=?, actual_start=?, actual_end=?, updated_at=? WHERE id=?",
        (status, actual_start, actual_end, now, batch_id),
    )


def list_options(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Light-weight list for batch selectors."""
    return rows_to_dicts(
        conn.execute(
            "SELECT id, batch_code, status, material_description FROM batches ORDER BY created_at DESC, id DESC"
        ).fetchall()
    )
