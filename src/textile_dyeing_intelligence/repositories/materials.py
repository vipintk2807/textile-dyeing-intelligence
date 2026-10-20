from __future__ import annotations

import sqlite3
from typing import Any

from .common import next_code, row_to_dict, rows_to_dicts


def get_by_name(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute("SELECT * FROM chemical_materials WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    )


def get(conn: sqlite3.Connection, material_id: int) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM chemical_materials WHERE id = ?", (material_id,)).fetchone())


def insert(conn: sqlite3.Connection, name: str, now: str) -> int:
    code = next_code(conn, "chemical_materials", "material_code", "MAT", 4)
    cur = conn.execute(
        "INSERT INTO chemical_materials (material_code, name, description, status, created_at) "
        "VALUES (?, ?, NULL, 'active', ?)",
        (code, name, now),
    )
    return int(cur.lastrowid)


def list_materials(conn: sqlite3.Connection, include_archived: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM chemical_materials"
    if not include_archived:
        sql += " WHERE status = 'active'"
    return rows_to_dicts(conn.execute(sql + " ORDER BY name COLLATE NOCASE").fetchall())
