"""Process records: observations and parameters recorded for a batch."""

import bootstrap  # noqa: F401  # isort: skip

import streamlit as st

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence import ui
from textile_dyeing_intelligence.errors import TDIError, ValidationFailure
from textile_dyeing_intelligence.services import batches as batch_service
from textile_dyeing_intelligence.services import process_records as svc
from textile_dyeing_intelligence.timeutil import now


def _now_text() -> str:
    return now().strftime("%Y-%m-%d %H:%M")


def record_form(conn, name: str, existing: dict | None = None) -> None:
    editing = existing is not None
    ex = existing or {}
    fk = ui.form_key(name)
    top = st.container()
    slots = ui.Slots()
    with st.form(fk):
        if editing:
            st.text_input("Batch", value=ex["batch_code"], disabled=True, key=f"{fk}_b")
            batch_id = ex["batch_id"]
        else:
            batch_id = ui.batch_select(conn, "Batch", f"{fk}_batch", slots=slots)
        pname = st.text_input(
            ui.req("Parameter name"),
            value=ex.get("parameter_name", ""),
            key=f"{fk}_p",
            max_chars=200,
            help="e.g. Temperature, Duration, pH",
        )
        slots.after("parameter_name")
        vcols = st.columns(2)
        value = vcols[0].text_input(ui.req("Recorded value"), value=ex.get("value", ""), key=f"{fk}_v")
        with vcols[1]:
            unit = ui.unit_input("Unit", f"{fk}_u", c.PROCESS_UNITS, optional=True, default=ex.get("unit"))
        slots.after("value")
        observed = st.text_input(
            ui.req("Observation time (YYYY-MM-DD HH:MM, local time)"),
            value=(ex.get("observed_at") or _now_text()).replace("T", " ")[:16],
            key=f"{fk}_o",
            help="When the condition was observed. The time you save it is stored separately.",
        )
        slots.after("observed_at")
        source = st.selectbox(
            "Source",
            c.PROCESS_SOURCES,
            format_func=lambda s: c.PROCESS_SOURCE_LABELS[s],
            index=c.PROCESS_SOURCES.index(ex.get("source", "operator_entry")),
            key=f"{fk}_s",
            help="Values entered here are not sensor readings.",
        )
        notes = st.text_area("Notes (optional)", value=ex.get("notes") or "", key=f"{fk}_n")
        submitted = st.form_submit_button("Save Correction" if editing else "Add Process Record")
    if submitted:
        data = {
            "batch_id": batch_id,
            "parameter_name": pname,
            "value": value,
            "unit": unit,
            "observed_at": observed,
            "source": source,
            "notes": notes,
        }
        try:
            if editing:
                svc.update_process_record(conn, ex["id"], data)
                ui.saved(name, "Process record corrected successfully. The previous values are kept in its history.")
            else:
                svc.create_process_record(conn, data)
                ui.saved(name, "Process record saved successfully.")
        except ValidationFailure as exc:
            ui.show_failure(top, slots, exc)
        except TDIError as exc:
            top.error(str(exc))


def body(conn) -> None:
    list_tab, add_tab = st.tabs(["Process records", "Add process record"])
    with list_tab:
        cols = st.columns(4)
        batches = {b["id"]: b["batch_code"] for b in batch_service.batch_options(conn)}
        batch_id = cols[0].selectbox(
            "Batch", [None, *batches], key="pr_batch", format_func=lambda i: "All batches" if i is None else batches[i]
        )
        parameter = cols[1].text_input("Parameter name contains", key="pr_param")
        start = cols[2].date_input("From (observation date)", value=None, key="pr_from")
        end = cols[3].date_input("To", value=None, key="pr_to")
        if start and end and start > end:
            st.error("End date must not be earlier than the start date.")
            return
        records = svc.list_process_records(
            conn,
            batch_id=batch_id,
            parameter=parameter or None,
            start_date=ui.date_str(start),
            end_date=ui.date_str(end),
            limit=500,
        )
        rows = [
            {
                "Batch ID": r["batch_code"],
                "Parameter": r["parameter_name"],
                "Value": r["value"],
                "Unit": r["unit"],
                "Observed at": r["observed_at"],
                "Recorded at": r["recorded_at"],
                "Source": c.PROCESS_SOURCE_LABELS[r["source"]],
                "Notes": r["notes"],
            }
            for r in records
        ]
        picked = ui.table(rows, key="pr_table", selectable=True, empty="No process records match the selected filters.")
        if picked is not None:
            rec = records[picked]
            st.subheader(f"Record {rec['id']} - {rec['parameter_name']} for batch {rec['batch_code']}")
            with st.expander("Correct this record", expanded=True):
                record_form(conn, f"pr_edit_{rec['id']}", rec)
            history = svc.record_history(conn, rec["id"])
            if history:
                st.markdown("**Change history (previous values)**")
                ui.table(
                    [
                        {
                            "Changed at": h["changed_at"],
                            "Parameter": h["previous_parameter_name"],
                            "Value": h["previous_value"],
                            "Unit": h["previous_unit"],
                            "Observed at": h["previous_observed_at"],
                        }
                        for h in history
                    ]
                )
    with add_tab:
        record_form(conn, "pr_add")


ui.run_page("Process Records", "Record process parameters and observations for a batch (manual entries).", body)
