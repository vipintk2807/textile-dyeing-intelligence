"""Deterministic SYNTHETIC demonstration data.

Everything created here is illustrative only. It is not real factory data, not a validated
dyeing recipe and not a production benchmark. All identifiers start with ``SYN-`` so the
records are easy to recognise and can be removed again with :func:`remove_sample_data`.

The loader is never run by application start-up; it must be invoked explicitly.
"""

from __future__ import annotations

import sqlite3

from .database import transaction
from .errors import Conflict
from .services import batches, consumption, machines, process_records, quality, recipes, rework

SYNTHETIC_NOTE = "SYNTHETIC EXAMPLE - not real production data."
SAMPLE_PREFIX = "SYN-"
MARKER_BATCH = "SYN-B001"


def is_loaded(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM batches WHERE batch_code = ?", (MARKER_BATCH,)).fetchone()
    return row is not None


def has_non_sample_records(conn: sqlite3.Connection) -> bool:
    for table, column in (("batches", "batch_code"), ("machines", "machine_code"), ("recipes", "recipe_code")):
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE {column} NOT LIKE ? LIMIT 1",
            (SAMPLE_PREFIX + "%",),  # noqa: S608
        ).fetchone()
        if row is not None:
            return True
    return False


def _batch(conn: sqlite3.Connection, code: str) -> int:
    return int(conn.execute("SELECT id FROM batches WHERE batch_code = ?", (code,)).fetchone()[0])


def _start_finish(conn, batch_id: int, start: str, end: str | None) -> None:
    batches.change_status(conn, batch_id, "in_progress", actual_start=start)
    if end:
        batches.change_status(conn, batch_id, "completed", actual_end=end)


def _consume(conn, batch_id, material, category, qty, unit, when, basis=None):
    consumption.create_consumption_record(
        conn,
        {
            "batch_id": batch_id,
            "material_name": material,
            "category": category,
            "quantity": qty,
            "unit": unit,
            "basis": basis,
            "recorded_at": when,
            "notes": SYNTHETIC_NOTE,
        },
    )


def _process(conn, batch_id, name, value, unit, when):
    process_records.create_process_record(
        conn,
        {
            "batch_id": batch_id,
            "parameter_name": name,
            "value": value,
            "unit": unit,
            "observed_at": when,
            "notes": SYNTHETIC_NOTE,
        },
    )


def _inspect(conn, batch_id, kind, when, disposition, defects=(), measurements=()):
    return quality.create_inspection(
        conn,
        {
            "batch_id": batch_id,
            "inspection_type": kind,
            "inspected_at": when,
            "inspector": "SYN-INSPECTOR",
            "disposition": disposition,
            "notes": SYNTHETIC_NOTE,
            "defects": [{"category": d} for d in defects],
            "measurements": [dict(m) for m in measurements],
        },
    )


def load_sample_data(conn: sqlite3.Connection) -> dict[str, int]:
    """Create the synthetic dataset. Raises ``Conflict`` if it is already loaded."""
    if is_loaded(conn):
        raise Conflict("Synthetic sample data is already loaded. Nothing was changed.")

    for code, name, status in (
        ("SYN-M01", "Synthetic Jet Machine 1", "available"),
        ("SYN-M02", "Synthetic Jet Machine 2", "maintenance"),
        ("SYN-M03", "Synthetic Winch 3", "unavailable"),
    ):
        machines.create_machine(
            conn,
            {
                "machine_code": code,
                "name": name,
                "machine_type": "Synthetic example",
                "status": status,
                "notes": SYNTHETIC_NOTE,
            },
        )

    r1a = recipes.create_recipe(
        conn,
        {
            "recipe_code": "SYN-R01",
            "name": "Synthetic Recipe 1 (illustrative only)",
            "description": SYNTHETIC_NOTE,
            "applicable_material": "Synthetic cotton knit",
        },
        {
            "revision_code": "A",
            "description": "Illustrative first revision",
            "notes": SYNTHETIC_NOTE,
            "ingredients": [
                {"material_name": "Synthetic Dye A", "quantity": "2.5", "unit": "kg"},
                {"material_name": "Synthetic Salt", "quantity": "10", "unit": "kg"},
                {"material_name": "Synthetic Soda Ash", "quantity": "4", "unit": "kg"},
            ],
        },
    )
    r1b = recipes.add_revision(
        conn,
        r1a["recipe_id"],
        {
            "revision_code": "B",
            "description": "Illustrative revision with more dye",
            "notes": SYNTHETIC_NOTE,
            "ingredients": [
                {"material_name": "Synthetic Dye A", "quantity": "2.8", "unit": "kg"},
                {"material_name": "Synthetic Salt", "quantity": "10", "unit": "kg"},
                {"material_name": "Synthetic Soda Ash", "quantity": "4", "unit": "kg"},
            ],
        },
    )
    r2a = recipes.create_recipe(
        conn,
        {"recipe_code": "SYN-R02", "name": "Synthetic Recipe 2 (illustrative only)", "description": SYNTHETIC_NOTE},
        {
            "revision_code": "A",
            "notes": SYNTHETIC_NOTE,
            "ingredients": [
                {"material_name": "Synthetic Dye B", "quantity": "1.2", "unit": "kg"},
                {"material_name": "Synthetic Wetting Agent", "quantity": "0.5", "unit": "kg"},
            ],
        },
    )
    m = {r["machine_code"]: r["id"] for r in machines.list_machines(conn)}

    def new_batch(code, rev, machine, planned, qty="100"):
        return batches.create_batch(
            conn,
            {
                "batch_code": code,
                "work_order_ref": "SYN-WO-" + code[-3:],
                "material_description": "Synthetic cotton knit fabric",
                "quantity": qty,
                "quantity_unit": "kg",
                "recipe_revision_id": rev["id"] if rev else None,
                "machine_id": m.get(machine) if machine else None,
                "planned_date": planned,
                "notes": SYNTHETIC_NOTE,
            },
        )["id"]

    # B001: normal batch, passed inspection, +20 % salt variance
    b1 = new_batch("SYN-B001", r1a, "SYN-M01", "2026-03-02")
    _start_finish(conn, b1, "2026-03-02 08:00", "2026-03-02 12:00")
    _process(conn, b1, "Temperature", "60", "°C", "2026-03-02 09:00")
    _process(conn, b1, "Temperature", "80", "°C", "2026-03-02 10:00")
    _process(conn, b1, "pH", "10.5", None, "2026-03-02 09:30")
    _consume(conn, b1, "Synthetic Salt", "planned", "10", "kg", "2026-03-02 08:00")
    _consume(conn, b1, "Synthetic Salt", "actual", "12", "kg", "2026-03-02 11:00")
    _consume(conn, b1, "Synthetic Dye A", "planned", "2.5", "kg", "2026-03-02 08:00")
    _consume(conn, b1, "Synthetic Dye A", "actual", "2.5", "kg", "2026-03-02 11:00")
    _inspect(conn, b1, "Final shade check", "2026-03-02 14:00", "passed")

    # B002: failed inspection, rework, passed follow-up (history preserved)
    b2 = new_batch("SYN-B002", r1a, "SYN-M01", "2026-03-04")
    _start_finish(conn, b2, "2026-03-04 08:00", "2026-03-04 12:30")
    _process(conn, b2, "Temperature", "60", "°C", "2026-03-04 09:00")
    _consume(conn, b2, "Synthetic Dye A", "planned", "2.5", "kg", "2026-03-04 08:00")
    _consume(conn, b2, "Synthetic Dye A", "actual", "2.2", "kg", "2026-03-04 11:00")
    failed = _inspect(
        conn,
        b2,
        "Final shade check",
        "2026-03-04 15:00",
        "failed",
        defects=["Uneven shade (synthetic example)"],
        measurements=[{"name": "Shade difference", "value": "0", "unit": "units"}],
    )
    rw = rework.create_rework(
        conn,
        {"batch_id": b2, "inspection_id": failed["id"], "reason": "Uneven shade (synthetic)", "notes": SYNTHETIC_NOTE},
    )
    rework.update_rework(conn, rw["id"], {"status": "in_progress", "started_at": "2026-03-05 08:00"})
    rework.update_rework(
        conn,
        rw["id"],
        {
            "status": "completed",
            "completed_at": "2026-03-05 09:30",
            "corrective_description": "Synthetic corrective step (illustrative only).",
        },
    )
    _inspect(conn, b2, "Follow-up shade check", "2026-03-05 10:00", "passed")

    # B003: in progress, zero planned quantity and missing actual quantity
    b3 = new_batch("SYN-B003", r2a, "SYN-M02", "2026-03-06")
    batches.change_status(conn, b3, "in_progress", actual_start="2026-03-06 08:00")
    _process(conn, b3, "Temperature", "55", "°C", "2026-03-06 08:30")
    _consume(conn, b3, "Synthetic Wetting Agent", "planned", "0", "kg", "2026-03-06 08:00")
    _consume(conn, b3, "Synthetic Wetting Agent", "actual", "0.5", "kg", "2026-03-06 08:45")
    _consume(conn, b3, "Synthetic Dye B", "planned", "1.2", "kg", "2026-03-06 08:00")

    # B004: completed, inspection still pending, incompatible units
    b4 = new_batch("SYN-B004", r2a, "SYN-M01", "2026-03-09")
    _start_finish(conn, b4, "2026-03-09 08:00", "2026-03-09 11:00")
    _consume(conn, b4, "Synthetic Dye B", "planned", "5", "kg", "2026-03-09 08:00")
    _consume(conn, b4, "Synthetic Dye B", "actual", "5000", "g", "2026-03-09 10:00")
    _inspect(conn, b4, "Final shade check", "2026-03-09 13:00", "pending")

    # B005: planned only, newer recipe revision, no machine assigned yet
    new_batch("SYN-B005", r1b, None, "2026-03-20", qty="80")

    # B006: cancelled before start
    b6 = new_batch("SYN-B006", r2a, "SYN-M03", "2026-03-10", qty="60")
    batches.change_status(conn, b6, "cancelled")

    # B007: completed, failed (final), rework still required
    b7 = new_batch("SYN-B007", r1a, "SYN-M01", "2026-03-12")
    _start_finish(conn, b7, "2026-03-12 08:00", "2026-03-12 12:00")
    failed7 = _inspect(
        conn, b7, "Final shade check", "2026-03-12 14:00", "failed", defects=["Staining (synthetic example)"]
    )
    rework.create_rework(
        conn,
        {"batch_id": b7, "inspection_id": failed7["id"], "reason": "Staining (synthetic)", "notes": SYNTHETIC_NOTE},
    )
    return summary(conn)


def summary(conn: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "machines",
        "recipes",
        "recipe_revisions",
        "batches",
        "process_records",
        "consumption_records",
        "quality_inspections",
        "rework_records",
    )
    return {t: int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]) for t in tables}  # noqa: S608


def remove_sample_data(conn: sqlite3.Connection) -> int:
    """Delete only records whose identifiers start with ``SYN-`` (the deliberate reset).

    Returns the number of batches removed. Real records are never touched.
    """
    like = SAMPLE_PREFIX + "%"
    with transaction(conn):
        batch_ids = "SELECT id FROM batches WHERE batch_code LIKE ?"
        insp_ids = f"SELECT id FROM quality_inspections WHERE batch_id IN ({batch_ids})"
        removed = int(conn.execute(f"SELECT COUNT(*) FROM ({batch_ids})", (like,)).fetchone()[0])  # noqa: S608
        steps = [
            (f"DELETE FROM rework_records WHERE batch_id IN ({batch_ids})", (like,)),
            (f"DELETE FROM quality_measurements WHERE inspection_id IN ({insp_ids})", (like,)),
            (f"DELETE FROM quality_defects WHERE inspection_id IN ({insp_ids})", (like,)),
        ]
        for sql, params in steps:
            conn.execute(sql, params)
        # Finalised inspections are protected by a trigger; lift it for this transaction only
        # (DDL is transactional, so a failure restores it) and recreate it straight after.
        conn.execute("DROP TRIGGER IF EXISTS trg_inspection_final_no_delete")
        try:
            conn.execute(f"DELETE FROM quality_inspections WHERE batch_id IN ({batch_ids})", (like,))  # noqa: S608
        finally:
            conn.execute(_RECREATE_NO_DELETE_TRIGGER)
        conn.execute(
            f"DELETE FROM process_record_history WHERE process_record_id IN "
            f"(SELECT id FROM process_records WHERE batch_id IN ({batch_ids}))",
            (like,),
        )  # noqa: S608
        conn.execute(f"DELETE FROM process_records WHERE batch_id IN ({batch_ids})", (like,))  # noqa: S608
        conn.execute(f"DELETE FROM consumption_records WHERE batch_id IN ({batch_ids})", (like,))  # noqa: S608
        conn.execute("DELETE FROM batches WHERE batch_code LIKE ?", (like,))
        conn.execute(
            "DELETE FROM recipe_ingredients WHERE revision_id IN (SELECT rr.id FROM recipe_revisions rr "
            "JOIN recipes r ON r.id = rr.recipe_id WHERE r.recipe_code LIKE ?)",
            (like,),
        )
        conn.execute(
            "DELETE FROM recipe_revisions WHERE recipe_id IN (SELECT id FROM recipes WHERE recipe_code LIKE ?)", (like,)
        )
        conn.execute("DELETE FROM recipes WHERE recipe_code LIKE ?", (like,))
        conn.execute("DELETE FROM machines WHERE machine_code LIKE ?", (like,))
        conn.execute(
            "DELETE FROM chemical_materials WHERE name LIKE 'Synthetic %' AND id NOT IN "
            "(SELECT material_id FROM recipe_ingredients UNION SELECT material_id FROM consumption_records)"
        )
    return removed


_RECREATE_NO_DELETE_TRIGGER = """
CREATE TRIGGER trg_inspection_final_no_delete
BEFORE DELETE ON quality_inspections
WHEN OLD.disposition IN ('passed','failed')
BEGIN
    SELECT RAISE(ABORT, 'TDI: A finalised inspection cannot be deleted.');
END
"""
