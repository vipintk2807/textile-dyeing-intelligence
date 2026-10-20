"""Helpers shared by repositories."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from typing import Any


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def next_code(conn: sqlite3.Connection, table: str, column: str, prefix: str, width: int = 5) -> str:
    """Next sequential identifier such as ``QI-00007``.

    Call inside the write transaction (``BEGIN IMMEDIATE`` serialises writers). ``table`` and
    ``column`` are internal constants, never user input.
    """
    start = len(prefix) + 2  # 1-based SUBSTR position after "<prefix>-"
    row = conn.execute(
        f"SELECT MAX(CAST(SUBSTR({column}, ?) AS INTEGER)) FROM {table} WHERE {column} LIKE ?",  # noqa: S608
        (start, f"{prefix}-%"),
    ).fetchone()
    return f"{prefix}-{(row[0] or 0) + 1:0{width}d}"
