def build_minimal_pdf_bytes() -> bytes:
    """Builds the smallest valid single-page PDF byte-for-byte (correct xref
    offsets, so pypdf parses it cleanly with no recovery warnings) — good
    enough to exercise the page-count extractor without a real PDF file or
    a PDF-writing library as a test dependency."""
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
