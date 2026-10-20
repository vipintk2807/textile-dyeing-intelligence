import sqlite3

import pytest

from tests.fixtures.sample_records import make_batch, make_recipe
from textile_dyeing_intelligence.errors import Conflict, ValidationFailure
from textile_dyeing_intelligence.repositories import recipes as recipe_repo
from textile_dyeing_intelligence.services import batches, recipes


def test_recipe_with_structured_ingredients(conn):
    rev = make_recipe(conn)
    assert rev["ingredients"][0]["material_name"] == "Test Salt"
    assert rev["ingredients"][0]["quantity"] == "10" and rev["ingredients"][0]["unit"] == "kg"


def test_invalid_ingredients_rejected_with_row_numbers(conn):
    with pytest.raises(ValidationFailure) as exc:
        recipes.create_recipe(
            conn,
            {"recipe_code": "R", "name": "n"},
            {
                "revision_code": "A",
                "ingredients": [
                    {"material_name": "Ok", "quantity": "1", "unit": "kg"},
                    {"material_name": "Zero", "quantity": "0", "unit": "kg"},
                    {"material_name": "", "quantity": "1", "unit": ""},
                ],
            },
        )
    errors = exc.value.errors
    assert "Ingredient 2" in errors["ingredients[1].quantity"]
    assert "ingredients[2].material_name" in errors
    assert conn.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == 0
    with pytest.raises(ValidationFailure):
        recipes.create_recipe(conn, {"recipe_code": "R", "name": "n"}, {"revision_code": "A", "ingredients": []})


def test_failure_while_saving_ingredients_leaves_no_partial_revision(conn, monkeypatch):
    rev = make_recipe(conn)
    calls = {"n": 0}
    real = recipe_repo.insert_ingredient

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise sqlite3.OperationalError("disk I/O error")
        return real(*args, **kwargs)

    monkeypatch.setattr(recipe_repo, "insert_ingredient", flaky)
    before = conn.execute("SELECT COUNT(*) FROM recipe_revisions").fetchone()[0]
    materials_before = conn.execute("SELECT COUNT(*) FROM chemical_materials").fetchone()[0]
    with pytest.raises(Exception, match="not been confirmed"):
        recipes.add_revision(
            conn,
            rev["recipe_id"],
            {
                "revision_code": "B",
                "ingredients": [
                    {"material_name": "New One", "quantity": "1", "unit": "kg"},
                    {"material_name": "New Two", "quantity": "2", "unit": "kg"},
                ],
            },
        )
    assert conn.execute("SELECT COUNT(*) FROM recipe_revisions").fetchone()[0] == before
    assert conn.execute("SELECT COUNT(*) FROM chemical_materials").fetchone()[0] == materials_before
    assert conn.execute("SELECT COUNT(*) FROM recipe_ingredients").fetchone()[0] == 1


def test_duplicate_revision_code_rejected(conn):
    rev = make_recipe(conn)
    with pytest.raises(Conflict, match="revision"):
        recipes.add_revision(
            conn,
            rev["recipe_id"],
            {"revision_code": "a", "ingredients": [{"material_name": "X", "quantity": "1", "unit": "kg"}]},
        )


def test_revision_in_use_cannot_be_modified(conn):
    rev = make_recipe(conn)
    make_batch(conn, revision_id=rev["id"])
    for sql in ("UPDATE recipe_ingredients SET quantity='99'", "DELETE FROM recipe_ingredients"):
        with pytest.raises(sqlite3.IntegrityError, match="used by a batch"):
            conn.execute(sql)
    material = conn.execute("SELECT id FROM chemical_materials").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="used by a batch"):
        conn.execute(
            "INSERT INTO recipe_ingredients (revision_id, material_id, position, quantity, unit)"
            " VALUES (?, ?, 2, '1', 'kg')",
            (rev["id"], material),
        )


def test_archive_blocks_new_use_but_keeps_history(conn):
    rev = make_recipe(conn)
    old = make_batch(conn, revision_id=rev["id"])
    recipes.set_recipe_status(conn, rev["recipe_id"], "archived")
    assert recipes.selectable_revisions(conn) == []
    with pytest.raises(ValidationFailure, match="archived"):
        make_batch(conn, "T-B2", revision_id=rev["id"])
    assert batches.get_batch(conn, old["id"])["revision_code"] == "A"
    assert recipes.get_revision(conn, rev["id"])["ingredients"]
    recipes.set_recipe_status(conn, rev["recipe_id"], "active")
    assert len(recipes.selectable_revisions(conn)) == 1


def test_referenced_recipe_cannot_be_deleted(conn):
    rev = make_recipe(conn)
    make_batch(conn, revision_id=rev["id"])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM recipe_revisions WHERE id=?", (rev["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM recipes")


def test_material_names_are_shared_case_insensitively(conn):
    make_recipe(conn, "R1")
    recipes.create_recipe(
        conn,
        {"recipe_code": "R2", "name": "n"},
        {"revision_code": "A", "ingredients": [{"material_name": "  test   SALT ", "quantity": "1", "unit": "kg"}]},
    )
    assert conn.execute("SELECT COUNT(*) FROM chemical_materials").fetchone()[0] == 1
