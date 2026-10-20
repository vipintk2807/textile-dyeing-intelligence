from __future__ import annotations

import re
import sqlite3
from typing import Any

from ..errors import ValidationFailure
from ..repositories import materials as repo
from ..timeutil import now_iso


def normalise_name(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip()


def get_or_create(conn: sqlite3.Connection, name: str) -> int:
    """Return the material id for ``name`` (case-insensitive), creating it when new.

    Must be called inside the caller's transaction so a failed write also discards the
    new catalogue entry.
    """
    clean = normalise_name(name)
    if not clean:
        raise ValidationFailure({"material_name": "Material is required."})
    existing = repo.get_by_name(conn, clean)
    if existing is not None:
        return int(existing["id"])
    return repo.insert(conn, clean, now_iso())


def list_materials(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return repo.list_materials(conn)
