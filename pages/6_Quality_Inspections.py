"""Quality inspections: outcomes, measurements and defects, with full history."""

import bootstrap  # noqa: F401  # isort: skip

import streamlit as st

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence import ui
from textile_dyeing_intelligence.errors import TDIError, ValidationFailure
from textile_dyeing_intelligence.services import batches as batch_service
from textile_dyeing_intelligence.services import quality as svc
from textile_dyeing_intelligence.timeutil import now

MCOLS = ["Measurement", "Value", "Unit"]


def _now_text() -> str:
    return now().strftime("%Y-%m-%d %H:%M")


def _measurements(edited) -> list[dict]:
    rows = edited if isinstance(edited, list) else edited.to_dict("records")
    out = []
    for r in rows:
        vals = {k: ("" if r.get(k) is None else str(r.get(k)).strip()) for k in MCOLS}
        if any(vals.values()):
            out.append({"name": vals["Measurement"], "value": vals["Value"], "unit": vals["Unit"]})
    return out


def inspection_form(conn, name: str, existing: dict | None = None) -> None:
    """New inspection, or completion of a pending one."""
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
        types = svc.inspection_types(conn)
        itype = st.text_input(
            ui.req("Inspection type"),
            value=ex.get("inspection_type", ""),
            key=f"{fk}_t",
            max_chars=200,
            help="e.g. Final shade check, Follow-up shade check"
            + (f". Used before: {', '.join(types[:8])}" if types else ""),
        )
        slots.after("inspection_type")
        when = st.text_input(
            ui.req("Inspection time (YYYY-MM-DD HH:MM, local time)"),
            value=(ex.get("inspected_at") or _now_text()).replace("T", " ")[:16],
            key=f"{fk}_w",
        )
        slots.after("inspected_at")
        inspector = st.text_input("Inspector (optional)", value=ex.get("inspector") or "", key=f"{fk}_i")
        dispo = st.radio(
            ui.req("Outcome"),
            c.QUALITY_DISPOSITIONS,
            horizontal=True,
            key=f"{fk}_d",
            format_func=lambda d: c.QUALITY_DISPOSITION_LABELS[d],
            help="Pending keeps the inspection open. An empty defect list is never treated as a pass.",
        )
        st.markdown("**Measurements** (optional - only values actually measured)")
        seed = [
            {"Measurement": m["name"], "Value": m["value"], "Unit": m["unit"] or ""} for m in ex.get("measurements", [])
        ]
        edited_m = st.data_editor(
            seed or [{k: "" for k in MCOLS}],
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            key=f"{fk}_m",
            column_config={k: st.column_config.TextColumn(k) for k in MCOLS},
        )
        slots.after("measurements")
        defects_text = st.text_area(
            "Defect categories (optional, one per line)",
            key=f"{fk}_df",
            value="\n".join(d["category"] for d in ex.get("defects", [])),
        )
        slots.after("defects")
        notes = st.text_area("Notes (optional)", value=ex.get("notes") or "", key=f"{fk}_n")
        submitted = st.form_submit_button("Save Inspection")
    if submitted:
        data = {
            "batch_id": batch_id,
            "inspection_type": itype,
            "inspected_at": when,
            "inspector": inspector,
            "disposition": dispo,
            "measurements": _measurements(edited_m),
            "defects": [{"category": ln.strip()} for ln in defects_text.splitlines() if ln.strip()],
            "notes": notes,
        }
        try:
            if editing:
                saved = svc.update_pending_inspection(conn, ex["id"], data)
            else:
                saved = svc.create_inspection(conn, data)
            ui.saved(
                name,
                f"Quality inspection {saved['inspection_code']} recorded successfully "
                f"({c.QUALITY_DISPOSITION_LABELS[saved['disposition']]}).",
            )
        except ValidationFailure as exc:
            ui.show_failure(top, slots, exc)
        except TDIError as exc:
            top.error(str(exc))


def body(conn) -> None:
    list_tab, add_tab = st.tabs(["Inspection history", "Record inspection"])
    batches = {b["id"]: b["batch_code"] for b in batch_service.batch_options(conn)}
    with list_tab:
        cols = st.columns(4)
        batch_id = cols[0].selectbox(
            "Batch", [None, *batches], key="q_batch", format_func=lambda i: "All batches" if i is None else batches[i]
        )
        outcome = cols[1].selectbox(
            "Outcome",
            [None, *c.QUALITY_DISPOSITIONS],
            key="q_out",
            format_func=lambda x: "All outcomes" if x is None else c.QUALITY_DISPOSITION_LABELS[x],
        )
        start = cols[2].date_input("From (inspection date)", value=None, key="q_from")
        end = cols[3].date_input("To", value=None, key="q_to")
        if start and end and start > end:
            st.error("End date must not be earlier than the start date.")
            return
        items = svc.list_inspections(
            conn,
            batch_id=batch_id,
            outcome=outcome,
            start_date=ui.date_str(start),
            end_date=ui.date_str(end),
            limit=500,
        )
        rows = [
            {
                "Inspection": q["inspection_code"],
                "Batch ID": q["batch_code"],
                "Type": q["inspection_type"],
                "Inspected at": q["inspected_at"],
                "Outcome": ui.status_text(q["disposition"], c.QUALITY_DISPOSITION_LABELS),
                "Inspector": q["inspector"],
                "Defects": q["defect_count"],
                "Measurements": q["measurement_count"],
            }
            for q in items
        ]
        picked = ui.table(
            rows, key="q_table", selectable=True, empty="No quality inspections match the selected filters."
        )
        if picked is not None:
            q = svc.get_inspection(conn, items[picked]["id"])
            st.subheader(f"Inspection {q['inspection_code']} - batch {q['batch_code']}")
            st.markdown(
                f"**Outcome:** {ui.status_text(q['disposition'], c.QUALITY_DISPOSITION_LABELS)}  \n"
                f"**Finalised at:** {q['finalised_at'] or 'Not finalised'}"
            )
            ui.table(
                [{"Measurement": m["name"], "Value": m["value"], "Unit": m["unit"]} for m in q["measurements"]],
                empty="No measurements were recorded.",
            )
            ui.table(
                [{"Defect": d["category"]} for d in q["defects"]],
                empty="No defects were recorded (this does not mean the batch passed).",
            )
            if q["disposition"] == "pending":
                with st.expander("Complete or finalise this inspection", expanded=True):
                    inspection_form(conn, f"q_edit_{q['id']}", q)
            else:
                st.info("Finalised inspections cannot be changed. Use 'Record inspection' for a follow-up inspection.")
    with add_tab:
        st.caption("Each inspection is stored separately; a follow-up inspection never overwrites an earlier result.")
        inspection_form(conn, "q_add")


ui.run_page("Quality Inspections", "Record inspection outcomes, measurements and defects.", body)
