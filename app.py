"""Textile Dyeing Intelligence - application entry point (``streamlit run app.py``)."""

import bootstrap  # noqa: F401  # isort: skip

import streamlit as st

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence import ui
from textile_dyeing_intelligence.config import APP_NAME, UNAVAILABLE_LABEL
from textile_dyeing_intelligence.decimals import format_decimal
from textile_dyeing_intelligence.errors import ValidationFailure
from textile_dyeing_intelligence.filters import ReportFilters
from textile_dyeing_intelligence.reporting.dashboard import build_dashboard
from textile_dyeing_intelligence.services import machines as machines_service

st.set_page_config(page_title=APP_NAME, layout="wide")


def _percent(value) -> str:
    return UNAVAILABLE_LABEL if value is None else f"{format_decimal(value, 1)} %"


def dashboard_body(conn) -> None:
    st.subheader("Reporting period and filters")
    cols = st.columns(4)
    start = cols[0].date_input("From (batch reporting date)", value=None, key="dash_from")
    end = cols[1].date_input("To (batch reporting date)", value=None, key="dash_to")
    machines = {m["id"]: f"{m['machine_code']} - {m['name']}" for m in machines_service.list_machines(conn)}
    machine_id = cols[2].selectbox(
        "Machine",
        [None, *machines],
        format_func=lambda i: "All machines" if i is None else machines[i],
        key="dash_machine",
    )
    status = cols[3].selectbox(
        "Production status",
        [None, *c.BATCH_STATUSES],
        format_func=lambda s: "All statuses" if s is None else c.BATCH_STATUS_LABELS[s],
        key="dash_status",
    )
    try:
        filters = ReportFilters(ui.date_str(start), ui.date_str(end), machine_id=machine_id, status=status).validated()
        data = build_dashboard(conn, filters)
    except ValidationFailure as exc:
        st.error(" ".join(exc.errors.values()))
        return

    if data.is_empty:
        st.info(
            "No batches match the selected filters. Create a batch on the Batches page to get started. "
            "Indicators are calculated only from recorded data; none are shown for an empty database."
        )
        if st.button("Go to Batches"):
            ui.go_to("pages/1_Batches.py")
        return

    m = data.metrics
    st.caption(
        "Reporting date of a batch = actual start date, else planned date, else creation date. "
        "Rates exclude cancelled batches and count each batch once."
    )
    top = st.columns(5)
    top[0].metric("Batches in period", m.total_batches)
    for col, status_key in zip(top[1:], c.BATCH_STATUSES, strict=True):
        col.metric(c.BATCH_STATUS_LABELS[status_key], m.status_counts[status_key])

    st.subheader("Quality and rework")
    q = st.columns(4)
    q[0].metric(
        "Completed batches awaiting a quality outcome",
        m.awaiting_quality_outcome,
        help="Completed batches with no passed/failed inspection (none recorded or only pending).",
    )
    q[1].metric("Batches with at least one failed inspection", m.batches_with_failed_inspection)
    q[2].metric(
        "Batch failure rate (final outcome)",
        _percent(m.failure_rate),
        help=f"{m.batches_final_failed} failed of {m.batches_with_final_outcome} batches with a final outcome.",
    )
    q[3].metric(
        "Batch rework rate",
        _percent(m.rework_rate),
        help=f"{m.batches_with_rework} batches with rework of {m.rate_population} eligible batches.",
    )
    st.caption(
        f"Rework events (excluding cancelled): {m.rework_events}. "
        f"Batches with unresolved rework: {m.batches_with_open_rework}. "
        "Rework events and batches needing rework are different measures."
    )

    st.subheader("Chemical consumption comparisons")
    k = st.columns(3)
    k[0].metric("Compared (planned vs actual)", data.comparable)
    k[1].metric("Incomplete data", data.incomplete)
    k[2].metric("Not comparable (units or basis)", data.incompatible)
    if not data.comparisons:
        st.info("No consumption records for the selected batches.")

    st.subheader("Recent batches")
    rows = [
        {
            "Batch ID": b["batch_code"],
            "Production status": ui.status_text(b["status"], c.BATCH_STATUS_LABELS),
            "Quantity": ui.quantity_text(b["quantity"], b["quantity_unit"]),
            "Machine": b["machine_code"],
            "Recipe": b["recipe_code"],
            "Quality": b["quality_label"],
            "Rework events": b["rework_events"],
        }
        for b in data.recent_batches
    ]
    picked = ui.table(rows, key="dash_recent", selectable=True)
    if picked is not None:
        st.session_state["open_batch_id"] = data.recent_batches[picked]["id"]
        ui.go_to("pages/1_Batches.py")
    st.caption("Select a row to open the batch.")


def dashboard() -> None:
    ui.run_page("Dashboard", "Operational overview calculated from stored records.", dashboard_body)


pages = [
    st.Page(dashboard, title="Dashboard", url_path="dashboard", default=True),
    st.Page("pages/1_Batches.py", title="Batches"),
    st.Page("pages/2_Recipes.py", title="Recipes"),
    st.Page("pages/3_Machines.py", title="Machines"),
    st.Page("pages/4_Process_Records.py", title="Process Records"),
    st.Page("pages/5_Chemical_Consumption.py", title="Chemical Consumption"),
    st.Page("pages/6_Quality_Inspections.py", title="Quality Inspections"),
    st.Page("pages/7_Rework.py", title="Rework"),
    st.Page("pages/8_Reports.py", title="Reports"),
]
st.sidebar.markdown(f"**{APP_NAME}**")
st.sidebar.caption("Local record management. Not a machine-control or process-validation system.")
st.navigation(pages).run()
