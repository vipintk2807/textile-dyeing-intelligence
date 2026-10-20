"""Report and list filters, with the SQL conditions they translate to."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .errors import ValidationFailure
from .timeutil import parse_date

#: Reporting date of a batch: actual start date, else planned date, else creation date.
BATCH_DATE_SQL = "COALESCE(substr({a}.actual_start, 1, 10), {a}.planned_date, substr({a}.created_at, 1, 10))"

#: Final quality outcome of a batch (latest finalised inspection), see calculations.final_outcome.
FINAL_OUTCOME_SQL = (
    "(SELECT q.disposition FROM quality_inspections q WHERE q.batch_id = {a}.id "
    "AND q.disposition IN ('passed','failed') ORDER BY q.inspected_at DESC, q.id DESC LIMIT 1)"
)


def batch_date_sql(alias: str = "b") -> str:
    return BATCH_DATE_SQL.format(a=alias)


def final_outcome_sql(alias: str = "b") -> str:
    return FINAL_OUTCOME_SQL.format(a=alias)


def like_pattern(text: str) -> str:
    """Escape LIKE wildcards; use with ``ESCAPE '\\'``."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class Where:
    """Small helper to assemble parameterised WHERE clauses."""

    def __init__(self) -> None:
        self.clauses: list[str] = []
        self.params: list[object] = []

    def add(self, clause: str, *params: object) -> None:
        self.clauses.append(clause)
        self.params.extend(params)

    def sql(self) -> str:
        return (" WHERE " + " AND ".join(self.clauses)) if self.clauses else ""


@dataclass(frozen=True)
class ReportFilters:
    """Filters shared by lists, the dashboard and reports. ``None`` means "no filter"."""

    start_date: str | None = None
    end_date: str | None = None
    search: str | None = None  # batch identifier or work-order reference (substring)
    machine_id: int | None = None
    recipe_id: int | None = None
    status: str | None = None  # production status
    inspection_outcome: str | None = None
    rework_status: str | None = None
    material: str | None = None  # chemical or material name (substring)

    def validated(self) -> ReportFilters:
        """Normalise dates and reject invalid ranges instead of silently ignoring them."""
        start = end = None
        errors: dict[str, str] = {}
        try:
            start = parse_date(self.start_date) if self.start_date else None
        except ValueError as exc:
            errors["start_date"] = f"Start date {exc}"
        try:
            end = parse_date(self.end_date) if self.end_date else None
        except ValueError as exc:
            errors["end_date"] = f"End date {exc}"
        if not errors and start and end and start > end:
            errors["end_date"] = "End date must not be earlier than the start date."
        if errors:
            raise ValidationFailure(errors)
        search = (self.search or "").strip() or None
        material = (self.material or "").strip() or None
        return replace(self, start_date=start, end_date=end, search=search, material=material)

    def describe(self) -> list[str]:
        """Human-readable list of active filters (for on-screen scope notes)."""
        parts: list[str] = []
        if self.start_date or self.end_date:
            parts.append(f"dates {self.start_date or '…'} to {self.end_date or '…'}")
        for label, value in (
            ("search", self.search),
            ("production status", self.status),
            ("inspection outcome", self.inspection_outcome),
            ("rework status", self.rework_status),
            ("material", self.material),
        ):
            if value:
                parts.append(f"{label}: {value}")
        if self.machine_id:
            parts.append("machine filter")
        if self.recipe_id:
            parts.append("recipe filter")
        return parts


def batch_conditions(filters: ReportFilters, where: Where, alias: str = "b") -> None:
    """Add the batch-level conditions of ``filters`` (alias must refer to ``batches``)."""
    f = filters
    if f.search:
        pattern = like_pattern(f.search)
        where.add(
            f"({alias}.batch_code LIKE ? ESCAPE '\\' OR {alias}.work_order_ref LIKE ? ESCAPE '\\')",
            pattern,
            pattern,
        )
    if f.status:
        where.add(f"{alias}.status = ?", f.status)
    if f.machine_id:
        where.add(f"{alias}.machine_id = ?", f.machine_id)
    if f.recipe_id:
        where.add(
            f"{alias}.recipe_revision_id IN (SELECT id FROM recipe_revisions WHERE recipe_id = ?)",
            f.recipe_id,
        )
    date_expr = batch_date_sql(alias)
    if f.start_date:
        where.add(f"{date_expr} >= ?", f.start_date)
    if f.end_date:
        where.add(f"{date_expr} <= ?", f.end_date)
