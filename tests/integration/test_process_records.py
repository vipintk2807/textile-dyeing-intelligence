import pytest

from tests.fixtures.sample_records import make_batch
from textile_dyeing_intelligence.errors import Conflict, ValidationFailure
from textile_dyeing_intelligence.services import process_records as svc


def rec(conn, batch_id, **kw):
    data = {
        "batch_id": batch_id,
        "parameter_name": "Temperature",
        "value": "60",
        "unit": "°C",
        "observed_at": "2026-03-01 09:00",
        **kw,
    }
    return svc.create_process_record(conn, data)


def test_record_keeps_both_timestamps_and_manual_source(conn):
    b = make_batch(conn)
    r = rec(conn, b["id"])
    assert r["observed_at"] == "2026-03-01T09:00:00" and r["recorded_at"] != r["observed_at"]
    assert r["source"] == "operator_entry" and r["unit"] == "°C"


def test_zero_value_and_missing_unit_are_distinct_from_missing(conn):
    b = make_batch(conn)
    r = rec(conn, b["id"], parameter_name="pH", value="0", unit=None)
    assert r["value"] == "0" and r["unit"] is None


def test_invalid_input_and_invalid_batch(conn):
    b = make_batch(conn)
    for bad in (
        {"value": "hot"},
        {"value": ""},
        {"parameter_name": ""},
        {"observed_at": "yesterday"},
        {"value": "-5"},
        {"source": "sensor"},
    ):
        with pytest.raises(ValidationFailure):
            rec(conn, b["id"], **bad)
    with pytest.raises(ValidationFailure, match="Selected batch does not exist"):
        rec(conn, 4242)
    assert conn.execute("SELECT COUNT(*) FROM process_records").fetchone()[0] == 0


def test_duplicate_submission_rejected(conn):
    b = make_batch(conn)
    rec(conn, b["id"])
    with pytest.raises(Conflict, match="Nothing was saved again"):
        rec(conn, b["id"])
    assert len(svc.list_process_records(conn, batch_id=b["id"])) == 1


def test_correction_preserves_history_and_batch(conn):
    a, b = make_batch(conn, "T-A"), make_batch(conn, "T-B")
    r = rec(conn, a["id"])
    updated = svc.update_process_record(
        conn,
        r["id"],
        {
            "batch_id": b["id"],
            "parameter_name": "Temperature",
            "value": "65",
            "unit": "°C",
            "observed_at": "2026-03-01 09:00",
        },
    )
    assert updated["value"] == "65" and updated["batch_id"] == a["id"]
    history = svc.record_history(conn, r["id"])
    assert len(history) == 1 and history[0]["previous_value"] == "60"


def test_filters(conn):
    a, b = make_batch(conn, "T-A"), make_batch(conn, "T-B")
    rec(conn, a["id"])
    rec(conn, a["id"], parameter_name="pH", value="10", unit=None, observed_at="2026-04-01 09:00")
    rec(conn, b["id"])
    assert len(svc.list_process_records(conn, batch_id=a["id"])) == 2
    assert len(svc.list_process_records(conn, parameter="ph")) == 1
    assert len(svc.list_process_records(conn, start_date="2026-03-15")) == 1
    assert len(svc.list_process_records(conn, end_date="2026-03-15")) == 2
