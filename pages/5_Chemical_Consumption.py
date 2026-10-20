"""Chemical consumption: planned and actual quantities, and their comparison."""

import bootstrap  # noqa: F401  # isort: skip

import streamlit as st

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence import ui
from textile_dyeing_intelligence.config import UNAVAILABLE_LABEL
from textile_dyeing_intelligence.errors import TDIError, ValidationFailure
from textile_dyeing_intelligence.filters import ReportFilters
from textile_dyeing_intelligence.reporting.export import export_filename, rows_to_csv
from textile_dyeing_intelligence.reporting.reports import consumption_records_report
from textile_dyeing_intelligence.services import batches as batch_service
from textile_dyeing_intelligence.services import consumption as svc
from textile_dyeing_intelligence.services import materials as materials_service
from textile_dyeing_intelligence.timeutil import now

NEW_MATERIAL = "(add a new material...)"


def _now_text() -> str:
    return now().strftime("%Y-%m-%d %H:%M")


def add_form(conn) -> None:
    fk = ui.form_key("consumption_add")
    top = st.container()
    slots = ui.Slots()
    names = [m["name"] for m in materials_service.list_materials(conn)]
    with st.form(fk):
        batch_id = ui.batch_select(conn, "Batch", f"{fk}_batch", slots=slots)
        choice = st.selectbox(ui.req("Chemical or material"), [*names, NEW_MATERIAL], key=f"{fk}_mat")
        new_name = st.text_input("New material name (only if adding a new material)", key=f"{fk}_new", max_chars=200)
        slots.after("material_name")
        category = st.radio(
            ui.req("Quantity category"),
            c.CONSUMPTION_CATEGORIES,
            horizontal=True,
            key=f"{fk}_cat",
            format_func=lambda x: c.CONSUMPTION_CATEGORY_LABELS[x],
            help="Planned = intended quantity. Actual = quantity actually used. They are never interchangeable.",
        )
        qcols = st.columns(2)
        qty = qcols[0].text_input(ui.req("Quantity"), key=f"{fk}_qty", help="Zero is allowed; negative is not.")
        with qcols[1]:
            unit = ui.unit_input(ui.req("Unit"), f"{fk}_unit", c.QUANTITY_UNITS)
        slots.after("quantity")
        slots.after("unit")
        basis = st.text_input(
            "Measurement basis (optional)",
            key=f"{fk}_basis",
            max_chars=200,
            help="e.g. 'per batch'. Planned and actual are only compared when the basis matches.",
        )
        when = st.text_input(
            ui.req("Recording time (YYYY-MM-DD HH:MM, local time)"), value=_now_text(), key=f"{fk}_when"
        )
        slots.after("recorded_at")
        notes = st.text_area("Notes (optional)", key=f"{fk}_notes")
        submitted = st.form_submit_button("Add Consumption Record")
    if submitted:
        material = new_name if choice == NEW_MATERIAL else choice
        data = {
            "batch_id": batch_id,
            "material_name": material,
            "category": category,
            "quantity": qty,
            "unit": unit,
            "basis": basis,
            "recorded_at": when,
            "notes": notes,
        }
        try:
            svc.create_consumption_record(conn, data)
            ui.saved("consumption_add", "Consumption record saved successfully.")
        except ValidationFailure as exc:
            ui.show_failure(top, slots, exc)
        except TDIError as exc:
            top.error(str(exc))


def comparison_rows(items: list[dict]) -> list[dict]:
    rows = []
    for r in items:
        ok = r["status"] == "ok"
        pct = r["variance_percent"]
        rows.append(
            {
                "Batch ID": r["batch_code"],
                "Material": r["material_name"],
                "Planned": r["planned_total"],
                "Planned unit": r["planned_unit"],
                "Actual": r["actual_total"],
                "Actual unit": r["actual_unit"],
                "Variance (actual - planned)": (
                    f"{r['variance']:+f} {r['variance_unit']}" if ok else UNAVAILABLE_LABEL
                ),
                "Variance %": (f"{pct:+.2f} %" if pct is not None else UNAVAILABLE_LABEL),
                "Note": r["message"] or None,
            }
        )
    return rows


def body(conn) -> None:
    rec_tab, add_tab, cmp_tab = st.tabs(["Consumption records", "Add record", "Planned vs actual"])
    batches = {b["id"]: b["batch_code"] for b in batch_service.batch_options(conn)}
    with rec_tab:
        cols = st.columns(5)
        batch_id = cols[0].selectbox(
            "Batch", [None, *batches], key="cr_batch", format_func=lambda i: "All batches" if i is None else batches[i]
        )
        material = cols[1].text_input("Material contains", key="cr_mat")
        category = cols[2].selectbox(
            "Category",
            [None, *c.CONSUMPTION_CATEGORIES],
            key="cr_cat",
            format_func=lambda x: "All" if x is None else c.CONSUMPTION_CATEGORY_LABELS[x],
        )
        start = cols[3].date_input("From (recording date)", value=None, key="cr_from")
        end = cols[4].date_input("To", value=None, key="cr_to")
        if start and end and start > end:
            st.error("End date must not be earlier than the start date.")
        else:
            records = svc.list_consumption_records(
                conn,
                batch_id=batch_id,
                material=material or None,
                category=category,
                start_date=ui.date_str(start),
                end_date=ui.date_str(end),
                limit=500,
            )
            ui.table(
                [
                    {
                        "Batch ID": r["batch_code"],
                        "Material": r["material_name"],
                        "Category": c.CONSUMPTION_CATEGORY_LABELS[r["category"]],
                        "Quantity": r["quantity"],
                        "Unit": r["unit"],
                        "Basis": r["basis"] or None,
                        "Recorded at": r["recorded_at"],
                        "Notes": r["notes"],
                    }
                    for r in records
                ],
                empty="No consumption records match the selected filters.",
            )
            if records:
                rep = consumption_records_report(
                    conn, ReportFilters(ui.date_str(start), ui.date_str(end), material=material or None)
                )
                if batch_id is None and category is None:
                    st.download_button(
                        "Download these records (CSV)",
                        rows_to_csv(rep.columns, rep.rows),
                        file_name=export_filename("consumption_records", ui.date_str(start), ui.date_str(end)),
                        mime="text/csv",
                        key="cr_dl",
                    )
                else:
                    st.caption("For a CSV export that matches exactly this view, use the Reports page.")
    with add_tab:
        add_form(conn)
    with cmp_tab:
        st.caption(
            "Variance = actual - planned; percentage = (actual - planned) / planned x 100. "
            "Only the same material, unit and measurement basis are compared; nothing is converted or combined."
        )
        pick = st.selectbox(
            "Batch", [None, *batches], key="cmp_batch", format_func=lambda i: "All batches" if i is None else batches[i]
        )
        items = svc.compare_for_batch(conn, pick) if pick else svc.compare_for_filters(conn, ReportFilters())
        ui.table(comparison_rows(items), empty="No consumption records to compare yet.")


ui.run_page(
    "Chemical Consumption", "Record planned and actual quantities per batch and compare them like for like.", body
)
