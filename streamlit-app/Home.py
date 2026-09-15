import streamlit as st

from api_client import ApiError, DOCUMENT_SERVICE_URL, REPORTING_SERVICE_URL, upload_document

st.set_page_config(page_title="Doc Digest", layout="wide")

st.title("Doc Digest")
st.write(
    "Upload a document below. Once it's processed, use **Documents** in the sidebar "
    "to read its AI-generated summary and ask follow-up questions about it, or "
    "**Dashboard** for aggregate metrics."
)

st.subheader("Upload a document")
st.caption(
    "Accepted types: PDF and plain text (.txt). Processing (checks, metadata "
    "extraction, and an AI-generated summary) runs in the background after "
    "upload — check the Documents page a moment later to see the result."
)

uploaded_file = st.file_uploader("Choose a file", type=["pdf", "txt"])

if uploaded_file is not None and st.button("Upload", type="primary"):
    with st.spinner("Uploading..."):
        try:
            document = upload_document(
                filename=uploaded_file.name,
                content=uploaded_file.getvalue(),
                content_type=uploaded_file.type or "application/octet-stream",
            )
        except ApiError as exc:
            st.error(f"Upload failed: {exc}")
        else:
            st.success(f"Uploaded '{document['filename']}' — status: {document['status']}")
            st.json(document)
            st.info("Head to the **Documents** page to track its processing status.")

st.divider()
st.caption(f"document-service: {DOCUMENT_SERVICE_URL}")
st.caption(f"reporting-service: {REPORTING_SERVICE_URL}")
