"""Controlled vocabularies, labels and status-transition rules."""

from __future__ import annotations

# --- Production status (independent of quality and rework) -----------------------------
BATCH_STATUSES = ("planned", "in_progress", "completed", "cancelled")
BATCH_STATUS_LABELS = {
    "planned": "Planned",
    "in_progress": "In progress",
    "completed": "Completed",
    "cancelled": "Cancelled",
}
#: Allowed production-status transitions. Completed and cancelled are terminal.
BATCH_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "planned": ("in_progress", "cancelled"),
    "in_progress": ("planned", "completed", "cancelled"),
    "completed": (),
    "cancelled": (),
}
#: Statuses whose recipe revision, machine and quantity are locked.
BATCH_LOCKED_STATUSES = ("completed", "cancelled")

# --- Machines (administrative record, not telemetry) -----------------------------------
MACHINE_STATUSES = ("available", "unavailable", "maintenance")
MACHINE_STATUS_LABELS = {
    "available": "Available",
    "unavailable": "Unavailable",
    "maintenance": "Maintenance",
}

# --- Recipes ---------------------------------------------------------------------------
RECIPE_STATUSES = ("active", "archived")
RECIPE_STATUS_LABELS = {"active": "Active", "archived": "Archived"}

# --- Consumption -----------------------------------------------------------------------
CONSUMPTION_CATEGORIES = ("planned", "actual")
CONSUMPTION_CATEGORY_LABELS = {"planned": "Planned", "actual": "Actual"}

# --- Process records -------------------------------------------------------------------
PROCESS_SOURCES = ("operator_entry", "document_transcription", "other_documented")
PROCESS_SOURCE_LABELS = {
    "operator_entry": "Operator entry (manual)",
    "document_transcription": "Transcribed from a document",
    "other_documented": "Other documented source",
}

# --- Quality ---------------------------------------------------------------------------
QUALITY_DISPOSITIONS = ("pending", "passed", "failed")
QUALITY_DISPOSITION_LABELS = {"pending": "Pending", "passed": "Passed", "failed": "Failed"}
FINAL_DISPOSITIONS = ("passed", "failed")

# --- Rework ----------------------------------------------------------------------------
REWORK_STATUSES = ("required", "in_progress", "completed", "cancelled")
REWORK_STATUS_LABELS = {
    "required": "Required",
    "in_progress": "In progress",
    "completed": "Completed",
    "cancelled": "Cancelled",
}
REWORK_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "required": ("in_progress", "cancelled"),
    "in_progress": ("completed", "cancelled"),
    "completed": (),
    "cancelled": (),
}
OPEN_REWORK_STATUSES = ("required", "in_progress")

# --- Unit suggestions (free text is still accepted; no automatic conversion) ------------
QUANTITY_UNITS = ("kg", "g", "L", "mL", "m", "pcs")
PROCESS_UNITS = ("°C", "min", "h", "rpm", "g/L", "%", "bar")
