from __future__ import annotations

import sqlite3
from typing import Any

from ..filters import like_pattern
from .common import row_to_dict, rows_to_dicts


def insert_recipe(conn: sqlite3.Connection, d: dict[str, Any], now: str) -> int:
    cur = conn.execute(
        "INSERT INTO recipes (recipe_code, name, description, applicable_material, status, "
        "created_at, updated_at) VALUES (?,?,?,?, 'active', ?, ?)",
        (d["recipe_code"], d["name"], d["description"], d["applicable_material"], now, now),
    )
    return int(cur.lastrowid)


def insert_revision(conn: sqlite3.Connection, recipe_id: int, d: dict[str, Any], now: str) -> int:
    cur = conn.execute(
        "INSERT INTO recipe_revisions (recipe_id, revision_code, description, effective_date, "
        "status, notes, created_at) VALUES (?,?,?,?, 'active', ?, ?)",
        (recipe_id, d["revision_code"], d["description"], d["effective_date"], d["notes"], now),
    )
    return int(cur.lastrowid)


def insert_ingredient(
    conn: sqlite3.Connection, revision_id: int, material_id: int, position: int, d: dict[str, Any]
) -> None:
    conn.execute(
        "INSERT INTO recipe_ingredients (revision_id, material_id, position, quantity, unit, "
        "dosing_basis, notes) VALUES (?,?,?,?,?,?,?)",
        (revision_id, material_id, position, d["quantity"], d["unit"], d["dosing_basis"], d["notes"]),
    )


def get_recipe(conn: sqlite3.Connection, recipe_id: int) -> dict[str, Any] | None:
    return row_to_dict(conn.execute("SELECT * FROM recipes WHERE id=?", (recipe_id,)).fetchone())


def get_revision(conn: sqlite3.Connection, revision_id: int) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            "SELECT rr.*, r.recipe_code, r.name AS recipe_name, r.status AS recipe_status, "
            "(SELECT COUNT(*) FROM batches b WHERE b.recipe_revision_id = rr.id) AS batch_count "
            "FROM recipe_revisions rr JOIN recipes r ON r.id = rr.recipe_id WHERE rr.id=?",
            (revision_id,),
        ).fetchone()
    )


def list_recipes(
    conn: sqlite3.Connection, search: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    sql = (
        "SELECT r.*, (SELECT COUNT(*) FROM recipe_revisions rr WHERE rr.recipe_id = r.id) "
        "AS revision_count FROM recipes r"
    )
    clauses, params = [], []
    if search:
        clauses.append("(r.recipe_code LIKE ? ESCAPE '\\' OR r.name LIKE ? ESCAPE '\\')")
        params += [like_pattern(search)] * 2
    if status:
        clauses.append("r.status = ?")
        params.append(status)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return rows_to_dicts(conn.execute(sql + " ORDER BY r.recipe_code", params).fetchall())


def list_revisions(conn: sqlite3.Connection, recipe_id: int) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT rr.*, (SELECT COUNT(*) FROM batches b WHERE b.recipe_revision_id = rr.id) "
            "AS batch_count FROM recipe_revisions rr WHERE rr.recipe_id=? ORDER BY rr.id",
            (recipe_id,),
        ).fetchall()
    )


def list_ingredients(conn: sqlite3.Connection, revision_id: int) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            "SELECT ri.*, m.name AS material_name, m.material_code FROM recipe_ingredients ri "
            "JOIN chemical_materials m ON m.id = ri.material_id "
            "WHERE ri.revision_id=? ORDER BY ri.position",
            (revision_id,),
        ).fetchall()
    )


def selectable_revisions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Revisions available for new batches: active revision of an active recipe."""
    return rows_to_dicts(
        conn.execute(
            "SELECT rr.id, rr.revision_code, r.recipe_code, r.name AS recipe_name "
            "FROM recipe_revisions rr JOIN recipes r ON r.id = rr.recipe_id "
            "WHERE rr.status='active' AND r.status='active' ORDER BY r.recipe_code, rr.id"
        ).fetchall()
    )


def set_recipe_status(conn: sqlite3.Connection, recipe_id: int, status: str, now: str) -> None:
    conn.execute("UPDATE recipes SET status=?, updated_at=? WHERE id=?", (status, now, recipe_id))


def set_revision_status(conn: sqlite3.Connection, revision_id: int, status: str) -> None:
    conn.execute("UPDATE recipe_revisions SET status=? WHERE id=?", (status, revision_id))
