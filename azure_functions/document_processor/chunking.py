"""Pure logic with zero Azure dependencies — kept separate from
function_app.py so it's trivially unit-testable without the Azure
Functions runtime or any Azure SDK installed."""

import uuid

_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 150


def chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Fixed-size character chunking with overlap."""
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def parse_blob_path(blob_path: str) -> tuple[str, str, str]:
    """blob_path looks like '{user_oid}/{document_id}-{filename}', written
    by UploadDocumentUseCase. document_id is a UUID string, which itself
    contains hyphens, so this can't just split on the first '-' — it slices
    the fixed 36-character UUID instead."""
    user_oid, rest = blob_path.split("/", 1)
    document_id = rest[:36]
    uuid.UUID(document_id)  # raises ValueError if this wasn't actually a UUID
    filename = rest[37:]
    return user_oid, document_id, filename
