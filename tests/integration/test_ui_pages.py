"""Headless Streamlit tests (streamlit.testing.v1.AppTest) against temporary databases."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from textile_dyeing_intelligence import sample_data
from textile_dyeing_intelligence.database import initialize_database, open_connection

ROOT = Path(__file__).resolve().parents[2]
PAGES = sorted((ROOT / "pages").glob("*.py"))


@pytest.fixture
def empty_db(tmp_path, monkeypatch):
    path = tmp_path / "ui.db"
    monkeypatch.setenv("TDI_DB_PATH", str(path))
    initialize_database(path)
    return path


@pytest.fixture
def sample_db(empty_db):
    with open_connection(empty_db) as conn:
        sample_data.load_sample_data(conn)
    return empty_db


def run(script: Path) -> AppTest:
    at = AppTest.from_file(str(script), default_timeout=30)
    at.run()
    return at


def count_machines(path) -> int:
    with open_connection(path) as conn:
        return conn.execute("SELECT COUNT(*) FROM machines").fetchone()[0]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_load_on_empty_database(empty_db, page):
    at = run(page)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_load_with_sample_data(sample_db, page):
    at = run(page)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error


def test_dashboard_loads_empty_and_with_sample_data(empty_db):
    at = run(ROOT / "app.py")
    assert not at.exception and not at.error
    with open_connection(empty_db) as conn:
        sample_data.load_sample_data(conn)
    at = run(ROOT / "app.py")
    assert not at.exception and not at.error


def submit(at: AppTest, label: str) -> None:
    next(b for b in at.button if b.label == label).click().run()


def test_valid_machine_form_creates_exactly_one_record(empty_db):
    page = ROOT / "pages" / "3_Machines.py"
    at = run(page)
    at.text_input(key="machine_add_0_code").input("UI-M1")
    at.text_input(key="machine_add_0_name").input("UI machine")
    submit(at, "Add Machine")
    assert not at.exception and count_machines(empty_db) == 1
    assert any("created successfully" in s.value for s in at.success)
    at.run()  # an ordinary rerun must not write again
    assert count_machines(empty_db) == 1
    assert at.text_input(key="machine_add_1_code").value == ""  # the form was cleared


def test_invalid_machine_form_shows_error_and_saves_nothing(empty_db):
    at = run(ROOT / "pages" / "3_Machines.py")
    at.text_input(key="machine_add_0_code").input("bad code!")
    at.text_input(key="machine_add_0_name").input("Name")
    submit(at, "Add Machine")
    assert not at.exception
    assert any("Nothing was saved" in e.value for e in at.error)
    assert count_machines(empty_db) == 0


def test_duplicate_machine_is_refused(empty_db):
    page = ROOT / "pages" / "3_Machines.py"
    at = run(page)
    at.text_input(key="machine_add_0_code").input("DUP-1")
    at.text_input(key="machine_add_0_name").input("First")
    submit(at, "Add Machine")
    at.text_input(key="machine_add_1_code").input("DUP-1")
    at.text_input(key="machine_add_1_name").input("Second")
    submit(at, "Add Machine")
    assert any("already exists" in e.value for e in at.error)
    assert count_machines(empty_db) == 1
