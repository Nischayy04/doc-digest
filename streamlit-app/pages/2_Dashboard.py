import altair as alt
import pandas as pd
import streamlit as st

from api_client import (
    ApiError,
    get_processing_stats_report,
    get_recent_activity_report,
    get_summary_report,
)

st.set_page_config(page_title="Dashboard - Document Workflow Platform", layout="wide")
st.title("Dashboard")

if st.button("Refresh"):
    st.rerun()

try:
    summary = get_summary_report()
    stats = get_processing_stats_report()
    recent = get_recent_activity_report(limit=10)
except ApiError as exc:
    st.error(f"Could not load reports: {exc}")
    st.stop()

st.subheader("Overview")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total documents", summary["total_documents"])
col2.metric("Uploaded", summary["counts_by_status"]["UPLOADED"])
col3.metric("Processing", summary["counts_by_status"]["PROCESSING"])
col4.metric("Completed", summary["counts_by_status"]["COMPLETED"])
col5.metric("Failed", summary["counts_by_status"]["FAILED"])

finished = stats["completed_count"] + stats["failed_count"]
avg_seconds = stats["average_processing_seconds"]
metric_col1, metric_col2 = st.columns(2)
metric_col1.metric(
    "Failure rate", f"{stats['failure_rate'] * 100:.1f}%" if finished else "No documents finished yet"
)
metric_col2.metric(
    "Average processing time", f"{avg_seconds:.2f}s" if avg_seconds is not None else "No documents finished yet"
)

st.subheader("Documents by status")

# Status colors: workflow states mapped to a fixed, mode-invariant status
# palette (UPLOADED is a neutral queued state, not a severity, so it uses a
# plain categorical blue rather than one of the good/warning/critical roles).
STATUS_COLORS = {
    "UPLOADED": "#2a78d6",
    "PROCESSING": "#fab219",
    "COMPLETED": "#0ca30c",
    "FAILED": "#d03b3b",
}
STATUS_ORDER = ["UPLOADED", "PROCESSING", "COMPLETED", "FAILED"]

counts_df = pd.DataFrame(
    {
        "status": STATUS_ORDER,
        "count": [summary["counts_by_status"][status] for status in STATUS_ORDER],
    }
)

chart = (
    alt.Chart(counts_df)
    .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
    .encode(
        x=alt.X("status:N", sort=STATUS_ORDER, title=None),
        y=alt.Y("count:Q", title="Documents"),
        color=alt.Color(
            "status:N",
            scale=alt.Scale(domain=STATUS_ORDER, range=[STATUS_COLORS[s] for s in STATUS_ORDER]),
            legend=None,
        ),
        tooltip=[alt.Tooltip("status:N", title="Status"), alt.Tooltip("count:Q", title="Documents")],
    )
    .properties(height=300)
)
st.altair_chart(chart, use_container_width=True)

st.subheader("Recent activity")
if recent["items"]:
    st.dataframe(
        [
            {"Filename": item["filename"], "Status": item["status"], "Updated": item["updated_at"]}
            for item in recent["items"]
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No activity yet.")
