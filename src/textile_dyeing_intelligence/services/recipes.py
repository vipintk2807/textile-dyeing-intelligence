from __future__ import annotations

import sqlite3
from typing import Any

from .. import constants as c
from ..database import transaction
from ..errors import NotFound, ValidationFailure
from ..repositories import recipes as repo
from ..timeutil import now_iso
from ..validation import RecipeInput, RevisionInput, validate_model
from . import materials


def _save_revision(conn: sqlite3.Connection, recipe_id: int, revision: RevisionInput, now: str) -> int:
    revision_id = repo.insert_revision(conn, recipe_id, revision.model_dump(), now)
    for position, ingredient in enumerate(revision.ingredients, start=1):
        material_id = materials.get_or_create(conn, ingredient.material_name)
        repo.insert_ingredient(conn, revision_id, material_id, position, ingredient.model_dump())
    return revision_id


def create_recipe(
    conn: sqlite3.Connection, recipe_data: dict[str, Any], revision_data: dict[str, Any]
) -> dict[str, Any]:
    """Create a recipe with its first revision and ingredients, atomically."""
    errors: dict[str, str] = {}
    recipe = revision = None
    try:
        recipe = validate_model(RecipeInput, recipe_data)
    except ValidationFailure as exc:
        errors.update(exc.errors)
    try:
        revision = validate_model(RevisionInput, revision_data)
    except ValidationFailure as exc:
        errors.update(exc.errors)
    if errors or recipe is None or revision is None:
        raise ValidationFailure(errors)
    now = now_iso()
    with transaction(conn):
        recipe_id = repo.insert_recipe(conn, recipe.model_dump(), now)
        revision_id = _save_revision(conn, recipe_id, revision, now)
    return get_revision(conn, revision_id)


def add_revision(conn: sqlite3.Connection, recipe_id: int, revision_data: dict[str, Any]) -> dict[str, Any]:
    """Create a new revision. Existing revisions, and the batches using them, are untouched."""
    if repo.get_recipe(conn, recipe_id) is None:
        raise NotFound("The selected recipe does not exist.")
    revision = validate_model(RevisionInput, revision_data)
    with transaction(conn):
        revision_id = _save_revision(conn, recipe_id, revision, now_iso())
    return get_revision(conn, revision_id)


def get_recipe(conn: sqlite3.Connection, recipe_id: int) -> dict[str, Any]:
    row = repo.get_recipe(conn, recipe_id)
    if row is None:
        raise NotFound("The selected recipe does not exist.")
    return row


def get_revision(conn: sqlite3.Connection, revision_id: int) -> dict[str, Any]:
    row = repo.get_revision(conn, revision_id)
    if row is None:
        raise NotFound("The selected recipe revision does not exist.")
    row["ingredients"] = repo.list_ingredients(conn, revision_id)
    return row


def list_recipes(
    conn: sqlite3.Connection, search: str | None = None, status: str | None = None
) -> list[dict[str, Any]]:
    return repo.list_recipes(conn, search, status)


def list_revisions(conn: sqlite3.Connection, recipe_id: int) -> list[dict[str, Any]]:
    return repo.list_revisions(conn, recipe_id)


def selectable_revisions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return repo.selectable_revisions(conn)


def set_recipe_status(conn: sqlite3.Connection, recipe_id: int, status: str) -> dict[str, Any]:
    """Archive or reactivate a recipe. Archiving only blocks *new* selection; historical
    batches keep their references and all revision data."""
    get_recipe(conn, recipe_id)
    if status not in c.RECIPE_STATUSES:
        raise ValidationFailure({"status": "Select a valid recipe status."})
    with transaction(conn):
        repo.set_recipe_status(conn, recipe_id, status, now_iso())
    return get_recipe(conn, recipe_id)


def set_revision_status(conn: sqlite3.Connection, revision_id: int, status: str) -> dict[str, Any]:
    get_revision(conn, revision_id)
    if status not in c.RECIPE_STATUSES:
        raise ValidationFailure({"status": "Select a valid revision status."})
    with transaction(conn):
        repo.set_revision_status(conn, revision_id, status)
    return get_revision(conn, revision_id)
