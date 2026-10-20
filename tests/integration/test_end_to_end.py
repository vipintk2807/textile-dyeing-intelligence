"""Technical specification 14.3 / workflow scenarios A, C, E, F expressed as one flow."""

from decimal import Decimal

import pytest

from textile_dyeing_intelligence.errors import TDIError
from textile_dyeing_intelligence.filters import ReportFilters
from textile_dyeing_intelligence.reporting import dashboard, reports
from textile_dyeing_intelligence.reporting.export import rows_to_csv
from textile_dyeing_intelligence.services import (
    batches,
    consumption,
    machines,
    process_records,
    quality,
    recipes,
    rework,
)


def test_full_batch_lifecycle(conn):
    machine = machines.create_machine(conn, {"machine_code": "E-M1", "name": "E2E machine"})
    rev_a = recipes.create_recipe(
        conn,
        {"recipe_code": "E-R1", "name": "E2E recipe"},
        {"revision_code": "A", "ingredients": [{"material_name": "Salt", "quantity": "10", "unit": "kg"}]},
    )
    batch = batches.create_batch(
        conn,
        {
            "batch_code": "E-B1",
            "material_description": "Fabric",
            "quantity": "100",
            "quantity_unit": "kg",
            "recipe_revision_id": rev_a["id"],
            "machine_id": machine["id"],
            "planned_date": "2026-03-01",
        },
    )
    batches.change_status(conn, batch["id"], "in_progress", actual_start="2026-03-01 08:00")
    process_records.create_process_record(
        conn,
        {
            "batch_id": batch["id"],
            "parameter_name": "Temperature",
            "value": "60",
            "unit": "°C",
            "observed_at": "2026-03-01 09:00",
        },
    )
    for category, qty in (("planned", "10"), ("actual", "12")):
        consumption.create_consumption_record(
            conn,
            {
                "batch_id": batch["id"],
                "material_name": "Salt",
                "category": category,
                "quantity": qty,
                "unit": "kg",
                "recorded_at": "2026-03-01 09:30",
            },
        )
    failed = quality.create_inspection(
        conn,
        {
            "batch_id": batch["id"],
            "inspection_type": "Final",
            "inspected_at": "2026-03-01 14:00",
            "disposition": "failed",
            "defects": [{"category": "Uneven shade"}],
        },
    )
    batches.change_status(conn, batch["id"], "completed", actual_end="2026-03-01 13:00")
    work = rework.create_rework(conn, {"batch_id": batch["id"], "inspection_id": failed["id"], "reason": "Uneven"})
    rework.update_rework(conn, work["id"], {"status": "in_progress"})
    quality.create_inspection(
        conn,
        {
            "batch_id": batch["id"],
            "inspection_type": "Follow-up",
            "inspected_at": "2026-03-02 09:00",
            "disposition": "passed",
        },
    )
    # new revision must not disturb the batch
    recipes.add_revision(
        conn,
        rev_a["recipe_id"],
        {"revision_code": "B", "ingredients": [{"material_name": "Salt", "quantity": "11", "unit": "kg"}]},
    )

    detail = batches.get_batch_detail(conn, batch["id"])
    assert detail["batch"]["status"] == "completed"
    assert detail["batch"]["final_outcome"] == "passed"
    assert [i["disposition"] for i in detail["inspections"]] == ["passed", "failed"]  # both kept, newest first
    assert detail["inspections"][1]["defects"][0]["category"] == "Uneven shade"
    assert detail["revision"]["revision_code"] == "A"
    assert detail["consumption_comparison"][0]["variance_percent"] == Decimal(20)
    assert len(detail["process_records"]) == 1 and len(detail["rework"]) == 1
    assert detail["rework"][0]["status"] == "in_progress"

    d = dashboard.build_dashboard(conn, ReportFilters())
    assert d.metrics.total_batches == 1 and d.metrics.failure_rate == 0
    assert d.metrics.batches_with_failed_inspection == 1 and d.metrics.batches_with_rework == 1
    rep = reports.consumption_comparison_report(conn, ReportFilters())
    assert rows_to_csv(rep.columns, rep.rows).count(b"\r\n") == 2


def test_invalid_records_never_create_partial_data(conn):
    def counts():
        return [
            conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731, S608
            for t in ("batches", "consumption_records", "chemical_materials", "recipes")
        ]

    before = counts()
    with pytest.raises(TDIError):
        batches.create_batch(
            conn, {"batch_code": "X", "material_description": "f", "quantity": "-1", "quantity_unit": "kg"}
        )
    with pytest.raises(TDIError):
        consumption.create_consumption_record(
            conn,
            {
                "batch_id": 99,
                "material_name": "NewChem",
                "category": "planned",
                "quantity": "1",
                "unit": "kg",
                "recorded_at": "2026-03-01 08:00",
            },
        )
    with pytest.raises(TDIError):
        recipes.create_recipe(
            conn,
            {"recipe_code": "R", "name": "n"},
            {"revision_code": "A", "ingredients": [{"material_name": "Fresh", "quantity": "0", "unit": "kg"}]},
        )
    assert counts() == before
