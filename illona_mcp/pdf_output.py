"""Verify expanded native PDF geometry and set real trim/bleed boxes atomically."""

import os
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import RectangleObject


def finish_pdf(path: Path, trim_width_pt: float, trim_height_pt: float, bleed_pt: float) -> dict:
    expected = (float(trim_width_pt), float(trim_height_pt), float(bleed_pt))
    if not all(0 <= n < 20000 for n in expected) or not all(n > 0 for n in expected[:2]):
        raise ValueError("Invalid PDF trim/bleed geometry")
    width, height, bleed = expected
    reader = PdfReader(path)
    if reader.is_encrypted or len(reader.pages) != 1:
        raise ValueError("PDF finalization requires one unencrypted native-exported page")
    page = reader.pages[0]
    media = page.mediabox
    if page.rotation % 360 or abs(float(media.width) - width - 2 * bleed) > 0.15 or abs(float(media.height) - height - 2 * bleed) > 0.15:
        raise ValueError("Illustrator did not export the expected expanded bleed area; original PDF was preserved")
    x0, y0, x1, y1 = [float(v) for v in media]
    trim = [x0 + bleed, y0 + bleed, x1 - bleed, y1 - bleed]
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    out = writer.pages[0]
    out.cropbox = RectangleObject([x0, y0, x1, y1])
    out.bleedbox = RectangleObject([x0, y0, x1, y1])
    out.trimbox = RectangleObject(trim)
    # TrimBox describes the finished page. Keeping a separate ArtBox as well
    # conflicts with PDF/X page-box rules, so remove any native ArtBox.
    out.pop("/ArtBox", None)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".illona-pdf-", suffix=".pdf", delete=False) as stream:
            staged = Path(stream.name)
            writer.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        check = PdfReader(staged).pages[0]
        if abs(float(check.trimbox.width) - width) > 0.15 or abs(float(check.trimbox.height) - height) > 0.15:
            raise ValueError("PDF trim box verification failed; native PDF was preserved")
        if abs(float(check.bleedbox.width) - width - 2 * bleed) > 0.15:
            raise ValueError("PDF bleed box verification failed; native PDF was preserved")
        os.replace(staged, path)
        staged = None
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    to_mm = lambda n: round(n * 25.4 / 72, 4)
    return {"bytes": path.stat().st_size, "pdf_boxes_verified": True,
            "trim_mm": {"width": to_mm(width), "height": to_mm(height)},
            "media_mm": {"width": to_mm(x1 - x0), "height": to_mm(y1 - y0)},
            "bleed_mm": to_mm(bleed), "trim_marks": False}

