import streamlit as st

from api_client import (
    ApiError,
    get_document,
    get_document_content,
    get_document_history,
    list_documents,
)

st.set_page_config(page_title="Documents - Document Workflow Platform", layout="wide")
st.title("Documents")

col_filter, col_refresh = st.columns([4, 1])
with col_filter:
    status_filter = st.selectbox(
        "Filter by status", ["All", "UPLOADED", "PROCESSING", "COMPLETED", "FAILED"]
    )
with col_refresh:
    st.write("")  # vertical spacer to align the button with the selectbox
    if st.button("Refresh"):
        st.rerun()

try:
    documents = list_documents()
except ApiError as exc:
    st.error(f"Could not load documents: {exc}")
    st.stop()

if status_filter != "All":
    documents = [d for d in documents if d["status"] == status_filter]

if not documents:
    st.info("No documents found.")
    st.stop()

st.dataframe(
    [
        {
            "Filename": d["filename"],
            "Status": d["status"],
            "Size (bytes)": d["file_size"],
            "Uploaded": d["created_at"],
        }
        for d in documents
    ],
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Document detail")

search_query = st.text_input("Search by filename", "", placeholder="Type to filter the list below")
detail_documents = documents
if search_query:
    detail_documents = [
        d for d in documents if search_query.lower() in d["filename"].lower()
    ]

if not detail_documents:
    st.info("No documents match your search.")
else:
    options = {
        f"{d['filename']}  ·  {d['status']}  ·  {d['id']}": d["id"] for d in detail_documents
    }
    selected_label = st.selectbox("Select a document", list(options.keys()))
    selected_id = options[selected_label]

    try:
        document = get_document(selected_id)
        history = get_document_history(selected_id)
    except ApiError as exc:
        st.error(f"Could not load document detail: {exc}")
        st.stop()

    detail_col, metadata_col = st.columns(2)
    with detail_col:
        st.write("**Filename:**", document["filename"])
        st.write("**Status:**", document["status"])
        st.write("**Content type:**", document["content_type"])
        st.write("**Size:**", f"{document['file_size']} bytes")
        st.write("**Uploaded:**", document["created_at"])
        st.write("**Last updated:**", document["updated_at"])
    with metadata_col:
        st.write("**Extracted metadata**")
        st.json(document["extracted_metadata"] or {"info": "Not available yet"})

    st.write("**File**")
    # Cached per document in session state so the download button can show
    # immediately (no extra click) without re-fetching the file on every
    # unrelated rerun of this page — only the first time each document is
    # selected in this browser session. See LEARNING.md Phase 4 addendum.
    content_cache = st.session_state.setdefault("document_content_cache", {})
    if selected_id not in content_cache:
        try:
            content_cache[selected_id] = get_document_content(selected_id)
        except ApiError as exc:
            content_cache[selected_id] = exc

    cached = content_cache[selected_id]
    if isinstance(cached, ApiError):
        st.warning(f"Could not load file: {cached}")
    else:
        content, content_type = cached
        if content_type.startswith("text/"):
            st.text_area("Preview", content.decode("utf-8", errors="replace"), height=200)
        st.download_button(
            "Download / open file",
            data=content,
            file_name=document["filename"],
            mime=content_type,
        )

    st.write("**Processing history**")
    if history:
        for entry in history:
            from_status = entry["from_status"] or "—"
            st.markdown(
                f"- `{entry['created_at']}` — {from_status} → **{entry['to_status']}**: {entry['message']}"
            )
    else:
        st.caption("No processing history yet.")
