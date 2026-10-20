"""Batches: create, search, review and update dyeing batches."""

import bootstrap  # noqa: F401  # isort: skip

from datetime import date

import streamlit as st

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence import ui
from textile_dyeing_intelligence.config import MISSING_LABEL, TABLE_ROW_LIMIT
from textile_dyeing_intelligence.errors import TDIError, ValidationFailure
from textile_dyeing_intelligence.filters import ReportFilters
from textile_dyeing_intelligence.services import batches as svc
from textile_dyeing_intelligence.services import machines as machines_service
from textile_dyeing_intelligence.services import recipes as recipes_service


def _revision_options(conn, current_id=None):
    revisions = recipes_service.selectable_revisions(conn)
    labels = {r["id"]: f"{r['recipe_code']} rev {r['revision_code']} - {r['recipe_name']}" for r in revisions}
    if current_id and current_id not in labels:
        rev = recipes_service.get_revision(conn, current_id)
        labels[current_id] = f"{rev['recipe_code']} rev {rev['revision_code']} (archived)"
    return [None, *labels], labels


def batch_form(conn, name: str, existing: dict | None = None) -> None:
    editing = existing is not None
    fk = ui.form_key(name)
    top = st.container()
    slots = ui.Slots()
    locked = editing and existing["status"] in c.BATCH_LOCKED_STATUSES
    if locked:
        st.info("This batch is completed or cancelled: quantity, recipe revision and machine are locked.")
    rev_ids, rev_labels = _revision_options(conn, (existing or {}).get("recipe_revision_id"))
    machines = machines_service.list_machines(conn)
    mach_labels = {
        m["id"]: f"{m['machine_code']} - {m['name']} ({c.MACHINE_STATUS_LABELS[m['status']]})" for m in machines
    }
    ex = existing or {}
    with st.form(fk):
        st.markdown("**Batch identity**")
        code = st.text_input(
            ui.req("Batch identifier"),
            value=ex.get("batch_code", ""),
            disabled=editing,
            key=f"{fk}_code",
            max_chars=40,
            help="Unique and permanent, e.g. B-2026-001.",
        )
        slots.after("batch_code")
        wo = st.text_input("Work-order reference (optional)", value=ex.get("work_order_ref") or "", key=f"{fk}_wo")
        desc = st.text_input(
            ui.req("Fabric or material description"),
            value=ex.get("material_description", ""),
            key=f"{fk}_desc",
            max_chars=200,
        )
        slots.after("material_description")
        qcols = st.columns(2)
        qty = qcols[0].text_input(
            ui.req("Batch quantity"),
            value=ex.get("quantity", ""),
            key=f"{fk}_qty",
            disabled=locked,
            help="Positive number, e.g. 120 or 120.5",
        )
        with qcols[1]:
            unit = ui.unit_input(
                ui.req("Quantity unit"), f"{fk}_unit", c.QUANTITY_UNITS, default=ex.get("quantity_unit")
            )
        slots.after("quantity")
        slots.after("quantity_unit")
        st.markdown("**Production associations**")
        rev = st.selectbox(
            "Recipe and revision (optional)",
            rev_ids,
            key=f"{fk}_rev",
            disabled=locked,
            index=rev_ids.index(ex.get("recipe_revision_id")) if ex.get("recipe_revision_id") in rev_ids else 0,
            format_func=lambda i: "(none yet)" if i is None else rev_labels[i],
        )
        slots.after("recipe_revision_id")
        mach_ids = [None, *mach_labels]
        mach = st.selectbox(
            "Assigned machine (optional)",
            mach_ids,
            key=f"{fk}_mach",
            disabled=locked,
            index=mach_ids.index(ex.get("machine_id")) if ex.get("machine_id") in mach_ids else 0,
            format_func=lambda i: "(not assigned)" if i is None else mach_labels[i],
        )
        slots.after("machine_id")
        st.markdown("**Timing** (local time)")
        planned_default = date.fromisoformat(ex["planned_date"]) if ex.get("planned_date") else None
        planned = st.date_input("Planned production date (optional)", value=planned_default, key=f"{fk}_planned")
        tcols = st.columns(2)
        start = tcols[0].text_input(
            "Actual start (YYYY-MM-DD HH:MM, optional)",
            key=f"{fk}_start",
            value=(ex.get("actual_start") or "").replace("T", " ")[:16],
        )
        end = tcols[1].text_input(
            "Actual completion (YYYY-MM-DD HH:MM, optional)",
            key=f"{fk}_end",
            value=(ex.get("actual_end") or "").replace("T", " ")[:16],
        )
        slots.after("actual_start")
        slots.after("actual_end")
        notes = st.text_area("Notes (optional)", value=ex.get("notes") or "", key=f"{fk}_notes")
        c1, c2 = st.columns([1, 1])
        submitted = c1.form_submit_button("Save Changes" if editing else "Save Batch")
        c2.caption("Leave the form to cancel. Nothing is saved until you press Save.")
    if submitted:
        data = {
            "batch_code": code,
            "work_order_ref": wo,
            "material_description": desc,
            "quantity": qty if not locked else ex["quantity"],
            "quantity_unit": unit if not locked else ex["quantity_unit"],
            "recipe_revision_id": rev,
            "machine_id": mach,
            "planned_date": ui.date_str(planned),
            "actual_start": start,
            "actual_end": end,
            "notes": notes,
        }
        try:
            if editing:
                svc.update_batch(conn, existing["id"], data)
                ui.saved(name, f"Batch {existing['batch_code']} updated successfully.")
            else:
                created = svc.create_batch(conn, data)
                st.session_state["open_batch_id"] = created["id"]
                ui.saved(name, f"Batch {created['batch_code']} created successfully.")
        except ValidationFailure as exc:
            ui.show_failure(top, slots, exc)
        except TDIError as exc:
            top.error(str(exc))


def status_form(conn, batch: dict) -> None:
    allowed = c.BATCH_TRANSITIONS[batch["status"]]
    if not allowed:
        st.info(f"{c.BATCH_STATUS_LABELS[batch['status']]} batches cannot change production status.")
        return
    fk = ui.form_key(f"status_{batch['id']}")
    top = st.container()
    with st.form(fk):
        new = st.selectbox(
            "New production status", allowed, format_func=lambda s: c.BATCH_STATUS_LABELS[s], key=f"{fk}_s"
        )
        start = st.text_input("Actual start (YYYY-MM-DD HH:MM, optional)", key=f"{fk}_start")
        end = st.text_input("Actual completion (YYYY-MM-DD HH:MM, optional)", key=f"{fk}_end")
        st.caption("Timestamps are stored only if you enter them. Quality and rework records are not affected.")
        submitted = st.form_submit_button("Change Status")
    if submitted:
        try:
            svc.change_status(conn, batch["id"], new, actual_start=start or None, actual_end=end or None)
            ui.saved(f"status_{batch['id']}", f"Batch status changed to {c.BATCH_STATUS_LABELS[new]}.")
        except ValidationFailure as exc:
            ui.show_failure(top, None, exc)
        except TDIError as exc:
            top.error(str(exc))


def detail_view(conn, batch_id: int) -> None:
    detail = svc.get_batch_detail(conn, batch_id)
    b = detail["batch"]
    st.divider()
    st.header(f"Batch {b['batch_code']}")
    st.caption("Production status, quality and rework are tracked separately.")
    s = st.columns(3)
    s[0].markdown(f"**Production status**  \n{ui.status_text(b['status'], c.BATCH_STATUS_LABELS)}")
    s[1].markdown(f"**Quality (latest final outcome)**  \n{b['quality_label']}")
    s[2].markdown(f"**Rework**  \n{b['rework_events']} event(s), {b['open_rework']} unresolved")
    i = st.columns(3)
    i[0].markdown(f"**Quantity**  \n{ui.quantity_text(b['quantity'], b['quantity_unit'])}")
    i[1].markdown(f"**Material**  \n{b['material_description']}")
    i[2].markdown(f"**Work-order reference**  \n{b['work_order_ref'] or MISSING_LABEL}")
    j = st.columns(3)
    rev = detail["revision"]
    j[0].markdown(
        "**Recipe revision**  \n" + (f"{rev['recipe_code']} rev {rev['revision_code']}" if rev else MISSING_LABEL)
    )
    j[1].markdown(
        "**Machine**  \n" + (f"{b['machine_code']} - {b['machine_name']}" if b["machine_code"] else MISSING_LABEL)
    )
    j[2].markdown(f"**Planned date**  \n{b['planned_date'] or MISSING_LABEL}")
    k = st.columns(3)
    k[0].markdown(f"**Actual start**  \n{b['actual_start'] or MISSING_LABEL}")
    k[1].markdown(f"**Actual completion**  \n{b['actual_end'] or MISSING_LABEL}")
    k[2].markdown(f"**Notes**  \n{b['notes'] or MISSING_LABEL}")

    with st.expander("Edit batch details"):
        batch_form(conn, f"batch_edit_{b['id']}", b)
    with st.expander("Change production status"):
        status_form(conn, b)

    tabs = st.tabs(["Recipe", "Process records", "Chemical consumption", "Quality inspections", "Rework"])
    with tabs[0]:
        if rev:
            st.caption(f"Revision {rev['revision_code']} as used by this batch (historical revisions never change).")
            ui.table(
                [
                    {
                        "Material": x["material_name"],
                        "Quantity": x["quantity"],
                        "Unit": x["unit"],
                        "Dosing basis": x["dosing_basis"],
                    }
                    for x in rev["ingredients"]
                ]
            )
        else:
            st.info("No recipe revision is associated with this batch.")
    with tabs[1]:
        ui.table(
            [
                {
                    "Parameter": p["parameter_name"],
                    "Value": p["value"],
                    "Unit": p["unit"],
                    "Observed at": p["observed_at"],
                    "Source": c.PROCESS_SOURCE_LABELS[p["source"]],
                }
                for p in detail["process_records"]
            ],
            empty="No process records have been recorded for this batch.",
        )
        if st.button("Add process record for this batch"):
            ui.go_to("pages/4_Process_Records.py", b["id"])
    with tabs[2]:
        ui.table(
            [
                {
                    "Material": r["material_name"],
                    "Category": c.CONSUMPTION_CATEGORY_LABELS[r["category"]],
                    "Quantity": r["quantity"],
                    "Unit": r["unit"],
                    "Recorded at": r["recorded_at"],
                }
                for r in detail["consumption_records"]
            ],
            empty="No consumption has been recorded for this batch.",
        )
        if detail["consumption_comparison"]:
            st.markdown("**Planned versus actual**")
            ui.table(
                [
                    {
                        "Material": r["material_name"],
                        "Planned": r["planned_total"],
                        "Planned unit": r["planned_unit"],
                        "Actual": r["actual_total"],
                        "Actual unit": r["actual_unit"],
                        "Variance": r["variance"] if r["status"] == "ok" else "Unavailable",
                        "Variance %": (
                            f"{r['variance_percent']:.2f}" if r["variance_percent"] is not None else "Unavailable"
                        ),
                        "Note": r["message"],
                    }
                    for r in detail["consumption_comparison"]
                ]
            )
        if st.button("Add consumption record for this batch"):
            ui.go_to("pages/5_Chemical_Consumption.py", b["id"])
    with tabs[3]:
        rows = []
        for q in detail["inspections"]:
            rows.append(
                {
                    "Inspection": q["inspection_code"],
                    "Type": q["inspection_type"],
                    "Inspected at": q["inspected_at"],
                    "Outcome": ui.status_text(q["disposition"], c.QUALITY_DISPOSITION_LABELS),
                    "Defects": "; ".join(d["category"] for d in q["defects"]) or None,
                    "Measurements": "; ".join(
                        f"{m['name']}: {m['value']} {m['unit'] or ''}".strip() for m in q["measurements"]
                    )
                    or None,
                }
            )
        ui.table(rows, empty="No quality inspections have been recorded for this batch.")
        if st.button("Record inspection for this batch"):
            ui.go_to("pages/6_Quality_Inspections.py", b["id"])
    with tabs[4]:
        ui.table(
            [
                {
                    "Rework": w["rework_code"],
                    "Reason": w["reason"],
                    "Status": ui.status_text(w["status"], c.REWORK_STATUS_LABELS),
                    "Related inspection": w["related_inspection_code"],
                    "Started": w["started_at"],
                    "Completed": w["completed_at"],
                }
                for w in detail["rework"]
            ],
            empty="No rework has been recorded for this batch.",
        )
        if st.button("Record rework for this batch"):
            ui.go_to("pages/7_Rework.py", b["id"])


def body(conn) -> None:
    list_tab, add_tab = st.tabs(["Batch list", "New batch"])
    with list_tab:
        cols = st.columns(4)
        search = cols[0].text_input("Search batch ID or work order", key="b_search")
        status = cols[1].selectbox(
            "Production status",
            [None, *c.BATCH_STATUSES],
            key="b_status",
            format_func=lambda s: "All statuses" if s is None else c.BATCH_STATUS_LABELS[s],
        )
        machines = {m["id"]: m["machine_code"] for m in machines_service.list_machines(conn)}
        machine = cols[2].selectbox(
            "Machine",
            [None, *machines],
            key="b_machine",
            format_func=lambda i: "All machines" if i is None else machines[i],
        )
        dcols = cols[3].columns(2)
        start = dcols[0].date_input("From", value=None, key="b_from")
        end = dcols[1].date_input("To", value=None, key="b_to")
        try:
            filters = ReportFilters(
                ui.date_str(start), ui.date_str(end), search=search, machine_id=machine, status=status
            )
            rows, total = svc.search_batches(conn, filters, limit=TABLE_ROW_LIMIT)
        except ValidationFailure as exc:
            st.error(" ".join(exc.errors.values()))
            return
        if any((search, status, machine, start, end)):
            st.caption(f"Filtered view: {total} matching batch(es).")
        if total > len(rows):
            st.warning(f"Showing the newest {len(rows)} of {total} batches. Narrow the filters to see others.")
        table_rows = [
            {
                "Batch ID": r["batch_code"],
                "Work order": r["work_order_ref"],
                "Material": r["material_description"],
                "Quantity": ui.quantity_text(r["quantity"], r["quantity_unit"]),
                "Recipe / revision": f"{r['recipe_code']} / {r['revision_code']}" if r["recipe_code"] else None,
                "Machine": r["machine_code"],
                "Production status": ui.status_text(r["status"], c.BATCH_STATUS_LABELS),
                "Reporting date": r["reporting_date"],
                "Quality": r["quality_label"],
                "Rework": f"{r['rework_events']} event(s)" if r["rework_events"] else "None",
            }
            for r in rows
        ]
        picked = ui.table(
            table_rows,
            key="batch_table",
            selectable=True,
            empty="No batches match the selected filters. Clear the filters or create a batch.",
        )
        if picked is not None:
            st.session_state["open_batch_id"] = rows[picked]["id"]
        st.caption("Select a row to open the batch.")
        open_id = st.session_state.get("open_batch_id")
        if open_id:
            try:
                detail_view(conn, open_id)
            except TDIError as exc:
                st.error(str(exc))
                st.session_state.pop("open_batch_id", None)
    with add_tab:
        batch_form(conn, "batch_add")


ui.run_page("Batches", "Create, search, review and update dyeing batches.", body)
