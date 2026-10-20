import pytest

from tests.fixtures.sample_records import make_batch, make_inspection, make_machine, make_recipe
from textile_dyeing_intelligence.errors import Conflict, NotFound, ValidationFailure
from textile_dyeing_intelligence.filters import ReportFilters
from textile_dyeing_intelligence.services import batches, recipes


def test_create_and_retrieve_batch(conn):
    machine = make_machine(conn)
    rev = make_recipe(conn)
    b = make_batch(conn, revision_id=rev["id"], machine_id=machine["id"])
    got = batches.get_batch(conn, b["id"])
    assert got["batch_code"] == "T-B1" and got["status"] == "planned"
    assert got["revision_code"] == "A" and got["machine_code"] == "T-M1"
    assert got["quality_label"] == "Not inspected"


def test_duplicate_and_invalid_references_rejected(conn):
    make_batch(conn)
    with pytest.raises(Conflict, match="batch with this identifier already exists"):
        make_batch(conn)
    with pytest.raises(ValidationFailure) as e1:
        make_batch(conn, "T-B2", revision_id=999)
    assert "recipe_revision_id" in e1.value.errors
    with pytest.raises(ValidationFailure) as e2:
        make_batch(conn, "T-B3", machine_id=999)
    assert "machine_id" in e2.value.errors
    with pytest.raises(ValidationFailure):
        make_batch(conn, "T-B4", quantity="-1")
    assert conn.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1


def test_status_transitions_and_independence_from_quality(conn):
    b = make_batch(conn)
    assert (
        batches.change_status(conn, b["id"], "in_progress", actual_start="2026-03-01 08:00")["status"] == "in_progress"
    )
    make_inspection(conn, b["id"], "failed")
    done = batches.change_status(conn, b["id"], "completed", actual_end="2026-03-01 12:00")
    assert done["status"] == "completed" and done["final_outcome"] == "failed"
    assert conn.execute("SELECT COUNT(*) FROM quality_inspections").fetchone()[0] == 1
    with pytest.raises(ValidationFailure, match="cannot change"):
        batches.change_status(conn, b["id"], "cancelled")
    c = make_batch(conn, "T-B2")
    batches.change_status(conn, c["id"], "cancelled")
    with pytest.raises(ValidationFailure):
        batches.change_status(conn, c["id"], "completed")
    with pytest.raises(ValidationFailure):
        batches.change_status(conn, c["id"], "in_progress", actual_start="bad")


def test_end_before_start_rejected(conn):
    b = make_batch(conn)
    batches.change_status(conn, b["id"], "in_progress", actual_start="2026-03-02 08:00")
    with pytest.raises(ValidationFailure):
        batches.change_status(conn, b["id"], "completed", actual_end="2026-03-01 08:00")
    assert batches.get_batch(conn, b["id"])["status"] == "in_progress"


def test_completed_batch_locks_quantity_recipe_machine(conn):
    m = make_machine(conn)
    b = make_batch(conn, machine_id=m["id"])
    batches.change_status(conn, b["id"], "in_progress")
    batches.change_status(conn, b["id"], "completed")
    base = {
        "material_description": "Test fabric",
        "quantity": "100",
        "quantity_unit": "kg",
        "machine_id": m["id"],
        "planned_date": "2026-03-01",
    }
    assert batches.update_batch(conn, b["id"], {**base, "notes": "edited"})["notes"] == "edited"
    with pytest.raises(ValidationFailure):
        batches.update_batch(conn, b["id"], {**base, "quantity": "50"})
    with pytest.raises(ValidationFailure):
        batches.update_batch(conn, b["id"], {**base, "machine_id": None})


def test_search_and_filters(conn):
    m1, m2 = make_machine(conn, "M1"), make_machine(conn, "M2")
    make_batch(conn, "AAA-1", machine_id=m1["id"], work_order_ref="WO-9", planned_date="2026-03-01")
    b2 = make_batch(conn, "BBB-2", machine_id=m2["id"], planned_date="2026-04-01")
    batches.change_status(conn, b2["id"], "in_progress")

    def codes(**kw):
        return [r["batch_code"] for r in batches.search_batches(conn, ReportFilters(**kw))[0]]

    assert sorted(codes()) == ["AAA-1", "BBB-2"]
    assert codes(search="aaa") == ["AAA-1"]
    assert codes(search="WO-9") == ["AAA-1"]
    assert codes(status="in_progress") == ["BBB-2"]
    assert codes(machine_id=m1["id"]) == ["AAA-1"]
    assert codes(start_date="2026-03-15") == ["BBB-2"]
    assert codes(end_date="2026-03-15") == ["AAA-1"]
    assert codes(search="%") == []  # wildcard is literal
    with pytest.raises(ValidationFailure):
        codes(start_date="2026-05-01", end_date="2026-01-01")


def test_historical_batch_keeps_revision(conn):
    rev_a = make_recipe(conn)
    b = make_batch(conn, revision_id=rev_a["id"])
    rev_b = recipes.add_revision(
        conn,
        rev_a["recipe_id"],
        {"revision_code": "B", "ingredients": [{"material_name": "Test Salt", "quantity": "11", "unit": "kg"}]},
    )
    assert batches.get_batch(conn, b["id"])["recipe_revision_id"] == rev_a["id"]
    assert rev_b["id"] != rev_a["id"]
    assert recipes.get_revision(conn, rev_a["id"])["ingredients"][0]["quantity"] == "10"


def test_missing_batch(conn):
    with pytest.raises(NotFound):
        batches.get_batch(conn, 12345)
