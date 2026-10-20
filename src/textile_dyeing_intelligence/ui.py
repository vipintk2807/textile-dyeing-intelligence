"""Shared Streamlit helpers: page frame, database access, forms, tables.

Only presentation concerns live here. Validation, calculations and SQL stay in the
services, reporting and repositories packages.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any

import streamlit as st

from . import constants as c
from .config import APP_NAME, MISSING_LABEL, resolve_db_path
from .database import initialize_database, open_connection
from .decimals import format_decimal
from .errors import TDIError, ValidationFailure
from .services import batches as batches_service

logger = logging.getLogger("textile_dyeing_intelligence")

SYMBOLS = {
    "planned": "○",
    "in_progress": "◐",
    "completed": "●",
    "cancelled": "✕",
    "pending": "…",
    "passed": "✓",
    "failed": "✗",
    "required": "!",
    "available": "●",
    "unavailable": "✕",
    "maintenance": "◐",
    "active": "●",
    "archived": "✕",
}


def status_text(key: str | None, labels: dict[str, str]) -> str:
    """Status as text plus a symbol, so meaning never depends on colour alone."""
    if not key:
        return MISSING_LABEL
    return f"{SYMBOLS.get(key, '')} {labels.get(key, key)}".strip()


# --- Database ------------------------------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _ensure_database(path: str) -> int:
    return initialize_database(path)


@contextmanager
def connection() -> Iterator[Any]:
    path = resolve_db_path()
    _ensure_database(str(path))
    with open_connection(path) as conn:
        yield conn


def _is_streamlit_control_exception(exc: BaseException) -> bool:
    return type(exc).__module__.startswith("streamlit")


def run_page(title: str, description: str, body: Callable[[Any], None]) -> None:
    """Standard page frame: title, description, feedback, database and error boundary."""
    st.title(title)
    st.caption(description)
    show_flash()
    try:
        with connection() as conn:
            body(conn)
    except TDIError as exc:
        st.error(str(exc))
    except Exception as exc:
        if _is_streamlit_control_exception(exc):
            raise
        logger.exception("Unexpected error on page %s", title)
        st.error(
            "Something unexpected went wrong and the operation was not completed. "
            "Nothing was reported as saved. Please try again; if it keeps happening, "
            "check the application log."
        )


# --- Feedback ------------------------------------------------------------------------------


def flash(message: str) -> None:
    st.session_state.setdefault("_flash", []).append(message)


def show_flash() -> None:
    for message in st.session_state.pop("_flash", []):
        st.success(message)


def show_failure(container: Any, slots: Slots | None, exc: ValidationFailure) -> None:
    """Summary at the top of the form, plus a message next to each affected field."""
    if slots:
        slots.show(exc.errors)
    lines = "\n".join(f"- {m}" for m in exc.errors.values())
    container.error(f"Nothing was saved. Please correct the following:\n\n{lines}")


class Slots:
    """Placeholders placed right after each control so errors appear next to the field."""

    def __init__(self) -> None:
        self._slots: dict[str, Any] = {}

    def after(self, name: str) -> None:
        self._slots[name] = st.empty()

    def show(self, errors: dict[str, str]) -> dict[str, str]:
        unplaced = {}
        for key, message in errors.items():
            slot = self._slots.get(key) or self._slots.get(key.split("[")[0])
            if slot is None:
                unplaced[key] = message
            else:
                slot.markdown(f":red[**Error:** {message}]")
        return unplaced


def form_key(name: str) -> str:
    """Form widgets get a new key after every successful save, which empties the form and
    discards any queued duplicate click."""
    return f"{name}_{st.session_state.get('_fv_' + name, 0)}"


def reset_form(name: str) -> None:
    st.session_state["_fv_" + name] = st.session_state.get("_fv_" + name, 0) + 1


def saved(form_name: str, message: str) -> None:
    """Call only after the service call returned (the transaction has committed)."""
    flash(message)
    reset_form(form_name)
    st.rerun()


# --- Controls ------------------------------------------------------------------------------


def req(label: str) -> str:
    return f"{label} *"


def date_str(value: date | None) -> str | None:
    return value.isoformat() if value else None


def unit_input(
    label: str,
    key: str,
    options: Sequence[str],
    *,
    optional: bool = False,
    default: str | None = None,
    help: str | None = None,
) -> str | None:
    """Choose a common unit or type another one. No unit conversion is ever applied."""
    none_label = "(no unit)"
    choices = ([none_label] if optional else []) + list(options) + ["Other (type below)"]
    index = choices.index(default) if default in choices else 0
    choice = st.selectbox(label, choices, index=index, key=key + "_sel", help=help)
    custom = st.text_input("Other unit (only if 'Other' is selected)", key=key + "_other", max_chars=20)
    if choice == "Other (type below)":
        return custom.strip() or None
    if choice == none_label:
        return None
    return choice


def display_value(value: Any) -> Any:
    if value is None:
        return MISSING_LABEL
    if isinstance(value, Decimal):
        return format_decimal(value)
    return value


def table(
    rows: list[dict[str, Any]],
    columns: Sequence[str] | None = None,
    *,
    key: str | None = None,
    selectable: bool = False,
    empty: str = "No records match.",
) -> int | None:
    """Show rows; returns the selected row index when ``selectable``."""
    if not rows:
        st.info(empty)
        return None
    cols = list(columns) if columns else list(rows[0].keys())
    data = [{col: display_value(row.get(col)) for col in cols} for row in rows]
    if selectable:
        event = st.dataframe(
            data, hide_index=True, width="stretch", key=key, on_select="rerun", selection_mode="single-row"
        )
        picked = event.selection.rows if event and event.selection else []
        return picked[0] if picked else None
    st.dataframe(data, hide_index=True, width="stretch", key=key)
    return None


def quantity_text(quantity: str | None, unit: str | None) -> str:
    if quantity is None:
        return MISSING_LABEL
    return f"{quantity} {unit}".strip() if unit else quantity


def batch_select(
    conn: Any, label: str, key: str, *, slots: Slots | None = None, slot_name: str = "batch_id", required: bool = True
) -> int | None:
    options = batches_service.batch_options(conn)
    if not options:
        st.info("No batches exist yet. Create a batch first.")
        if slots:
            slots.after(slot_name)
        return None
    ids = [o["id"] for o in options]
    labels = {
        o["id"]: f"{o['batch_code']} - {o['material_description']} ({c.BATCH_STATUS_LABELS[o['status']]})"
        for o in options
    }
    preselect = st.session_state.get("preselect_batch_id")
    index = ids.index(preselect) if preselect in ids else 0
    value = st.selectbox(req(label) if required else label, ids, index=index, key=key, format_func=lambda i: labels[i])
    if slots:
        slots.after(slot_name)
    return value


def go_to(page: str, batch_id: int | None = None) -> None:
    if batch_id is not None:
        st.session_state["preselect_batch_id"] = batch_id
    st.switch_page(page)


def app_title() -> str:
    return APP_NAME
