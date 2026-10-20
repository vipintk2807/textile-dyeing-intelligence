import csv
import io
from decimal import Decimal

import pytest

from tests.fixtures.sample_records import make_batch, make_inspection
from textile_dyeing_intelligence import sample_data
from textile_dyeing_intelligence.errors import Conflict, ValidationFailure
from textile_dyeing_intelligence.filters import ReportFilters
from textile_dyeing_intelligence.reporting import dashboard, reports
from textile_dyeing_intelligence.reporting.export import rows_to_csv
from textile_dyeing_intelligence.services import batches, consumption


def parse_csv(data: bytes):
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


@pytest.fixture
def demo(conn):
    sample_data.load_sample_data(conn)
    return conn


def test_empty_database_dashboard_and_reports(conn):
    d = dashboard.build_dashboard(conn, ReportFilters())
    assert d.is_empty and d.metrics.failure_rate is None and d.metrics.rework_rate is None
    for build in reports.REPORT_BUILDERS.values():
        rep = build(conn, ReportFilters())
        if rep.key != "machine_activity":
            assert rep.rows == []
        assert parse_csv(rows_to_csv(rep.columns, rep.rows))[0] == rep.columns


def test_dashboard_values_match_known_sample_data(demo):
    d = dashboard.build_dashboard(demo, ReportFilters())
    m = d.metrics
    assert m.total_batches == 7 and m.status_counts == {"planned": 1, "in_progress": 1, "completed": 4, "cancelled": 1}
    assert m.rate_population == 6
    assert m.awaiting_quality_outcome == 1  # B004 (only pending); B002/B001 passed, B007 failed
    assert m.batches_with_failed_inspection == 2  # B002 (earlier failure) and B007
    assert (m.batches_with_final_outcome, m.batches_final_failed) == (3, 1)
    assert m.failure_rate == Decimal(1) / Decimal(3) * 100
    assert (m.batches_with_rework, m.rework_events, m.batches_with_open_rework) == (2, 2, 1)
    assert (d.comparable, d.incomplete, d.incompatible) == (4, 1, 1)


def test_dashboard_filters_change_population_consistently(demo):
    d = dashboard.build_dashboard(demo, ReportFilters(status="completed"))
    assert d.metrics.total_batches == 4 and d.metrics.status_counts["planned"] == 0
    d = dashboard.build_dashboard(demo, ReportFilters(start_date="2026-03-06", end_date="2026-03-09"))
    assert sorted(b["batch_code"] for b in d.recent_batches) == ["SYN-B003", "SYN-B004"]
    with pytest.raises(ValidationFailure):
        dashboard.build_dashboard(demo, ReportFilters(start_date="2026-04-01", end_date="2026-03-01"))


def test_consumption_comparison_report_and_csv(demo):
    rep = reports.consumption_comparison_report(demo, ReportFilters())
    rows = {(r["Batch ID"], r["Material"]): r for r in rep.rows}
    salt = rows[("SYN-B001", "Synthetic Salt")]
    assert salt["Variance (actual - planned)"] == Decimal(2) and salt["Variance (%)"] == Decimal("20.00")
    zero = rows[("SYN-B003", "Synthetic Wetting Agent")]
    assert zero["Variance (%)"] == "Unavailable" and zero["Variance (actual - planned)"] == Decimal("0.5")
    missing = rows[("SYN-B003", "Synthetic Dye B")]
    assert missing["Actual quantity"] is None and missing["Variance (actual - planned)"] == "Unavailable"
    assert rows[("SYN-B004", "Synthetic Dye B")]["Comparison status"] == "Not comparable"
    table = parse_csv(rows_to_csv(rep.columns, rep.rows))
    assert table[0] == rep.columns and len(table) == len(rep.rows) + 1
    idx = rep.columns.index("Variance (actual - planned)")
    assert any(row[idx] == "2" for row in table[1:])  # numeric cells are not quoted/escaped


def test_csv_matches_displayed_rows_for_each_report(demo):
    f = ReportFilters(status="completed")
    for key, build in reports.REPORT_BUILDERS.items():
        rep = build(demo, f)
        assert len(parse_csv(rows_to_csv(rep.columns, rep.rows))) == len(rep.rows) + 1, key


def test_filters_apply_to_every_report(demo):
    f = ReportFilters(search="SYN-B002")
    assert [r["Batch ID"] for r in reports.batch_production_report(demo, f).rows] == ["SYN-B002"]
    assert {r["Batch ID"] for r in reports.consumption_records_report(demo, f).rows} == {"SYN-B002"}
    assert {r["Batch ID"] for r in reports.quality_report(demo, f).rows} == {"SYN-B002"}
    assert {r["Batch ID"] for r in reports.rework_report(demo, f).rows} == {"SYN-B002"}
    machine_rows = reports.machine_activity_report(demo, f).rows
    assert sum(r["Batches recorded"] for r in machine_rows) == 1


def test_quality_report_final_outcome_and_outcome_filter(demo):
    rep = reports.quality_report(demo, ReportFilters())
    assert rep.summary["by_disposition"] == {"pending": 1, "passed": 2, "failed": 2}
    assert rep.summary["batches_with_final_outcome"] == 3 and rep.summary["batches_final_failed"] == 1
    only_failed = reports.quality_report(demo, ReportFilters(inspection_outcome="failed"))
    assert len(only_failed.rows) == 2 and only_failed.summary["outcome_filter_active"]
    assert only_failed.summary["batches_with_final_outcome"] == 3  # indicator ignores the outcome filter
    day = reports.quality_report(demo, ReportFilters(start_date="2026-03-04", end_date="2026-03-04"))
    assert [r["Inspection ID"][:3] for r in day.rows] == ["QI-"] and day.summary["batches_with_final_outcome"] == 1


def test_rework_report_links_follow_up(demo):
    rep = reports.rework_report(demo, ReportFilters())
    by_batch = {r["Batch ID"]: r for r in rep.rows}
    assert by_batch["SYN-B002"]["Subsequent inspection outcome"] == "Passed"
    assert by_batch["SYN-B002"]["Related inspection outcome"] == "Failed"
    assert by_batch["SYN-B007"]["Subsequent inspection outcome"] == "None recorded yet"
    assert rep.summary["events"] == 2 and rep.summary["distinct_batches"] == 2
    assert [r["Batch ID"] for r in reports.rework_report(demo, ReportFilters(rework_status="required")).rows] == [
        "SYN-B007"
    ]


def test_machine_activity_counts_records_only(demo):
    rows = {r["Machine ID"]: r for r in reports.machine_activity_report(demo, ReportFilters()).rows}
    assert rows["SYN-M01"]["Batches recorded"] == 4 and rows["SYN-M01"]["Completed"] == 4
    assert rows["(none)"]["Batches recorded"] == 1 and rows["(none)"]["Planned"] == 1


def test_csv_formula_injection_end_to_end(conn):
    b = make_batch(conn, "CSV-1", work_order_ref="@WO", material_description="-2+3", notes="+1")
    rep = reports.batch_production_report(conn, ReportFilters())
    table = parse_csv(rows_to_csv(rep.columns, rep.rows))
    cells = table[1]
    assert cells[rep.columns.index("Work-order reference")] == "'@WO"
    assert cells[rep.columns.index("Fabric / material")] == "'-2+3"
    assert cells[rep.columns.index("Quantity")] == "100"
    stored = batches.get_batch(conn, b["id"])
    assert stored["work_order_ref"] == "@WO"  # the database value is unchanged


def test_sample_data_loader_is_protected_and_removable(conn):
    sample_data.load_sample_data(conn)
    with pytest.raises(Conflict):
        sample_data.load_sample_data(conn)
    assert not sample_data.has_non_sample_records(conn)
    real = make_batch(conn, "REAL-1")
    make_inspection(conn, real["id"], "passed")
    assert sample_data.has_non_sample_records(conn)
    assert sample_data.remove_sample_data(conn) == 7
    left = {r[0] for r in conn.execute("SELECT batch_code FROM batches")}
    assert left == {"REAL-1"}
    assert conn.execute("SELECT COUNT(*) FROM quality_inspections").fetchone()[0] == 1
    assert consumption.list_consumption_records(conn) == []
    from textile_dyeing_intelligence.database import integrity_problems

    assert integrity_problems(conn) == []
    # the protective trigger is back after removal
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM quality_inspections")
