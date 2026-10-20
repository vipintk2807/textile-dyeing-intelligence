from __future__ import annotations

import pytest

from textile_dyeing_intelligence import database as db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    db.initialize_database(path)
    return path


@pytest.fixture
def conn(db_path):
    connection = db.connect(db_path)
    yield connection
    connection.close()
