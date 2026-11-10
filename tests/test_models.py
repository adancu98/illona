"""Validate public MCP inputs before Illustrator can receive a mutation."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from illona_mcp.models import Color, Element, ObjectChange
from illona_mcp import server


def test_color_rejects_wrong_channels_ranges_nonfinite_and_extra_fields():
    invalid = [
        {"space": "rgb", "values": [1, 2, 3, 4]},
        {"space": "cmyk", "values": [0, 0, 0]},
        {"space": "rgb", "values": [256, 0, 0]},
        {"space": "cmyk", "values": [0, -1, 0, 0]},
        {"space": "rgb", "values": [0, float("nan"), 0]},
        {"space": "rgb", "values": [1, 2, 3], "script": "arbitrary"},
    ]
    for value in invalid:
        with pytest.raises(ValidationError):
            Color.model_validate(value)


def test_element_rejects_incomplete_or_unbounded_geometry_and_unknown_code():
    invalid = [
        {"type": "rect", "width": 10},
        {"type": "ellipse", "width": 10, "height": -1},
        {"type": "path", "points": [{"x": 1, "y": 2}]},
        {"type": "text"},
        {"type": "text", "text": "x", "size_pt": float("inf")},
        {"type": "text", "text": "x", "script": "app.quit()"},
    ]
    for value in invalid:
        with pytest.raises(ValidationError):
            Element.model_validate(value)


def test_drawing_payload_keeps_editable_unicode_and_flattens_stroke():
    element = Element.model_validate({
        "type": "text", "text": "Ilona — România 😊", "x": 12.5, "y": 9,
        "stroke": {"color": {"space": "cmyk", "values": [0, 80, 30, 5]}, "width_pt": 0.75},
    })
    payload = server.drawing_payload(element)
    assert payload["text"] == "Ilona — România 😊"
    assert payload["stroke"] == {"space": "cmyk", "values": [0, 80, 30, 5]}
    assert payload["stroke_width_pt"] == 0.75
    assert payload["x"] == 12.5


def test_explicit_null_paint_survives_update_payload():
    """Omitted paint preserves it; explicit null must remove an existing paint."""
    omitted = server.drawing_payload(ObjectChange(id="object-1", name="Renamed"))
    clear = server.drawing_payload(ObjectChange.model_validate({"id": "object-1", "fill": None, "stroke": None}))
    assert "fill" not in omitted and "stroke" not in omitted
    assert "fill" in clear and clear["fill"] is None
    assert "stroke" in clear and clear["stroke"] is None


def test_mcp_rejects_invalid_schema_before_dispatch_and_emits_no_stdout(monkeypatch, capsys):
    fake_call = AsyncMock(return_value={"created": [], "operation_id": "test"})
    monkeypatch.setattr(server.bridge, "call", fake_call)
    invalid = [
        ("illona_create_document", {"width": -10}),
        ("illona_create_elements", {"document_id": "doc1", "elements": [{"type": "rect", "width": 10, "height": -1}]}),
        ("illona_update_objects", {"document_id": "", "changes": [{"id": "x", "opacity": 101}]}),
        ("illona_export_document", {"document_id": "doc1", "filename": "x.pdf", "format": "exe"}),
    ]
    for name, arguments in invalid:
        with pytest.raises(Exception):
            asyncio.run(server.mcp.call_tool(name, arguments))
    fake_call.assert_not_called()
    asyncio.run(server.mcp.call_tool("illona_create_elements", {
        "document_id": "doc1", "operation_id": "fixed-id",
        "elements": [{"type": "path", "points": [{"x": 0, "y": 0}, {"x": 10, "y": 10, "left": {"x": 5, "y": 10}}]}],
    }))
    fake_call.assert_awaited_once()
    args = fake_call.await_args.args
    assert args[0] == "create_elements" and args[2] == "fixed-id"
    assert args[1]["elements"][0]["points"][1]["left"] == {"x": 5, "y": 10}
    assert capsys.readouterr().out == ""
