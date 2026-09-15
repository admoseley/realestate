"""Validation for uploaded PDFs (sheriff-sale analysis and the debug report)."""
from fastapi import HTTPException, UploadFile

# Static Web Apps rejects request bodies over 30 MB at the edge, with an error
# the frontend can't explain, so the API's own limit sits below that. By the
# time this runs the server has already received the body, so this is a
# validation limit, not memory protection; the edge limit covers that.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

_CHUNK_BYTES = 1024 * 1024

# The PDF specification allows the "%PDF-" header anywhere in the first 1024
# bytes, and some producers do put bytes before it.
_PDF_SIGNATURE = b"%PDF-"
_SIGNATURE_WINDOW = 1024


async def read_pdf_upload(file: UploadFile) -> bytes:
    """Read an uploaded PDF, rejecting anything that isn't one or is too large.

    The name check alone used to be the only guard: any file named ``.pdf``
    went straight to ``pdftotext``.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Uploaded file must be a PDF.")

    limit = MAX_UPLOAD_BYTES
    chunks, size = [], 0
    while chunk := await file.read(_CHUNK_BYTES):
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"PDF is larger than the {limit // (1024 * 1024)} MB upload limit.")
        chunks.append(chunk)
    content = b"".join(chunks)

    if _PDF_SIGNATURE not in content[:_SIGNATURE_WINDOW]:
        raise HTTPException(400, "Uploaded file is not a valid PDF.")
    return content
