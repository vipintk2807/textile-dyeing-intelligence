"""Machines: maintain the catalogue of machines that batches can be assigned to."""

import bootstrap  # noqa: F401  # isort: skip

import streamlit as st

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence import ui
from textile_dyeing_intelligence.errors import TDIError, ValidationFailure
from textile_dyeing_intelligence.services import machines as svc

STATUS_FORMAT = lambda s: c.MACHINE_STATUS_LABELS[s]  # noqa: E731


def machine_form(conn, name: str, existing: dict | None = None) -> None:
    fk = ui.form_key(name)
    top = st.container()
    slots = ui.Slots()
    editing = existing is not None
    with st.form(fk):
        code = st.text_input(
            ui.req("Machine identifier"),
            value=existing["machine_code"] if editing else "",
            disabled=editing,
            key=f"{fk}_code",
            max_chars=40,
            help="Unique and permanent, e.g. M-01.",
        )
        slots.after("machine_code")
        machine_name = st.text_input(
            ui.req("Machine name"), value=existing["name"] if editing else "", key=f"{fk}_name", max_chars=200
        )
        slots.after("name")
        mtype = st.text_input(
            "Machine type (optional)", value=(existing or {}).get("machine_type") or "", key=f"{fk}_type", max_chars=200
        )
        cap_cols = st.columns(2)
        capacity = cap_cols[0].text_input(
            "Capacity (optional - only if verified)", value=(existing or {}).get("capacity") or "", key=f"{fk}_cap"
        )
        cap_unit = cap_cols[1].text_input(
            "Capacity unit", value=(existing or {}).get("capacity_unit") or "", key=f"{fk}_capu", max_chars=20
        )
        slots.after("capacity")
        status = st.selectbox(
            ui.req("Recorded status"),
            c.MACHINE_STATUSES,
            format_func=STATUS_FORMAT,
            index=c.MACHINE_STATUSES.index(existing["status"]) if editing else 0,
            key=f"{fk}_status",
            help="Administrative record only; not read from the machine.",
        )
        notes = st.text_area("Notes (optional)", value=(existing or {}).get("notes") or "", key=f"{fk}_notes")
        submitted = st.form_submit_button("Save Machine" if editing else "Add Machine")
    if submitted:
        data = {
            "machine_code": code,
            "name": machine_name,
            "machine_type": mtype,
            "capacity": capacity,
            "capacity_unit": cap_unit,
            "status": status,
            "notes": notes,
        }
        try:
            if editing:
                svc.update_machine(conn, existing["id"], data)
                ui.saved(name, "Machine updated successfully.")
            else:
                saved = svc.create_machine(conn, data)
                ui.saved(name, f"Machine {saved['machine_code']} created successfully.")
        except ValidationFailure as exc:
            ui.show_failure(top, slots, exc)
        except TDIError as exc:
            top.error(str(exc))


def body(conn) -> None:
    list_tab, add_tab = st.tabs(["Machine list", "Add machine"])
    with list_tab:
        cols = st.columns(2)
        search = cols[0].text_input("Search by identifier or name", key="mach_search")
        status = cols[1].selectbox(
            "Status",
            [None, *c.MACHINE_STATUSES],
            key="mach_status_filter",
            format_func=lambda s: "All statuses" if s is None else STATUS_FORMAT(s),
        )
        machines = svc.list_machines(conn, search or None, status)
        rows = [
            {
                "Machine ID": m["machine_code"],
                "Name": m["name"],
                "Type": m["machine_type"],
                "Recorded status": ui.status_text(m["status"], c.MACHINE_STATUS_LABELS),
                "Capacity": ui.quantity_text(m["capacity"], m["capacity_unit"]) if m["capacity"] else None,
                "Batches": m["batch_count"],
                "Notes": m["notes"],
            }
            for m in machines
        ]
        picked = ui.table(
            rows,
            key="mach_table",
            selectable=True,
            empty="No machines match the selected filters. Use 'Add machine' to register one.",
        )
        if picked is not None:
            machine = machines[picked]
            st.subheader(f"Machine {machine['machine_code']}")
            with st.expander("Edit machine details and status", expanded=True):
                machine_form(conn, f"machine_edit_{machine['id']}", machine)
            if machine["batch_count"]:
                st.info(
                    f"{machine['batch_count']} batch(es) reference this machine, so it cannot be deleted. "
                    "Set its status to Unavailable instead; historical batches keep their reference."
                )
            else:
                with st.expander("Delete this machine"):
                    st.warning("Permanent. Only possible because no batch uses this machine.")
                    confirm = st.checkbox("I understand this cannot be undone", key=f"del_ok_{machine['id']}")
                    if st.button("Delete Machine", disabled=not confirm, key=f"del_{machine['id']}"):
                        try:
                            svc.delete_machine(conn, machine["id"])
                            ui.flash("Machine deleted.")
                            st.rerun()
                        except TDIError as exc:
                            st.error(str(exc))
    with add_tab:
        machine_form(conn, "machine_add")


ui.run_page("Machines", "Maintain the catalogue of machines used for dyeing batches.", body)
