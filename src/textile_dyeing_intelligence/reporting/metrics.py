"""Batch-level indicators shared by the dashboard and the reports.

Documented definitions
----------------------
* **Population** - batches matching the active filters (date filter applies to the batch
  reporting date: actual start, else planned date, else creation date).
* **Rate population** - population excluding cancelled batches.
* **Final quality outcome** - disposition of the batch's most recent finalised inspection;
  pending inspections are ignored and a batch without one has *no* final outcome.
* **Quality failure rate** - batches whose final outcome is failed / batches with a final
  outcome. Each batch is counted once however many inspections it has.
* **Rework rate** - distinct batches with at least one non-cancelled rework event / rate
  population. Rework *events* are reported separately.
* **Awaiting quality outcome** - completed batches with no final outcome.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from .. import constants as c
from ..calculations import rate_percent
from ..filters import ReportFilters, Where, batch_conditions, final_outcome_sql


@dataclass(frozen=True)
class BatchMetrics:
    total_batches: int
    status_counts: dict[str, int]
    rate_population: int
    awaiting_quality_outcome: int
    batches_with_failed_inspection: int
    batches_with_final_outcome: int
    batches_final_failed: int
    failure_rate: Decimal | None
    batches_with_rework: int
    rework_events: int
    rework_rate: Decimal | None
    batches_with_open_rework: int


_QUERY = f"""
SELECT b.id, b.status,
       {final_outcome_sql("b")} AS final_outcome,
       EXISTS (SELECT 1 FROM quality_inspections q
                WHERE q.batch_id = b.id AND q.disposition = 'failed') AS any_failed,
       (SELECT COUNT(*) FROM rework_records w
         WHERE w.batch_id = b.id AND w.status <> 'cancelled') AS rework_events,
       (SELECT COUNT(*) FROM rework_records w
         WHERE w.batch_id = b.id AND w.status IN ('required','in_progress')) AS open_rework
FROM batches b
"""


def population_rows(conn: sqlite3.Connection, filters: ReportFilters) -> list[sqlite3.Row]:
    where = Where()
    batch_conditions(filters.validated(), where, "b")
    return conn.execute(_QUERY + where.sql(), where.params).fetchall()


def batch_metrics(conn: sqlite3.Connection, filters: ReportFilters) -> BatchMetrics:
    rows = population_rows(conn, filters)
    status_counts = dict.fromkeys(c.BATCH_STATUSES, 0)
    for r in rows:
        status_counts[r["status"]] += 1
    active = [r for r in rows if r["status"] != "cancelled"]
    with_outcome = [r for r in active if r["final_outcome"] is not None]
    final_failed = sum(1 for r in with_outcome if r["final_outcome"] == "failed")
    with_rework = sum(1 for r in active if r["rework_events"] > 0)
    return BatchMetrics(
        total_batches=len(rows),
        status_counts=status_counts,
        rate_population=len(active),
        awaiting_quality_outcome=sum(1 for r in active if r["status"] == "completed" and r["final_outcome"] is None),
        batches_with_failed_inspection=sum(1 for r in active if r["any_failed"]),
        batches_with_final_outcome=len(with_outcome),
        batches_final_failed=final_failed,
        failure_rate=rate_percent(final_failed, len(with_outcome)),
        batches_with_rework=with_rework,
        rework_events=sum(r["rework_events"] for r in active),
        rework_rate=rate_percent(with_rework, len(active)),
        batches_with_open_rework=sum(1 for r in active if r["open_rework"] > 0),
    )
