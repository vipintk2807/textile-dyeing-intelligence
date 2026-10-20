"""Small deterministic SYNTHETIC records for tests (not real production data)."""

from __future__ import annotations

from textile_dyeing_intelligence.services import batches, machines, quality, recipes


def make_machine(conn, code="T-M1", status="available"):
    return machines.create_machine(conn, {"machine_code": code, "name": f"Test machine {code}", "status": status})


def make_recipe(conn, code="T-R1", revision="A", quantity="10"):
    return recipes.create_recipe(
        conn,
        {"recipe_code": code, "name": f"Test recipe {code}"},
        {
            "revision_code": revision,
            "ingredients": [{"material_name": "Test Salt", "quantity": quantity, "unit": "kg"}],
        },
    )


def make_batch(conn, code="T-B1", revision_id=None, machine_id=None, **extra):
    data = {
        "batch_code": code,
        "material_description": "Test fabric",
        "quantity": "100",
        "quantity_unit": "kg",
        "recipe_revision_id": revision_id,
        "machine_id": machine_id,
        "planned_date": "2026-03-01",
        **extra,
    }
    return batches.create_batch(conn, data)


def make_inspection(conn, batch_id, disposition, when="2026-03-02 10:00", kind="Final"):
    return quality.create_inspection(
        conn, {"batch_id": batch_id, "inspection_type": kind, "inspected_at": when, "disposition": disposition}
    )
