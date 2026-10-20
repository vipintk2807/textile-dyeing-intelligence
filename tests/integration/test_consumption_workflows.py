from decimal import Decimal as D

import pytest

from tests.fixtures.sample_records import make_batch
from textile_dyeing_intelligence.errors import Conflict, ValidationFailure
from textile_dyeing_intelligence.filters import ReportFilters
from textile_dyeing_intelligence.services import consumption as svc


def add(conn, batch_id, category, qty, unit="kg", material="Salt", basis=None, when="2026-03-01 08:00"):
    return svc.create_consumption_record(
        conn,
        {
            "batch_id": batch_id,
            "material_name": material,
            "category": category,
            "quantity": qty,
            "unit": unit,
            "basis": basis,
            "recorded_at": when,
        },
    )


def test_planned_and_actual_are_stored_distinctly_and_compared(conn):
    b = make_batch(conn)
    add(conn, b["id"], "planned", "10")
    add(conn, b["id"], "actual", "12", when="2026-03-01 11:00")
    rows = svc.compare_for_batch(conn, b["id"])
    assert len(rows) == 1
    assert rows[0]["variance"] == D(2) and rows[0]["variance_percent"] == D(20)
    cats = [r["category"] for r in svc.list_consumption_records(conn, batch_id=b["id"])]
    assert sorted(cats) == ["actual", "planned"]


def test_zero_planned_missing_and_incompatible_cases(conn):
    b = make_batch(conn)
    add(conn, b["id"], "planned", "0", material="A")
    add(conn, b["id"], "actual", "5", material="A", when="2026-03-01 09:00")
    add(conn, b["id"], "actual", "5", material="B")  # no planned
    add(conn, b["id"], "planned", "10", material="C")
    add(conn, b["id"], "actual", "10000", unit="g", material="C", when="2026-03-01 09:00")
    by = {r["material_name"]: r for r in svc.compare_for_batch(conn, b["id"])}
    assert by["A"]["variance"] == D(5) and by["A"]["variance_percent"] is None
    assert by["B"]["status"] == "incomplete" and by["B"]["variance"] is None
    assert by["C"]["status"] == "incompatible"


def test_materials_never_combined_and_same_category_records_sum(conn):
    b = make_batch(conn)
    add(conn, b["id"], "planned", "10", material="A")
    add(conn, b["id"], "actual", "6", material="A")
    add(conn, b["id"], "actual", "6", material="A", when="2026-03-01 10:00")  # second dosing
    add(conn, b["id"], "planned", "1", material="B")
    rows = {r["material_name"]: r for r in svc.compare_for_batch(conn, b["id"])}
    assert rows["A"]["actual_total"] == D(12) and rows["A"]["variance"] == D(2)
    assert rows["B"]["actual_total"] is None


def test_mixed_units_within_one_category_are_not_summed(conn):
    b = make_batch(conn)
    add(conn, b["id"], "planned", "10")
    add(conn, b["id"], "actual", "5", unit="kg")
    add(conn, b["id"], "actual", "500", unit="g", when="2026-03-01 09:00")
    assert svc.compare_for_batch(conn, b["id"])[0]["status"] == "incompatible"


def test_invalid_input_rejected_and_not_saved(conn):
    b = make_batch(conn)
    for bad in ({"quantity": "-1"}, {"quantity": "abc"}, {"unit": ""}, {"material_name": ""}):
        with pytest.raises(ValidationFailure):
            svc.create_consumption_record(
                conn,
                {
                    "batch_id": b["id"],
                    "material_name": "Salt",
                    "category": "planned",
                    "quantity": "1",
                    "unit": "kg",
                    "recorded_at": "2026-03-01 08:00",
                    **bad,
                },
            )
    with pytest.raises(ValidationFailure, match="Selected batch does not exist"):
        add(conn, 9999, "planned", "1")
    assert conn.execute("SELECT COUNT(*) FROM consumption_records").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM chemical_materials").fetchone()[0] == 0


def test_duplicate_submission_is_rejected_once(conn):
    b = make_batch(conn)
    add(conn, b["id"], "planned", "10")
    with pytest.raises(Conflict, match="Nothing was saved again"):
        add(conn, b["id"], "planned", "10")
    assert conn.execute("SELECT COUNT(*) FROM consumption_records").fetchone()[0] == 1


def test_filter_scope_material_and_dates(conn):
    b = make_batch(conn)
    add(conn, b["id"], "planned", "10", material="Salt", when="2026-03-01 08:00")
    add(conn, b["id"], "actual", "11", material="Salt", when="2026-03-01 09:00")
    add(conn, b["id"], "planned", "1", material="Dye", when="2026-04-01 08:00")
    got = svc.compare_for_filters(conn, ReportFilters(material="Dye"))
    assert [r["material_name"] for r in got] == ["Dye"]
    got = svc.compare_for_filters(conn, ReportFilters(end_date="2026-03-31"))
    assert [r["material_name"] for r in got] == ["Salt"]
