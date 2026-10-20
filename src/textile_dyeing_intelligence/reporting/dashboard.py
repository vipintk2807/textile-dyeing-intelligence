from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from ..filters import ReportFilters
from ..repositories import batches as batches_repo
from ..services import batches as batches_service
from ..services import consumption as consumption_service
from .metrics import BatchMetrics, batch_metrics


@dataclass(frozen=True)
class Dashboard:
    metrics: BatchMetrics
    comparable: int
    incomplete: int
    incompatible: int
    comparisons: list[dict[str, Any]]
    recent_batches: list[dict[str, Any]]
    is_empty: bool


def build_dashboard(conn: sqlite3.Connection, filters: ReportFilters, recent: int = 10) -> Dashboard:
    """All values are calculated from stored records using the documented definitions."""
    filters = filters.validated()
    metrics = batch_metrics(conn, filters)
    batch_ids = [r["id"] for r in batches_repo.search(conn, filters)]
    comparisons = consumption_service.compare_for_batch_ids(conn, batch_ids)
    recent_rows, _ = batches_service.search_batches(conn, filters, limit=recent)
    return Dashboard(
        metrics=metrics,
        comparable=sum(1 for r in comparisons if r["status"] == "ok"),
        incomplete=sum(1 for r in comparisons if r["status"] == "incomplete"),
        incompatible=sum(1 for r in comparisons if r["status"] == "incompatible"),
        comparisons=comparisons,
        recent_batches=recent_rows,
        is_empty=metrics.total_batches == 0,
    )
