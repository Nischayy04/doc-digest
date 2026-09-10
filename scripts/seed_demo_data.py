#!/usr/bin/env python3
"""Uploads a handful of sample documents to a running document-service, so a
fresh checkout has something to look at immediately instead of starting
empty. Deliberately dependency-free (standard library only) — no venv setup
needed, just `python scripts/seed_demo_data.py` with the stack already up.

Includes documents that succeed (a couple of .txt files, a minimal valid
PDF) and documents that deliberately fail (a disallowed extension, an empty
file) — so a fresh run demonstrates both branches of the processing
workflow, not just the happy path.
"""

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid


def build_minimal_pdf_bytes() -> bytes:
    """The smallest valid single-page PDF, byte-accurate xref offsets so
    pypdf parses it with no recovery warnings. Same construction as
    document-service/tests/pdf_fixture.py — kept as a duplicate here since
    this script intentionally has zero dependencies on any service's code."""
    header = b"%PDF-1.4\n"
    obj1 = b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    obj2 = b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    obj3 = b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"

    offset1 = len(header)
    offset2 = offset1 + len(obj1)
    offset3 = offset2 + len(obj2)
    xref_offset = offset3 + len(obj3)

    body = header + obj1 + obj2 + obj3
    xref = (
        b"xref\n0 4\n0000000000 65535 f \n"
        + f"{offset1:010} 00000 n \n".encode()
        + f"{offset2:010} 00000 n \n".encode()
        + f"{offset3:010} 00000 n \n".encode()
    )
    trailer = b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n" + str(xref_offset).encode() + b"\n%%EOF"
    return body + xref + trailer


SAMPLE_DOCUMENTS = [
    ("meeting-notes.txt", b"Discussed the roadmap, assigned owners, agreed on next steps.", "text/plain"),
    ("readme-draft.txt", b"This project processes uploaded documents automatically.", "text/plain"),
    ("sample-report.pdf", build_minimal_pdf_bytes(), "application/pdf"),
    ("spreadsheet.xlsx", b"not actually an excel file", "application/octet-stream"),  # disallowed extension -> FAILED
    ("empty.txt", b"", "text/plain"),  # empty -> FAILED
]


def upload(base_url: str, filename: str, content: bytes, content_type: str) -> dict:
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

    request = urllib.request.Request(
        f"{base_url}/api/v1/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def get_document(base_url: str, document_id: str) -> dict:
    with urllib.request.urlopen(f"{base_url}/api/v1/documents/{document_id}", timeout=10) as response:
        return json.loads(response.read())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--document-service-url",
        default="http://localhost:8001",
        help="Base URL of document-service (default: http://localhost:8001)",
    )
    args = parser.parse_args()
    base_url = args.document_service_url.rstrip("/")

    try:
        urllib.request.urlopen(f"{base_url}/health", timeout=5)
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Could not reach document-service at {base_url} ({exc}). "
            "Is the stack running (docker compose up)?"
        )

    uploaded = []
    for filename, content, content_type in SAMPLE_DOCUMENTS:
        document = upload(base_url, filename, content, content_type)
        uploaded.append(document)
        print(f"Uploaded {filename} (id={document['id']})")

    print("\nWaiting for background processing...")
    time.sleep(2)

    print(f"\n{'Filename':<20} {'Status':<12} Metadata")
    print("-" * 60)
    for document in uploaded:
        final = get_document(base_url, document["id"])
        metadata = final["extracted_metadata"] or "-"
        print(f"{final['filename']:<20} {final['status']:<12} {metadata}")


if __name__ == "__main__":
    main()
