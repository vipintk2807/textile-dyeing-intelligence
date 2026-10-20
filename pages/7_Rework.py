"""Rework: corrective processing events, kept apart from inspection results."""

import bootstrap  # noqa: F401  # isort: skip

import streamlit as st

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence import ui
from textile_dyeing_intelligence.errors import TDIError, ValidationFailure
from textile_dyeing_intelligence.services import batches as batch_service
from textile_dyeing_intelligence.services import quality as quality_service
from textile_dyeing_intelligence.services import rework as svc


def create_form(conn) -> None:
    fk = ui.form_key("rw_add")
    top = st.container()
    slots = ui.Slots()
    batch_id = ui.batch_select(conn, "Batch (choose first; this loads its inspections)", f"{fk}_batch", slots=slots)
    with st.form(fk):
        inspections = quality_service.list_inspections(conn, batch_id=batch_id) if batch_id else []
        labels = {}
        for i in inspections:
            outcome = c.QUALITY_DISPOSITION_LABELS[i["disposition"]]
            labels[i["id"]] = f"{i['inspection_code']} - {i['inspection_type']} ({outcome}, {i['inspected_at'][:16]})"
        insp = st.selectbox(
            "Related inspection (optional)",
            [None, *labels],
            key=f"{fk}_insp",
            format_func=lambda i: "(none)" if i is None else labels[i],
            help="Choose the inspection that led to this rework. The original result stays unchanged.",
        )
        slots.after("inspection_id")
        reason = st.text_input(ui.req("Reason"), key=f"{fk}_reason", max_chars=200)
        slots.after("reason")
        status = st.selectbox(
            ui.req("Rework status"), c.REWORK_STATUSES, format_func=lambda s: c.REWORK_STATUS_LABELS[s], key=f"{fk}_st"
        )
        desc = st.text_area("Description of corrective work (required once completed)", key=f"{fk}_desc")
        slots.after("corrective_description")
        tcols = st.columns(2)
        start = tcols[0].text_input("Start (YYYY-MM-DD HH:MM, optional)", key=f"{fk}_start")
        end = tcols[1].text_input("Completion (YYYY-MM-DD HH:MM, required once completed)", key=f"{fk}_end")
        slots.after("started_at")
        slots.after("completed_at")
        notes = st.text_area("Notes (optional)", key=f"{fk}_notes")
        submitted = st.form_submit_button("Create Rework Record")
    st.caption("Chemicals used during rework must be recorded on the Chemical Consumption page.")
    if submitted:
        data = {
            "batch_id": batch_id,
            "inspection_id": insp,
            "reason": reason,
            "status": status,
            "corrective_description": desc,
            "started_at": start,
            "completed_at": end,
            "notes": notes,
        }
        try:
            saved = svc.create_rework(conn, data)
            ui.saved("rw_add", f"Rework record {saved['rework_code']} created successfully.")
        except ValidationFailure as exc:
            ui.show_failure(top, slots, exc)
        except TDIError as exc:
            top.error(str(exc))


def update_form(conn, rw: dict) -> None:
    allowed = c.REWORK_TRANSITIONS[rw["status"]]
    fk = ui.form_key(f"rw_upd_{rw['id']}")
    top = st.container()
    closed = not allowed
    with st.form(fk):
        statuses = [rw["status"], *allowed]
        status = st.selectbox(
            "Status", statuses, format_func=lambda s: c.REWORK_STATUS_LABELS[s], key=f"{fk}_s", disabled=closed
        )
        desc = st.text_area(
            "Description of corrective work", value=rw["corrective_description"] or "", key=f"{fk}_d", disabled=closed
        )
        tcols = st.columns(2)
        start = tcols[0].text_input(
            "Start (YYYY-MM-DD HH:MM)",
            value=(rw["started_at"] or "").replace("T", " ")[:16],
            key=f"{fk}_a",
            disabled=closed,
        )
        end = tcols[1].text_input(
            "Completion (YYYY-MM-DD HH:MM)",
            value=(rw["completed_at"] or "").replace("T", " ")[:16],
            key=f"{fk}_e",
            disabled=closed,
        )
        notes = st.text_area("Notes", value=rw["notes"] or "", key=f"{fk}_n")
        submitted = st.form_submit_button("Update Rework")
    st.caption("Completing rework does not mark the batch as passed. Record a follow-up inspection for that.")
    if submitted:
        try:
            svc.update_rework(
                conn,
                rw["id"],
                {
                    "status": status,
                    "corrective_description": desc,
                    "started_at": start,
                    "completed_at": end,
                    "notes": notes,
                },
            )
            ui.saved(f"rw_upd_{rw['id']}", f"Rework {rw['rework_code']} updated successfully.")
        except ValidationFailure as exc:
            ui.show_failure(top, None, exc)
        except TDIError as exc:
            top.error(str(exc))


def body(conn) -> None:
    list_tab, add_tab = st.tabs(["Rework records", "New rework record"])
    batches = {b["id"]: b["batch_code"] for b in batch_service.batch_options(conn)}
    with list_tab:
        cols = st.columns(4)
        batch_id = cols[0].selectbox(
            "Batch", [None, *batches], key="rw_batch", format_func=lambda i: "All batches" if i is None else batches[i]
        )
        status = cols[1].selectbox(
            "Status",
            [None, *c.REWORK_STATUSES],
            key="rw_status",
            format_func=lambda s: "All statuses" if s is None else c.REWORK_STATUS_LABELS[s],
        )
        reason = cols[2].text_input("Reason contains", key="rw_reason")
        start = cols[3].date_input("From", value=None, key="rw_from")
        end = st.date_input("To", value=None, key="rw_to")
        if start and end and start > end:
            st.error("End date must not be earlier than the start date.")
            return
        items = svc.with_subsequent_inspection(
            conn,
            svc.list_rework(
                conn,
                batch_id=batch_id,
                status=status,
                reason=reason or None,
                start_date=ui.date_str(start),
                end_date=ui.date_str(end),
                limit=500,
            ),
        )
        rows = []
        for r in items:
            sub = r["subsequent_inspection"]
            outcome = (
                "Unavailable (no related inspection)"
                if not r["subsequent_available"]
                else "None recorded yet"
                if sub is None
                else f"{sub['inspection_code']}: {c.QUALITY_DISPOSITION_LABELS[sub['disposition']]}"
            )
            rows.append(
                {
                    "Rework": r["rework_code"],
                    "Batch ID": r["batch_code"],
                    "Related inspection": r["related_inspection_code"],
                    "Reason": r["reason"],
                    "Status": ui.status_text(r["status"], c.REWORK_STATUS_LABELS),
                    "Started": r["started_at"],
                    "Completed": r["completed_at"],
                    "Subsequent inspection": outcome,
                }
            )
        picked = ui.table(rows, key="rw_table", selectable=True, empty="No rework records match the selected filters.")
        if picked is not None:
            st.subheader(f"Rework {items[picked]['rework_code']}")
            update_form(conn, items[picked])
    with add_tab:
        create_form(conn)


ui.run_page("Rework", "Record corrective processing events. Original inspection results are never overwritten.", body)
