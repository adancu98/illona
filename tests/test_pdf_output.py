"""Verify print geometry and receipt recovery without running Illustrator."""

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, RectangleObject

from illona_mcp.bridge import IllonaBridge
from illona_mcp.pdf_output import finish_pdf

PT_PER_MM = 72 / 25.4


def native_pdf(path, width_mm=303, height_mm=216, text=None, origin=(0, 0)):
    writer = PdfWriter()
    page = writer.add_blank_page(width=width_mm * PT_PER_MM, height=height_mm * PT_PER_MM)
    x, y = origin
    page.mediabox = RectangleObject([x, y, x + width_mm * PT_PER_MM, y + height_mm * PT_PER_MM])
    page.artbox = RectangleObject(list(page.mediabox))
    if text:
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        })
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 20 20 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)
    writer.add_metadata({"/Title": "Illona print geometry proof"})
    with path.open("wb") as stream:
        writer.write(stream)


def finish(path):
    return finish_pdf(path, 297 * PT_PER_MM, 210 * PT_PER_MM, 3 * PT_PER_MM)


def test_expanded_media_becomes_real_trim_and_bleed_with_nonzero_origin(tmp_path):
    path = tmp_path / "brochure.pdf"
    native_pdf(path, origin=(11, 17))
    result = finish(path)
    page = PdfReader(path).pages[0]
    assert float(page.mediabox.width) / PT_PER_MM == pytest.approx(303, abs=0.001)
    assert float(page.mediabox.height) / PT_PER_MM == pytest.approx(216, abs=0.001)
    assert float(page.trimbox.width) / PT_PER_MM == pytest.approx(297, abs=0.001)
    assert float(page.trimbox.height) / PT_PER_MM == pytest.approx(210, abs=0.001)
    assert float(page.trimbox.left) == pytest.approx(11 + 3 * PT_PER_MM, abs=0.001)
    assert float(page.trimbox.bottom) == pytest.approx(17 + 3 * PT_PER_MM, abs=0.001)
    assert list(page.bleedbox) == list(page.mediabox)
    assert list(page.cropbox) == list(page.mediabox)
    assert "/ArtBox" not in page
    assert result["pdf_boxes_verified"] is True
    assert result["trim_mm"] == {"width": 297.0, "height": 210.0}
    assert result["media_mm"] == {"width": 303.0, "height": 216.0}
    assert result["bleed_mm"] == 3.0 and result["trim_marks"] is False


def test_finalization_preserves_live_text_and_document_metadata(tmp_path):
    path = tmp_path / "editable-text.pdf"
    native_pdf(path, text="Illona brochure proof")
    before = PdfReader(path)
    original_text = before.pages[0].extract_text()
    finish(path)
    after = PdfReader(path)
    assert after.pages[0].extract_text() == original_text == "Illona brochure proof"
    assert after.metadata.title == "Illona print geometry proof"
    assert "/Font" in after.pages[0]["/Resources"]


def test_wrong_native_media_preserves_original_bytes_and_creates_no_staging_file(tmp_path):
    path = tmp_path / "no-bleed.pdf"
    native_pdf(path, width_mm=297, height_mm=210)
    original = path.read_bytes()
    with pytest.raises(ValueError, match="expected expanded bleed area"):
        finish(path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".illona-pdf-*"))


def test_repeated_finalization_is_idempotent(tmp_path):
    path = tmp_path / "repeat.pdf"
    native_pdf(path, text="A stable print proof")
    first = finish(path)
    first_bytes = path.read_bytes()
    second = finish(path)
    assert first == second
    assert path.read_bytes() == first_bytes
    assert PdfReader(path).pages[0].extract_text() == "A stable print proof"


def test_finishing_receipt_replays_and_verifies_without_native_execution(tmp_path, monkeypatch):
    bridge = IllonaBridge(state_dir=tmp_path / "state", output_dir=tmp_path / "output")
    path = bridge.output_path("brochure.pdf", ".pdf")
    native_pdf(path, text="Receipt recovery")
    operation_id = "finish-once"
    operation = "export_document"
    params = {"document_id": "doc1", "path": str(path), "format": "pdf", "bleed_mm": 3}
    job = bridge._job(operation_id)
    job.mkdir(parents=True)
    digest = hashlib.sha256(json.dumps([operation, params], sort_keys=True, allow_nan=False).encode()).hexdigest()
    (job / "request.json").write_text(json.dumps({"operation": operation, "digest": digest, "status": "uncertain"}))
    (job / "result.json").write_text(json.dumps({"ok": True, "data": {
        "path": str(path), "format": "pdf", "requires_pdf_finalize": True,
        "trim_width_pt": 297 * PT_PER_MM, "trim_height_pt": 210 * PT_PER_MM, "bleed_pt": 3 * PT_PER_MM,
    }}))
    assert bridge.operation_status(operation_id)["status"] == "finishing"
    spawn = AsyncMock(side_effect=AssertionError("finishing a receipt must not repeat Illustrator execution"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    result = asyncio.run(bridge.call(operation, params, operation_id))
    assert result["pdf_boxes_verified"] is True
    assert result["replayed"] is True
    assert result["trim_mm"] == {"width": 297.0, "height": 210.0}
    assert "requires_pdf_finalize" not in result
    assert bridge.operation_status(operation_id)["status"] == "completed"
    again = asyncio.run(bridge.call(operation, params, operation_id))
    assert again == result
    assert PdfReader(path).pages[0].extract_text() == "Receipt recovery"
    spawn.assert_not_called()
