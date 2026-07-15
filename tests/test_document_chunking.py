import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "azure_functions" / "document_processor"))

from chunking import chunk_text, parse_blob_path  # noqa: E402


def test_chunk_text_empty_returns_no_chunks():
    assert chunk_text("") == []


def test_chunk_text_shorter_than_chunk_size_returns_one_chunk():
    assert chunk_text("hello world", chunk_size=1000, overlap=150) == ["hello world"]


def test_chunk_text_splits_with_overlap():
    text = "a" * 25
    chunks = chunk_text(text, chunk_size=10, overlap=3)

    assert chunks[0] == "a" * 10
    # Each subsequent chunk starts overlap characters before the previous one ended.
    assert len(chunks) > 1
    assert all(len(c) <= 10 for c in chunks)
    # Reassembling with the known overlap recovers the original length coverage.
    assert "".join(chunks)[:10] == text[:10]


def test_chunk_text_covers_the_whole_text():
    text = "The quick brown fox jumps over the lazy dog. " * 50
    chunks = chunk_text(text, chunk_size=100, overlap=20)

    # Every character position ends up in at least one chunk.
    covered = set()
    pos = 0
    start = 0
    for chunk in chunks:
        covered.update(range(start, start + len(chunk)))
        start += 100 - 20
    assert max(covered) >= len(text) - 1


def test_parse_blob_path_extracts_user_oid_document_id_and_filename():
    document_id = str(uuid.uuid4())
    blob_path = f"some-user-oid/{document_id}-invoice.pdf"

    user_oid, parsed_id, filename = parse_blob_path(blob_path)

    assert user_oid == "some-user-oid"
    assert parsed_id == document_id
    assert filename == "invoice.pdf"


def test_parse_blob_path_rejects_malformed_id():
    with pytest.raises(ValueError):
        parse_blob_path("user-oid/not-a-real-uuid-filename.pdf")
