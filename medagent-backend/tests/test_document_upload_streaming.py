"""Streaming upload regression tests for unlimited-size PDF ingestion."""

import asyncio
import hashlib

import pytest
from fastapi import HTTPException

from app.api.v1.documents import UPLOAD_CHUNK_SIZE, _stream_upload_to_disk


class ChunkedUpload:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.requested_sizes = []

    async def read(self, size=-1):
        self.requested_sizes.append(size)
        return self.chunks.pop(0) if self.chunks else b""


def test_pdf_stream_has_no_application_size_limit(tmp_path):
    chunks = [b"%PDF-1.7\n", b"a" * 12, b"%%EOF"]
    upload = ChunkedUpload(chunks)
    target = tmp_path / "large.pdf"

    size, digest = asyncio.run(
        _stream_upload_to_disk(upload, str(target), max_bytes=None)
    )

    expected = b"%PDF-1.7\n" + b"a" * 12 + b"%%EOF"
    assert target.read_bytes() == expected
    assert size == len(expected)
    assert digest == hashlib.sha256(expected).hexdigest()
    assert set(upload.requested_sizes) == {UPLOAD_CHUNK_SIZE}
    assert not (tmp_path / "large.pdf.part").exists()


def test_non_pdf_limit_removes_partial_upload(tmp_path):
    upload = ChunkedUpload([b"1234", b"5678"])
    target = tmp_path / "large.txt"

    with pytest.raises(HTTPException, match="File too large"):
        asyncio.run(_stream_upload_to_disk(upload, str(target), max_bytes=5))

    assert not target.exists()
    assert not (tmp_path / "large.txt.part").exists()
