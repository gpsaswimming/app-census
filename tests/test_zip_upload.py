"""Zip-upload unwrapping (pure Python — no Node/swimparse needed).

Meet software usually exports a `.zip`; the ingest service unwraps it to the
inner `.sd3`/`.hy3`/`.txt` before parsing. These tests exercise that extraction
directly.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from ingest.service import IngestError, unwrap_upload


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_plain_file_passes_through():
    assert unwrap_upload(b"A0 sdif", "meet.sd3") == (b"A0 sdif", "meet.sd3")


def test_extracts_result_file_from_zip():
    data, name = unwrap_upload(_zip({"results.sd3": b"A0 sdif", "report.pdf": b"%PDF"}), "export.zip")
    assert (data, name) == (b"A0 sdif", "results.sd3")


def test_zip_detected_by_magic_even_when_misnamed():
    # A zip mislabeled with a .sd3 extension is still unwrapped (magic bytes win).
    data, name = unwrap_upload(_zip({"m.hy3": b"A1 hytek"}), "mislabeled.sd3")
    assert (data, name) == (b"A1 hytek", "m.hy3")


def test_prefers_sd3_then_hy3_then_txt():
    data, name = unwrap_upload(_zip({"b.txt": b"t", "a.hy3": b"h", "c.sd3": b"s"}), "x.zip")
    assert (data, name) == (b"s", "c.sd3")


def test_skips_macosx_and_directory_entries():
    z = _zip({"__MACOSX/._r.sd3": b"junk", "folder/": b"", "folder/real.sd3": b"A0"})
    data, name = unwrap_upload(z, "x.zip")
    assert (data, name) == (b"A0", "real.sd3")


def test_zip_without_result_file_is_rejected():
    with pytest.raises(IngestError, match="no .sd3"):
        unwrap_upload(_zip({"readme.pdf": b"%PDF"}), "x.zip")


def test_corrupt_zip_is_rejected():
    with pytest.raises(IngestError, match="not a valid zip"):
        unwrap_upload(b"PK\x03\x04 not really a zip", "x.zip")
