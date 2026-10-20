import sqlite3
from decimal import Decimal

import pytest

from tests.fixtures.sample_records import make_batch, make_inspection
from textile_dyeing_intelligence.errors import Conflict, ValidationFailure
from textile_dyeing_intelligence.filters import ReportFilters
from textile_dyeing_intelligence.reporting.metrics import batch_metrics
from textile_dyeing_intelligence.services import batches, quality, rework


def test_multiple_inspections_keep_their_own_outcomes(conn):
    b = make_batch(conn)
    first = make_inspection(conn, b["id"], "failed", "2026-03-02 10:00")
    second = make_inspection(conn, b["id"], "passed", "2026-03-03 10:00", kind="Follow-up")
    assert quality.get_inspection(conn, first["id"])["disposition"] == "failed"
    assert second["inspection_code"] != first["inspection_code"]
    detail = batches.get_batch(conn, b["id"])
    assert detail["final_outcome"] == "passed" and detail["inspection_count"] == 2


def test_no_or_pending_inspection_is_never_a_pass(conn):
    b = make_batch(conn)
    assert batches.get_batch(conn, b["id"])["final_outcome"] is None
    make_inspection(conn, b["id"], "pending")
    got = batches.get_batch(conn, b["id"])
    assert got["final_outcome"] is None and "Pending" in got["quality_label"]


def test_empty_defect_list_does_not_imply_pass(conn):
    b = make_batch(conn)
    insp = quality.create_inspection(
        conn, {"batch_id": b["id"], "inspection_type": "Final", "inspected_at": "2026-03-02 10:00"}
    )
    assert insp["disposition"] == "pending" and insp["defects"] == []


def test_measurements_zero_vs_missing(conn):
    b = make_batch(conn)
    insp = quality.create_inspection(
        conn,
        {
            "batch_id": b["id"],
            "inspection_type": "Final",
            "inspected_at": "2026-03-02 10:00",
            "measurements": [{"name": "Shade", "value": "0", "unit": "u"}],
        },
    )
    assert insp["measurements"][0]["value"] == "0"
    bare = make_inspection(conn, b["id"], "pending", "2026-03-02 11:00", kind="Other")
    assert quality.get_inspection(conn, bare["id"])["measurements"] == []
    with pytest.raises(ValidationFailure):
        quality.create_inspection(
            conn,
            {
                "batch_id": b["id"],
                "inspection_type": "X",
                "inspected_at": "2026-03-02 12:00",
                "measurements": [{"name": "Shade", "value": "", "unit": "u"}],
            },
        )


def test_pending_can_be_finalised_once_and_final_is_immutable(conn):
    b = make_batch(conn)
    p = make_inspection(conn, b["id"], "pending")
    done = quality.finalise_inspection(conn, p["id"], "failed")
    assert done["disposition"] == "failed" and done["finalised_at"]
    with pytest.raises(Conflict):
        quality.finalise_inspection(conn, p["id"], "passed")
    with pytest.raises(Conflict):
        quality.update_pending_inspection(conn, p["id"], {"inspection_type": "x", "inspected_at": "2026-03-02 10:00"})
    with pytest.raises(sqlite3.IntegrityError, match="finalised"):
        conn.execute("UPDATE quality_inspections SET disposition='passed' WHERE id=?", (p["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="finalised"):
        conn.execute("DELETE FROM quality_inspections WHERE id=?", (p["id"],))
    with pytest.raises(ValidationFailure):
        quality.finalise_inspection(
            conn, make_inspection(conn, b["id"], "pending", "2026-03-05 10:00")["id"], "pending"
        )


def test_duplicate_inspection_submission_rejected(conn):
    b = make_batch(conn)
    make_inspection(conn, b["id"], "passed")
    with pytest.raises(Conflict, match="already recorded"):
        make_inspection(conn, b["id"], "passed")


def test_inspection_for_missing_batch_rejected(conn):
    with pytest.raises(ValidationFailure):
        make_inspection(conn, 777, "passed")


def test_rework_preserves_original_failure_and_followup(conn):
    b = make_batch(conn)
    failed = make_inspection(conn, b["id"], "failed", "2026-03-02 10:00")
    rw = rework.create_rework(conn, {"batch_id": b["id"], "inspection_id": failed["id"], "reason": "Uneven"})
    assert rw["rework_code"] == "RW-00001" and rw["status"] == "required"
    rework.update_rework(conn, rw["id"], {"status": "in_progress", "started_at": "2026-03-03 08:00"})
    done = rework.update_rework(
        conn, rw["id"], {"status": "completed", "completed_at": "2026-03-03 10:00", "corrective_description": "Re-dyed"}
    )
    assert done["status"] == "completed"
    # completing rework must not approve the batch
    assert batches.get_batch(conn, b["id"])["final_outcome"] == "failed"
    follow = make_inspection(conn, b["id"], "passed", "2026-03-04 10:00", kind="Follow-up")
    rows = rework.with_subsequent_inspection(conn, rework.list_rework(conn, batch_id=b["id"]))
    assert rows[0]["subsequent_inspection"]["id"] == follow["id"]
    assert quality.get_inspection(conn, failed["id"])["disposition"] == "failed"


def test_rework_validation_and_links(conn):
    a, other = make_batch(conn, "T-A"), make_batch(conn, "T-B")
    insp_other = make_inspection(conn, other["id"], "failed")
    with pytest.raises(ValidationFailure, match="different batch"):
        rework.create_rework(conn, {"batch_id": a["id"], "inspection_id": insp_other["id"], "reason": "x"})
    with pytest.raises(sqlite3.IntegrityError, match="different batch"):
        conn.execute(
            "INSERT INTO rework_records (rework_code,batch_id,inspection_id,reason,status,created_at,updated_at)"
            " VALUES ('Z',?,?,'r','required','n','n')",
            (a["id"], insp_other["id"]),
        )
    with pytest.raises(ValidationFailure):
        rework.create_rework(conn, {"batch_id": 9999, "reason": "x"})
    with pytest.raises(ValidationFailure):
        rework.create_rework(conn, {"batch_id": a["id"], "reason": ""})
    with pytest.raises(ValidationFailure):
        rework.create_rework(conn, {"batch_id": a["id"], "reason": "x", "inspection_id": 4242})


def test_rework_status_rules(conn):
    b = make_batch(conn)
    rw = rework.create_rework(conn, {"batch_id": b["id"], "reason": "x"})
    with pytest.raises(ValidationFailure):
        rework.update_rework(
            conn, rw["id"], {"status": "completed", "corrective_description": "d", "completed_at": "2026-03-03 10:00"}
        )  # required -> completed not allowed
    rework.update_rework(conn, rw["id"], {"status": "cancelled"})
    with pytest.raises(Conflict):
        rework.update_rework(conn, rw["id"], {"status": "in_progress"})
    assert rework.update_rework(conn, rw["id"], {"notes": "late note"})["notes"] == "late note"


def test_rework_events_vs_distinct_batches_and_rates(conn):
    a, b, c = (make_batch(conn, code) for code in ("T-A", "T-B", "T-C"))
    for _ in range(3):  # three events, one batch
        rework.create_rework(conn, {"batch_id": a["id"], "reason": "x"})
    rework.create_rework(conn, {"batch_id": b["id"], "reason": "y", "status": "cancelled"})
    make_inspection(conn, a["id"], "failed", "2026-03-02 10:00")
    make_inspection(conn, a["id"], "failed", "2026-03-03 10:00", kind="Again")  # same batch twice
    make_inspection(conn, b["id"], "passed")
    make_inspection(conn, c["id"], "pending")
    m = batch_metrics(conn, ReportFilters())
    assert m.rework_events == 3 and m.batches_with_rework == 1
    assert m.rework_rate is not None and round(m.rework_rate, 2) == Decimal("33.33")
    assert m.batches_with_final_outcome == 2 and m.batches_final_failed == 1
    assert m.failure_rate == 50 and m.batches_with_failed_inspection == 1


def test_rates_unavailable_when_denominator_zero(conn):
    m = batch_metrics(conn, ReportFilters())
    assert m.total_batches == 0 and m.failure_rate is None and m.rework_rate is None
    make_batch(conn)  # batch without any final outcome
    m = batch_metrics(conn, ReportFilters())
    assert m.failure_rate is None and m.rework_rate == 0
