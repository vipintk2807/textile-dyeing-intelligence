import sqlite3

import pytest

from tests.fixtures.sample_records import make_batch, make_machine
from textile_dyeing_intelligence import database as db
from textile_dyeing_intelligence.errors import Conflict, StorageError, ValidationFailure
from textile_dyeing_intelligence.schema import EXPECTED_TABLES, LATEST_VERSION
from textile_dyeing_intelligence.services import machines


def test_schema_created_and_idempotent(db_path):
    assert db.initialize_database(db_path) == LATEST_VERSION
    conn = db.connect(db_path)
    make_machine(conn)
    db.initialize_database(db_path)  # rerun must not touch data
    assert conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 1
    assert set(EXPECTED_TABLES) <= db.table_names(conn)
    assert db.integrity_problems(conn) == []


def test_foreign_keys_enforced_on_every_connection(db_path):
    for _ in range(3):
        conn = db.connect(db_path)
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO process_records (batch_id, parameter_name, value, observed_at, recorded_at,"
                " updated_at) VALUES (999, 'x', '1', '2026-03-01T10:00:00', 'n', 'n')"
            )
        conn.close()


def test_unique_identifier_gives_friendly_conflict(conn):
    make_machine(conn, "DUP")
    with pytest.raises(Conflict, match="already exists"):
        make_machine(conn, "dup")  # case-insensitive
    assert conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 1


def test_transaction_rolls_back_everything(conn):
    with pytest.raises(RuntimeError), db.transaction(conn):
        conn.execute(
            "INSERT INTO machines (machine_code,name,status,created_at,updated_at) VALUES ('X','x','available','n','n')"
        )
        raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 0
    assert not conn.in_transaction


def test_persistence_across_connections(db_path):
    first = db.connect(db_path)
    machine = make_machine(first)
    batch = make_batch(first, machine_id=machine["id"])
    first.close()
    second = db.connect(db_path)
    assert machines.get_machine(second, machine["id"])["machine_code"] == "T-M1"
    assert second.execute("SELECT machine_id FROM batches WHERE id=?", (batch["id"],)).fetchone()[0] == machine["id"]


def test_failed_migration_leaves_no_partial_changes(tmp_path):
    path = tmp_path / "m.db"
    good = "CREATE TABLE a (id INTEGER PRIMARY KEY);"
    bad = "CREATE TABLE b (id INTEGER PRIMARY KEY); CREATE TABLE a (id INTEGER);"  # second statement fails
    db.initialize_database(path, ((1, good),))
    with pytest.raises(StorageError):
        db.initialize_database(path, ((1, good), (2, bad)))
    conn = db.connect(path)
    assert db.schema_version(conn) == 1
    assert "b" not in db.table_names(conn)


def test_newer_schema_is_refused(tmp_path):
    path = tmp_path / "n.db"
    db.initialize_database(path)
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {LATEST_VERSION + 5}")
    conn.close()
    with pytest.raises(StorageError, match="newer version"):
        db.initialize_database(path)


def test_unwritable_location_reports_error(tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    with pytest.raises(StorageError):
        db.initialize_database(blocker / "sub" / "db.sqlite3")


def test_corrupt_file_reports_error(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a database" * 50)
    with pytest.raises(StorageError):
        db.initialize_database(bad)


def test_locked_database_is_reported_not_saved(db_path):
    holder = db.connect(db_path)
    holder.execute("BEGIN IMMEDIATE")
    other = sqlite3.connect(db_path, timeout=0.05, isolation_level=None)
    other.row_factory = sqlite3.Row
    other.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(StorageError, match="not been confirmed"), db.transaction(other):
        pass
    holder.execute("ROLLBACK")


def test_sql_injection_text_is_stored_literally(conn):
    nasty = "'); DROP TABLE batches;--"
    make_batch(conn, "T-INJ", notes=nasty)
    row = conn.execute("SELECT notes FROM batches WHERE batch_code='T-INJ'").fetchone()
    assert row[0] == nasty
    assert "batches" in db.table_names(conn)


def test_backup_and_restore_roundtrip(db_path, tmp_path):
    conn = db.connect(db_path)
    machine = make_machine(conn)
    make_batch(conn, machine_id=machine["id"])
    backup = tmp_path / "backups" / "b.db"
    db.backup_database(db_path, backup)
    with pytest.raises(StorageError):  # no silent overwrite
        db.backup_database(db_path, backup)
    conn.execute("DELETE FROM batches")
    restored = tmp_path / "restored.db"
    safety = db.restore_database(backup, restored)
    assert safety is None
    r = db.connect(restored)
    assert r.execute("SELECT COUNT(*) FROM batches").fetchone()[0] == 1
    assert r.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 1
    assert db.integrity_problems(r) == []
    # restoring over an existing database keeps a safety copy
    safety = db.restore_database(backup, db_path)
    assert safety is not None and safety.exists()


def test_restore_rejects_foreign_or_corrupt_files(tmp_path):
    other = tmp_path / "other.db"
    c = sqlite3.connect(other)
    c.execute("CREATE TABLE t (x)")
    c.close()
    with pytest.raises(StorageError):
        db.restore_database(other, tmp_path / "target.db")
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"nope" * 100)
    with pytest.raises(StorageError):
        db.restore_database(junk, tmp_path / "target.db")
    assert not (tmp_path / "target.db").exists()


def test_validation_failure_does_not_touch_database(conn):
    with pytest.raises(ValidationFailure):
        machines.create_machine(conn, {"machine_code": "", "name": ""})
    assert conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0] == 0
