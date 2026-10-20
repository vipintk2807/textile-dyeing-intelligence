"""Reports: filtered operational summaries with CSV export."""

import bootstrap  # noqa: F401  # isort: skip

import streamlit as st

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence import ui
from textile_dyeing_intelligence.config import UNAVAILABLE_LABEL
from textile_dyeing_intelligence.decimals import format_decimal
from textile_dyeing_intelligence.errors import ValidationFailure
from textile_dyeing_intelligence.filters import ReportFilters
from textile_dyeing_intelligence.reporting.export import export_filename, rows_to_csv
from textile_dyeing_intelligence.reporting.metrics import batch_metrics
from textile_dyeing_intelligence.reporting.reports import REPORT_BUILDERS
from textile_dyeing_intelligence.services import machines as machines_service
from textile_dyeing_intelligence.services import recipes as recipes_service

REPORTS = {
    "batch_production": "Batch production",
    "consumption_comparison": "Chemical consumption - planned vs actual",
    "consumption_records": "Chemical consumption - records",
    "quality": "Quality inspections",
    "rework": "Rework",
    "machine_activity": "Machine activity",
}
RELEVANT = {  # which optional filters apply to which report
    "batch_production": {"search", "machine", "recipe", "status"},
    "consumption_comparison": {"search", "machine", "recipe", "status", "material"},
    "consumption_records": {"search", "machine", "recipe", "status", "material"},
    "quality": {"search", "machine", "recipe", "status", "outcome"},
    "rework": {"search", "machine", "recipe", "status", "rework_status"},
    "machine_activity": {"search", "machine", "recipe", "status"},
}


def _pct(value) -> str:
    return UNAVAILABLE_LABEL if value is None else f"{format_decimal(value, 1)} %"


def body(conn) -> None:
    key = st.selectbox("Report", list(REPORTS), format_func=REPORTS.get, key="rep_kind")
    use = RELEVANT[key]
    st.caption("Filters apply to the table, the summary figures and the CSV export alike.")
    c1 = st.columns(4)
    start = c1[0].date_input("From date", value=None, key="rep_from")
    end = c1[1].date_input("To date", value=None, key="rep_to")
    search = c1[2].text_input("Batch ID or work order contains", key="rep_search") if "search" in use else ""
    status = (
        c1[3].selectbox(
            "Production status",
            [None, *c.BATCH_STATUSES],
            key="rep_status",
            format_func=lambda s: "All statuses" if s is None else c.BATCH_STATUS_LABELS[s],
        )
        if "status" in use
        else None
    )
    c2 = st.columns(4)
    machines = {m["id"]: m["machine_code"] for m in machines_service.list_machines(conn)}
    machine = (
        c2[0].selectbox(
            "Machine",
            [None, *machines],
            key="rep_machine",
            format_func=lambda i: "All machines" if i is None else machines[i],
        )
        if "machine" in use
        else None
    )
    recipes = {r["id"]: r["recipe_code"] for r in recipes_service.list_recipes(conn)}
    recipe = (
        c2[1].selectbox(
            "Recipe",
            [None, *recipes],
            key="rep_recipe",
            format_func=lambda i: "All recipes" if i is None else recipes[i],
        )
        if "recipe" in use
        else None
    )
    material = c2[2].text_input("Chemical / material contains", key="rep_material") if "material" in use else ""
    outcome = (
        c2[2].selectbox(
            "Inspection outcome",
            [None, *c.QUALITY_DISPOSITIONS],
            key="rep_outcome",
            format_func=lambda x: "All outcomes" if x is None else c.QUALITY_DISPOSITION_LABELS[x],
        )
        if "outcome" in use
        else None
    )
    rstatus = (
        c2[2].selectbox(
            "Rework status",
            [None, *c.REWORK_STATUSES],
            key="rep_rstatus",
            format_func=lambda x: "All" if x is None else c.REWORK_STATUS_LABELS[x],
        )
        if "rework_status" in use
        else None
    )

    try:
        filters = ReportFilters(
            ui.date_str(start),
            ui.date_str(end),
            search=search,
            machine_id=machine,
            recipe_id=recipe,
            status=status,
            inspection_outcome=outcome,
            rework_status=rstatus,
            material=material,
        ).validated()
        report = REPORT_BUILDERS[key](conn, filters)
    except ValidationFailure as exc:
        st.error(" ".join(exc.errors.values()) + " Correct the filters to see this report.")
        return

    st.subheader(report.title)
    active = filters.describe()
    st.caption(
        f"Date filter applies to: {report.date_basis}. "
        + (f"**Filtered subset** ({'; '.join(active)})." if active else "No filters active: all records.")
    )
    for note in report.notes:
        st.caption(note)

    if key == "quality":
        s = report.summary
        k = st.columns(4)
        k[0].metric("Inspections in scope", s["inspections"])
        k[1].metric(
            "Passed / Failed / Pending",
            " / ".join(str(s["by_disposition"][d]) for d in ("passed", "failed", "pending")),
        )
        k[2].metric("Batches with a final outcome", s["batches_with_final_outcome"])
        k[3].metric(
            "Batch failure rate (final outcome)",
            UNAVAILABLE_LABEL if s["outcome_filter_active"] else _pct(s["failure_rate"]),
        )
        if s["outcome_filter_active"]:
            st.caption("The batch failure rate is not shown while an inspection-outcome filter is active.")
    elif key == "rework":
        s = report.summary
        k = st.columns(3)
        k[0].metric("Rework events (excluding cancelled)", s["events_excluding_cancelled"])
        k[1].metric("Distinct batches with rework", s["distinct_batches"])
        k[2].metric("All events including cancelled", s["events"])
        m = batch_metrics(conn, filters)
        st.caption(
            f"Batch rework rate for the same filters (batch reporting date basis): {_pct(m.rework_rate)} "
            f"({m.batches_with_rework} of {m.rate_population} eligible batches)."
        )

    ui.table(
        report.rows,
        report.columns,
        key=f"rep_table_{key}",
        empty="No records match the selected filters. Adjust or clear the filters.",
    )
    if report.rows:
        st.download_button(
            "Download this report (CSV)",
            rows_to_csv(report.columns, report.rows),
            file_name=export_filename(key, filters.start_date, filters.end_date),
            mime="text/csv",
            key=f"rep_dl_{key}",
        )
        st.caption("The CSV contains exactly the rows shown above. It is a report extract, not a database backup.")


ui.run_page("Reports", "Filter and review operational reports, and export them as CSV.", body)
