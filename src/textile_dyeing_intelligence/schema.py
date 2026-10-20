"""Database schema and ordered migrations.

Schema versioning uses ``PRAGMA user_version``. To change the schema after release, append a
new ``(version, sql)`` entry to ``MIGRATIONS``; never edit an existing entry and never use
DROP TABLE as an update mechanism.
"""

from __future__ import annotations

TS = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]'"
DT = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"

SCHEMA_V1 = f"""
CREATE TABLE machines (
    id INTEGER PRIMARY KEY,
    machine_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    machine_type TEXT,
    capacity TEXT,
    capacity_unit TEXT,
    status TEXT NOT NULL CHECK (status IN ('available','unavailable','maintenance')),
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK ((capacity IS NULL) = (capacity_unit IS NULL))
);

CREATE TABLE recipes (
    id INTEGER PRIMARY KEY,
    recipe_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    description TEXT,
    applicable_material TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE recipe_revisions (
    id INTEGER PRIMARY KEY,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE RESTRICT,
    revision_code TEXT NOT NULL COLLATE NOCASE,
    description TEXT,
    effective_date TEXT CHECK (effective_date IS NULL OR effective_date GLOB {DT}),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (recipe_id, revision_code)
);

CREATE TABLE chemical_materials (
    id INTEGER PRIMARY KEY,
    material_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_at TEXT NOT NULL
);

CREATE TABLE recipe_ingredients (
    id INTEGER PRIMARY KEY,
    revision_id INTEGER NOT NULL REFERENCES recipe_revisions(id) ON DELETE RESTRICT,
    material_id INTEGER NOT NULL REFERENCES chemical_materials(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL,
    quantity TEXT NOT NULL CHECK (CAST(quantity AS REAL) > 0),
    unit TEXT NOT NULL,
    dosing_basis TEXT,
    notes TEXT
);

CREATE TABLE batches (
    id INTEGER PRIMARY KEY,
    batch_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    work_order_ref TEXT,
    material_description TEXT NOT NULL,
    quantity TEXT NOT NULL CHECK (CAST(quantity AS REAL) > 0),
    quantity_unit TEXT NOT NULL,
    recipe_revision_id INTEGER REFERENCES recipe_revisions(id) ON DELETE RESTRICT,
    machine_id INTEGER REFERENCES machines(id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','in_progress','completed','cancelled')),
    planned_date TEXT CHECK (planned_date IS NULL OR planned_date GLOB {DT}),
    actual_start TEXT CHECK (actual_start IS NULL OR actual_start GLOB {TS}),
    actual_end TEXT CHECK (actual_end IS NULL OR actual_end GLOB {TS}),
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE process_records (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
    parameter_name TEXT NOT NULL,
    value TEXT NOT NULL CHECK (CAST(value AS REAL) >= 0),
    unit TEXT,
    observed_at TEXT NOT NULL CHECK (observed_at GLOB {TS}),
    recorded_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'operator_entry'
        CHECK (source IN ('operator_entry','document_transcription','other_documented')),
    notes TEXT
);

CREATE TABLE process_record_history (
    id INTEGER PRIMARY KEY,
    process_record_id INTEGER NOT NULL REFERENCES process_records(id) ON DELETE RESTRICT,
    changed_at TEXT NOT NULL,
    previous_parameter_name TEXT NOT NULL,
    previous_value TEXT NOT NULL,
    previous_unit TEXT,
    previous_observed_at TEXT NOT NULL,
    previous_source TEXT NOT NULL,
    previous_notes TEXT
);

CREATE TABLE consumption_records (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
    material_id INTEGER NOT NULL REFERENCES chemical_materials(id) ON DELETE RESTRICT,
    category TEXT NOT NULL CHECK (category IN ('planned','actual')),
    quantity TEXT NOT NULL CHECK (CAST(quantity AS REAL) >= 0),
    unit TEXT NOT NULL,
    basis TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL CHECK (recorded_at GLOB {TS}),
    created_at TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE quality_inspections (
    id INTEGER PRIMARY KEY,
    inspection_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
    inspection_type TEXT NOT NULL,
    inspected_at TEXT NOT NULL CHECK (inspected_at GLOB {TS}),
    inspector TEXT,
    disposition TEXT NOT NULL DEFAULT 'pending'
        CHECK (disposition IN ('pending','passed','failed')),
    finalised_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE quality_measurements (
    id INTEGER PRIMARY KEY,
    inspection_id INTEGER NOT NULL REFERENCES quality_inspections(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    value TEXT NOT NULL CHECK (CAST(value AS REAL) >= 0),
    unit TEXT,
    context TEXT
);

CREATE TABLE quality_defects (
    id INTEGER PRIMARY KEY,
    inspection_id INTEGER NOT NULL REFERENCES quality_inspections(id) ON DELETE RESTRICT,
    category TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE rework_records (
    id INTEGER PRIMARY KEY,
    rework_code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE RESTRICT,
    inspection_id INTEGER REFERENCES quality_inspections(id) ON DELETE RESTRICT,
    reason TEXT NOT NULL,
    corrective_description TEXT,
    status TEXT NOT NULL DEFAULT 'required'
        CHECK (status IN ('required','in_progress','completed','cancelled')),
    started_at TEXT CHECK (started_at IS NULL OR started_at GLOB {TS}),
    completed_at TEXT CHECK (completed_at IS NULL OR completed_at GLOB {TS}),
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexes for the actual filter and join patterns.
CREATE INDEX ix_batches_status ON batches(status);
CREATE INDEX ix_batches_machine ON batches(machine_id);
CREATE INDEX ix_batches_revision ON batches(recipe_revision_id);
CREATE INDEX ix_batches_planned_date ON batches(planned_date);
CREATE INDEX ix_revisions_recipe ON recipe_revisions(recipe_id);
CREATE INDEX ix_ingredients_revision ON recipe_ingredients(revision_id);
CREATE INDEX ix_process_batch ON process_records(batch_id, observed_at);
CREATE INDEX ix_consumption_batch ON consumption_records(batch_id, material_id);
CREATE INDEX ix_consumption_recorded ON consumption_records(recorded_at);
CREATE INDEX ix_inspections_batch ON quality_inspections(batch_id, inspected_at);
CREATE INDEX ix_measurements_inspection ON quality_measurements(inspection_id);
CREATE INDEX ix_defects_inspection ON quality_defects(inspection_id);
CREATE INDEX ix_rework_batch ON rework_records(batch_id);
CREATE INDEX ix_rework_inspection ON rework_records(inspection_id);

-- Duplicate-submission safeguards (an identical entry cannot be saved twice).
CREATE UNIQUE INDEX ux_process_duplicate ON process_records(
    batch_id, parameter_name COLLATE NOCASE, observed_at, value, COALESCE(unit, ''));
CREATE UNIQUE INDEX ux_consumption_duplicate ON consumption_records(
    batch_id, material_id, category, quantity, unit, basis, recorded_at);
CREATE UNIQUE INDEX ux_inspection_duplicate ON quality_inspections(
    batch_id, inspection_type COLLATE NOCASE, inspected_at);

-- Historical integrity rules enforced by the database itself.
CREATE TRIGGER trg_ingredients_no_insert_when_used
BEFORE INSERT ON recipe_ingredients
WHEN EXISTS (SELECT 1 FROM batches WHERE recipe_revision_id = NEW.revision_id)
BEGIN
    SELECT RAISE(ABORT, 'TDI: This recipe revision is used by a batch and cannot be changed. Create a new revision.');
END;

CREATE TRIGGER trg_ingredients_no_update_when_used
BEFORE UPDATE ON recipe_ingredients
WHEN EXISTS (SELECT 1 FROM batches WHERE recipe_revision_id IN (OLD.revision_id, NEW.revision_id))
BEGIN
    SELECT RAISE(ABORT, 'TDI: This recipe revision is used by a batch and cannot be changed. Create a new revision.');
END;

CREATE TRIGGER trg_ingredients_no_delete_when_used
BEFORE DELETE ON recipe_ingredients
WHEN EXISTS (SELECT 1 FROM batches WHERE recipe_revision_id = OLD.revision_id)
BEGIN
    SELECT RAISE(ABORT, 'TDI: This recipe revision is used by a batch and cannot be changed. Create a new revision.');
END;

CREATE TRIGGER trg_inspection_final_immutable
BEFORE UPDATE ON quality_inspections
WHEN OLD.disposition IN ('passed','failed') AND (
        NEW.disposition IS NOT OLD.disposition
     OR NEW.batch_id IS NOT OLD.batch_id
     OR NEW.inspected_at IS NOT OLD.inspected_at
     OR NEW.inspection_type IS NOT OLD.inspection_type
     OR NEW.inspection_code IS NOT OLD.inspection_code)
BEGIN
    SELECT RAISE(ABORT, 'TDI: A finalised inspection cannot be changed. Record a follow-up inspection instead.');
END;

CREATE TRIGGER trg_inspection_final_no_delete
BEFORE DELETE ON quality_inspections
WHEN OLD.disposition IN ('passed','failed')
BEGIN
    SELECT RAISE(ABORT, 'TDI: A finalised inspection cannot be deleted.');
END;

CREATE TRIGGER trg_rework_inspection_same_batch_insert
BEFORE INSERT ON rework_records
WHEN NEW.inspection_id IS NOT NULL
 AND (SELECT batch_id FROM quality_inspections WHERE id = NEW.inspection_id) IS NOT NEW.batch_id
BEGIN
    SELECT RAISE(ABORT, 'TDI: The related inspection belongs to a different batch.');
END;

CREATE TRIGGER trg_rework_inspection_same_batch_update
BEFORE UPDATE OF batch_id, inspection_id ON rework_records
WHEN NEW.inspection_id IS NOT NULL
 AND (SELECT batch_id FROM quality_inspections WHERE id = NEW.inspection_id) IS NOT NEW.batch_id
BEGIN
    SELECT RAISE(ABORT, 'TDI: The related inspection belongs to a different batch.');
END;
"""

#: Ordered migrations. Each entry is applied atomically together with its version bump.
MIGRATIONS: tuple[tuple[int, str], ...] = ((1, SCHEMA_V1),)

LATEST_VERSION = MIGRATIONS[-1][0]

EXPECTED_TABLES = (
    "machines",
    "recipes",
    "recipe_revisions",
    "chemical_materials",
    "recipe_ingredients",
    "batches",
    "process_records",
    "process_record_history",
    "consumption_records",
    "quality_inspections",
    "quality_measurements",
    "quality_defects",
    "rework_records",
)
