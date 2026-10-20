"""Filtered operational reports. Each returns a :class:`Report` whose rows feed both the
on-screen table and the CSV export, so the two always show the same dataset."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any

from .. import constants as c
from ..calculations import InspectionOutcome, final_outcome, rate_percent
from ..decimals import round_for_display
from ..filters import ReportFilters, Where, batch_conditions
from ..repositories import machines as machines_repo
from ..repositories import quality as quality_repo
from ..repositories import rework as rework_repo
from ..services import batches as batches_service
from ..services import consumption as consumption_service
from ..services import rework as rework_service

UNAVAILABLE = "Unavailable"


@dataclass
class Report:
    key: str
    title: str
    columns: list[str]
    rows: list[dict[str, Any]]
    date_basis: str
    notes: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _batch_subquery(filters: ReportFilters) -> tuple[str, list[Any]]:
    """Batch-level conditions (no date) as a ``batch_id IN (...)`` clause for child tables."""
    where = Where()
    batch_conditions(replace(filters, start_date=None, end_date=None), where, "b")
    if not where.clauses:
        return "", []
    return "{alias}.batch_id IN (SELECT b.id FROM batches b" + where.sql() + ")", list(where.params)


# --- Batch production --------------------------------------------------------------------


def batch_production_report(conn: sqlite3.Connection, filters: ReportFilters) -> Report:
    filters = filters.validated()
    batches, _ = batches_service.search_batches(conn, filters)
    columns = [
        "Batch ID",
        "Work-order reference",
        "Fabric / material",
        "Quantity",
        "Quantity unit",
        "Recipe",
        "Recipe revision",
        "Machine",
        "Production status",
        "Reporting date",
        "Planned date",
        "Actual start",
        "Actual completion",
        "Quality (latest final outcome)",
        "Rework events (excluding cancelled)",
    ]
    rows = [
        {
            "Batch ID": b["batch_code"],
            "Work-order reference": b["work_order_ref"],
            "Fabric / material": b["material_description"],
            "Quantity": Decimal(b["quantity"]),
            "Quantity unit": b["quantity_unit"],
            "Recipe": b["recipe_code"],
            "Recipe revision": b["revision_code"],
            "Machine": b["machine_code"],
            "Production status": c.BATCH_STATUS_LABELS[b["status"]],
            "Reporting date": b["reporting_date"],
            "Planned date": b["planned_date"],
            "Actual start": b["actual_start"],
            "Actual completion": b["actual_end"],
            "Quality (latest final outcome)": b["quality_label"],
            "Rework events (excluding cancelled)": b["rework_events"],
        }
        for b in batches
    ]
    return Report(
        "batch_production",
        "Batch production report",
        columns,
        rows,
        date_basis="Batch reporting date (actual start, else planned date, else creation date)",
    )


# --- Chemical consumption ------------------------------------------------------------------


def consumption_comparison_report(conn: sqlite3.Connection, filters: ReportFilters) -> Report:
    filters = filters.validated()
    comparisons = consumption_service.compare_for_filters(conn, filters)
    columns = [
        "Batch ID",
        "Material",
        "Planned quantity",
        "Planned unit",
        "Actual quantity",
        "Actual unit",
        "Variance (actual - planned)",
        "Variance unit",
        "Variance (%)",
        "Comparison status",
        "Note",
    ]
    status_text = {"ok": "Compared", "incomplete": "Incomplete data", "incompatible": "Not comparable"}
    rows = []
    for r in comparisons:
        ok = r["status"] == "ok"
        percent = r["variance_percent"]
        rows.append(
            {
                "Batch ID": r["batch_code"],
                "Material": r["material_name"],
                "Planned quantity": r["planned_total"],
                "Planned unit": r["planned_unit"],
                "Actual quantity": r["actual_total"],
                "Actual unit": r["actual_unit"],
                "Variance (actual - planned)": r["variance"] if ok else UNAVAILABLE,
                "Variance unit": r["variance_unit"] if ok else None,
                "Variance (%)": round_for_display(percent, 2) if percent is not None else UNAVAILABLE,
                "Comparison status": status_text[r["status"]],
                "Note": r["message"] or None,
            }
        )
    return Report(
        "consumption_comparison",
        "Planned versus actual chemical consumption",
        columns,
        rows,
        date_basis="Consumption recording date",
        notes=[
            "Variance = actual - planned; Variance (%) = (actual - planned) / planned x 100, "
            "rounded to 2 decimal places for display. Percentage is unavailable when planned is zero.",
            "Only like-for-like comparisons are calculated (same material, unit and basis). "
            "Different materials are never combined.",
        ],
    )


def consumption_records_report(conn: sqlite3.Connection, filters: ReportFilters) -> Report:
    filters = filters.validated()
    extra, params = _batch_subquery(filters)
    records = consumption_service.list_consumption_records(
        conn,
        material=filters.material,
        start_date=filters.start_date,
        end_date=filters.end_date,
        extra_where=extra.format(alias="c") if extra else "",
        extra_params=params,
    )
    columns = ["Batch ID", "Material", "Category", "Quantity", "Unit", "Measurement basis", "Recorded at", "Notes"]
    rows = [
        {
            "Batch ID": r["batch_code"],
            "Material": r["material_name"],
            "Category": c.CONSUMPTION_CATEGORY_LABELS[r["category"]],
            "Quantity": Decimal(r["quantity"]),
            "Unit": r["unit"],
            "Measurement basis": r["basis"] or None,
            "Recorded at": r["recorded_at"],
            "Notes": r["notes"],
        }
        for r in records
    ]
    return Report(
        "consumption_records", "Chemical consumption records", columns, rows, date_basis="Consumption recording date"
    )


# --- Quality -------------------------------------------------------------------------------


def _measure_text(items: list[dict[str, Any]]) -> str | None:
    if not items:
        return None
    return "; ".join(f"{m['name']}: {m['value']}" + (f" {m['unit']}" if m["unit"] else "") for m in items)


def quality_report(conn: sqlite3.Connection, filters: ReportFilters) -> Report:
    """Inspection records plus a batch-based failure indicator.

    The indicator uses the inspections inside the active filters (outcome filter excluded):
    each batch's final outcome is its most recent finalised inspection among them.
    """
    filters = filters.validated()
    extra, params = _batch_subquery(filters)
    extra_sql = extra.format(alias="q") if extra else ""
    all_rows = quality_repo.list_inspections(
        conn,
        start_date=filters.start_date,
        end_date=filters.end_date,
        extra_where=extra_sql,
        extra_params=params,
    )
    by_batch: dict[int, list[InspectionOutcome]] = {}
    for r in all_rows:
        by_batch.setdefault(r["batch_id"], []).append(InspectionOutcome(r["id"], r["inspected_at"], r["disposition"]))
    outcomes = {b: final_outcome(items) for b, items in by_batch.items()}
    eligible = [b for b, o in outcomes.items() if o is not None]
    failed = [b for b in eligible if outcomes[b] == "failed"]

    shown = [r for r in all_rows if not filters.inspection_outcome or r["disposition"] == filters.inspection_outcome]
    columns = [
        "Inspection ID",
        "Batch ID",
        "Inspection type",
        "Inspected at",
        "Inspector",
        "Outcome",
        "Measurements",
        "Defects",
        "Notes",
    ]
    rows = []
    for r in shown:
        defects = quality_repo.defects(conn, r["id"])
        rows.append(
            {
                "Inspection ID": r["inspection_code"],
                "Batch ID": r["batch_code"],
                "Inspection type": r["inspection_type"],
                "Inspected at": r["inspected_at"],
                "Inspector": r["inspector"],
                "Outcome": c.QUALITY_DISPOSITION_LABELS[r["disposition"]],
                "Measurements": _measure_text(quality_repo.measurements(conn, r["id"])),
                "Defects": "; ".join(d["category"] for d in defects) or None,
                "Notes": r["notes"],
            }
        )
    counts = {d: sum(1 for r in all_rows if r["disposition"] == d) for d in c.QUALITY_DISPOSITIONS}
    return Report(
        "quality",
        "Quality inspection report",
        columns,
        rows,
        date_basis="Inspection date and time",
        notes=[
            "A batch's final outcome is its most recent finalised (passed/failed) inspection "
            "within the selected scope. Batches with only pending or no inspections have no "
            "final outcome and are excluded from the failure rate, never counted as passed.",
        ],
        summary={
            "inspections": len(all_rows),
            "by_disposition": counts,
            "batches_inspected": len(by_batch),
            "batches_with_final_outcome": len(eligible),
            "batches_final_failed": len(failed),
            "failure_rate": rate_percent(len(failed), len(eligible)),
            "outcome_filter_active": bool(filters.inspection_outcome),
        },
    )


# --- Rework --------------------------------------------------------------------------------


def rework_report(conn: sqlite3.Connection, filters: ReportFilters) -> Report:
    filters = filters.validated()
    extra, params = _batch_subquery(filters)
    records = rework_repo.list_records(
        conn,
        status=filters.rework_status,
        start_date=filters.start_date,
        end_date=filters.end_date,
        extra_where=extra.format(alias="w") if extra else "",
        extra_params=params,
    )
    records = rework_service.with_subsequent_inspection(conn, records)
    columns = [
        "Rework ID",
        "Batch ID",
        "Related inspection",
        "Related inspection outcome",
        "Reason",
        "Rework status",
        "Started",
        "Completed",
        "Corrective work",
        "Subsequent inspection",
        "Subsequent inspection outcome",
    ]
    rows = []
    for r in records:
        sub = r["subsequent_inspection"]
        if not r["subsequent_available"]:
            sub_id = sub_outcome = UNAVAILABLE
        elif sub is None:
            sub_id = sub_outcome = "None recorded yet"
        else:
            sub_id = sub["inspection_code"]
            sub_outcome = c.QUALITY_DISPOSITION_LABELS[sub["disposition"]]
        rows.append(
            {
                "Rework ID": r["rework_code"],
                "Batch ID": r["batch_code"],
                "Related inspection": r["related_inspection_code"],
                "Related inspection outcome": (
                    c.QUALITY_DISPOSITION_LABELS[r["related_inspection_disposition"]]
                    if r["related_inspection_disposition"]
                    else None
                ),
                "Reason": r["reason"],
                "Rework status": c.REWORK_STATUS_LABELS[r["status"]],
                "Started": r["started_at"],
                "Completed": r["completed_at"],
                "Corrective work": r["corrective_description"],
                "Subsequent inspection": sub_id,
                "Subsequent inspection outcome": sub_outcome,
            }
        )
    distinct = len({r["batch_id"] for r in records if r["status"] != "cancelled"})
    return Report(
        "rework",
        "Rework report",
        columns,
        rows,
        date_basis="Rework start date, else record creation date",
        notes=[
            "Subsequent inspection = first finalised inspection of the same batch recorded after "
            "the linked inspection. It is unavailable when no inspection is linked. "
            "Completed rework does not mean the batch passed inspection.",
        ],
        summary={
            "events": len(records),
            "events_excluding_cancelled": sum(1 for r in records if r["status"] != "cancelled"),
            "distinct_batches": distinct,
        },
    )


# --- Machine activity ----------------------------------------------------------------------


def machine_activity_report(conn: sqlite3.Connection, filters: ReportFilters) -> Report:
    """Recorded batches per machine. This is a record count, not a utilisation measure."""
    filters = filters.validated()
    batches, _ = batches_service.search_batches(conn, filters)
    machines = machines_repo.list_machines(conn)
    if filters.machine_id:
        machines = [m for m in machines if m["id"] == filters.machine_id]
    columns = [
        "Machine ID",
        "Machine name",
        "Recorded machine status",
        "Batches recorded",
        "Planned",
        "In progress",
        "Completed",
        "Cancelled",
    ]

    def counts(items: list[dict[str, Any]]) -> dict[str, int]:
        return {s: sum(1 for b in items if b["status"] == s) for s in c.BATCH_STATUSES}

    rows = []
    for m in machines:
        mine = [b for b in batches if b["machine_id"] == m["id"]]
        n = counts(mine)
        rows.append(
            {
                "Machine ID": m["machine_code"],
                "Machine name": m["name"],
                "Recorded machine status": c.MACHINE_STATUS_LABELS[m["status"]],
                "Batches recorded": len(mine),
                "Planned": n["planned"],
                "In progress": n["in_progress"],
                "Completed": n["completed"],
                "Cancelled": n["cancelled"],
            }
        )
    if not filters.machine_id:
        unassigned = [b for b in batches if b["machine_id"] is None]
        n = counts(unassigned)
        rows.append(
            {
                "Machine ID": "(none)",
                "Machine name": "No machine assigned",
                "Recorded machine status": None,
                "Batches recorded": len(unassigned),
                "Planned": n["planned"],
                "In progress": n["in_progress"],
                "Completed": n["completed"],
                "Cancelled": n["cancelled"],
            }
        )
    return Report(
        "machine_activity",
        "Machine activity report",
        columns,
        rows,
        date_basis="Batch reporting date (actual start, else planned date, else creation date)",
        notes=["Counts of recorded batches only. Utilisation, productivity and capacity efficiency are not measured."],
    )


REPORT_BUILDERS = {
    "batch_production": batch_production_report,
    "consumption_comparison": consumption_comparison_report,
    "consumption_records": consumption_records_report,
    "quality": quality_report,
    "rework": rework_report,
    "machine_activity": machine_activity_report,
}
