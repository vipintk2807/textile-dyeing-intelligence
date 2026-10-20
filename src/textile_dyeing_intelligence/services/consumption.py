from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from typing import Any

from ..calculations import compute_variance, normalise_unit
from ..database import transaction
from ..errors import ValidationFailure
from ..filters import ReportFilters, Where, batch_conditions
from ..repositories import batches as batches_repo
from ..repositories import consumption as repo
from ..timeutil import now_iso
from ..validation import ConsumptionInput, validate_model
from . import materials


def create_consumption_record(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
    record = validate_model(ConsumptionInput, data)
    if batches_repo.get(conn, record.batch_id) is None:
        raise ValidationFailure({"batch_id": "Selected batch does not exist. Select a valid batch."})
    with transaction(conn):
        material_id = materials.get_or_create(conn, record.material_name)
        record_id = repo.insert(conn, record.model_dump(), material_id, now_iso())
    rows = repo.list_records(conn, extra_where="c.id = ?", extra_params=[record_id])
    return rows[0]


def list_consumption_records(conn: sqlite3.Connection, **filters: Any) -> list[dict[str, Any]]:
    return repo.list_records(conn, **filters)


# --- Planned vs actual comparison -------------------------------------------------------


def _group_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine records of one category. Mixed units or bases make the group incompatible."""
    if not records:
        return {"total": None, "unit": None, "basis": None, "count": 0, "conflict": None}
    units = {normalise_unit(r["unit"]) for r in records}
    bases = {(r["basis"] or "").strip().casefold() for r in records}
    conflict = None
    if len(units) > 1:
        conflict = "records use more than one unit"
    elif len(bases) > 1:
        conflict = "records use more than one measurement basis"
    total = sum((Decimal(r["quantity"]) for r in records), Decimal(0))
    return {
        "total": total,
        "unit": records[0]["unit"],
        "basis": records[0]["basis"] or None,
        "count": len(records),
        "conflict": conflict,
    }


def compare_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group consumption records by batch and material and compute variances.

    Different materials are never combined. Multiple records in the same category for the
    same batch and material are summed only when their units and bases agree.
    """
    groups: dict[tuple[int, int], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: {"planned": [], "actual": []})
    names: dict[tuple[int, int], tuple[str, str]] = {}
    for r in records:
        key = (r["batch_id"], r["material_id"])
        groups[key][r["category"]].append(r)
        names[key] = (r["batch_code"], r["material_name"])

    rows: list[dict[str, Any]] = []
    for key in sorted(groups, key=lambda k: (names[k][0].casefold(), names[k][1].casefold())):
        planned = _group_summary(groups[key]["planned"])
        actual = _group_summary(groups[key]["actual"])
        conflict = planned["conflict"] or actual["conflict"]
        if conflict:
            status, absolute, percent, unit = "incompatible", None, None, None
            message = f"Comparison unavailable: the {('planned' if planned['conflict'] else 'actual')} {conflict}."
        else:
            variance = compute_variance(
                planned["total"],
                actual["total"],
                planned_unit=planned["unit"],
                actual_unit=actual["unit"],
                planned_basis=planned["basis"],
                actual_basis=actual["basis"],
            )
            status, absolute, percent = variance.status, variance.absolute, variance.percent
            unit, message = variance.unit, variance.message
        rows.append(
            {
                "batch_id": key[0],
                "batch_code": names[key][0],
                "material_id": key[1],
                "material_name": names[key][1],
                "planned_total": planned["total"],
                "planned_unit": planned["unit"],
                "planned_basis": planned["basis"],
                "planned_count": planned["count"],
                "actual_total": actual["total"],
                "actual_unit": actual["unit"],
                "actual_basis": actual["basis"],
                "actual_count": actual["count"],
                "status": status,
                "variance": absolute,
                "variance_percent": percent,
                "variance_unit": unit,
                "message": message,
            }
        )
    return rows


def compare_for_batch(conn: sqlite3.Connection, batch_id: int) -> list[dict[str, Any]]:
    return compare_records(repo.list_records(conn, batch_id=batch_id))


def compare_for_filters(conn: sqlite3.Connection, filters: ReportFilters) -> list[dict[str, Any]]:
    """Comparison report scope: batch-level filters plus the recording-date range and
    material filter, applied identically to the displayed table and the CSV export."""
    filters = filters.validated()
    where = Where()
    batch_conditions(replace(filters, start_date=None, end_date=None), where, "b")
    extra, params = "", []
    if where.clauses:
        extra = "c.batch_id IN (SELECT b.id FROM batches b" + where.sql() + ")"
        params = list(where.params)
    records = repo.list_records(
        conn,
        material=filters.material,
        start_date=filters.start_date,
        end_date=filters.end_date,
        extra_where=extra,
        extra_params=params,
    )
    return compare_records(records)


def compare_for_batch_ids(conn: sqlite3.Connection, batch_ids: list[int]) -> list[dict[str, Any]]:
    if not batch_ids:
        return []
    records: list[dict[str, Any]] = []
    for start in range(0, len(batch_ids), 500):
        chunk = batch_ids[start : start + 500]
        marks = ",".join("?" for _ in chunk)
        records.extend(repo.list_records(conn, extra_where=f"c.batch_id IN ({marks})", extra_params=list(chunk)))
    return compare_records(records)
