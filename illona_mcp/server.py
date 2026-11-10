"""Illona's bounded design tools, served through the official MCP SDK over stdio."""

import json
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations
from pydantic import Field

from . import __version__
from .bridge import IllonaBridge
from .models import Element, ObjectChange, Palette, Panel

bridge = IllonaBridge()
mcp = FastMCP(
    "Illona",
    instructions="""Illona creates editable vector illustrations and brochure layouts in stable Adobe Illustrator on macOS.
Start with illona_status and use explicit document IDs; never infer the target from the active window.
Coordinates are top-left relative to the requested zero-based artboard, in millimetres unless stated otherwise.
All 66 advanced illona_pro_ tools use POINTS for geometry and preserve native UUIDs. Their point-text Y is the baseline.
Use target_artboard to temporarily select an advanced tool's board, and explicit document_id for document-specific tools.
Create workflows always create new documents. Existing project modifications require explicit user intent.
Inspect before editing and request a preview after each meaningful design stage. Verify actual geometry and visual quality.
For complex illustration, logo or brochure work, consult illona://learning-playbook for native drawing procedures and visual review criteria.
Supply a stable operation_id for mutations. After timeout, inspect operation status; never blindly repeat a mutation.
Use installed PostScript font names. Preserve editable text. Full-content replacement may reset mixed styles.
Brochure fitting and preflight are advisory, not certified print validation. Follow the printer's bleed/profile specifications.
Exports are confined to the configured output folder. Native save changes the document's path; export-copy preserves it.
The bridge is local; document details and previews returned to Codex are available to its AI model.
""",
    log_level="WARNING",
)

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CREATE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
EDIT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)

DocId = Annotated[str, Field(min_length=1, max_length=200)]
OperationId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")]
Dimension = Annotated[float, Field(gt=0, le=5000, allow_inf_nan=False)]
BoardIndex = Annotated[int, Field(ge=0, le=999)]
Units = Literal["mm", "pt"]


def drawing_payload(model: Element | ObjectChange) -> dict:
    data = model.model_dump(exclude_none=True)
    if data.get("type") == "image":
        data["path"] = str(bridge.asset_path(data["path"]))
    if isinstance(model, ObjectChange):
        for paint in ("fill", "stroke"):
            if paint in model.model_fields_set and getattr(model, paint) is None:
                data[paint] = None
    if "stroke" in data and data["stroke"] is not None:
        stroke = data["stroke"]
        data["stroke"] = stroke["color"]
        data["stroke_width_pt"] = stroke["width_pt"]
    return data


@mcp.tool(annotations=READ)
async def illona_status() -> dict:
    """Connect to Illustrator and list open documents with session IDs. Does not modify artwork."""
    result = await bridge.call("status", {})
    return {**result, "illona_version": __version__, "output_directory": str(bridge.output_dir)}


@mcp.tool(annotations=READ)
async def illona_inspect_document(document_id: DocId, limit: Annotated[int, Field(ge=1, le=500)] = 200) -> dict:
    """Read artboards, layers and bounded object details. Bounds are in Illustrator document points."""
    return await bridge.call("inspect_document", {"document_id": document_id, "limit": limit})


@mcp.tool(annotations=READ)
async def illona_inspect_selection(document_id: DocId) -> dict:
    """Read the explicit document's current selection without switching documents."""
    return await bridge.call("inspect_selection", {"document_id": document_id})


@mcp.tool(annotations=READ)
async def illona_list_fonts(limit: Annotated[int, Field(ge=1, le=1000)] = 200) -> dict:
    """List installed Illustrator font PostScript names for editable typography."""
    return await bridge.call("list_fonts", {"limit": limit})


@mcp.tool(annotations=CREATE)
async def illona_create_document(
    width: Dimension = 210, height: Dimension = 297, name: str = "Illona — Untitled",
    color_mode: Literal["RGB", "CMYK"] = "RGB", units: Units = "mm",
    operation_id: OperationId | None = None,
    artboard_count: Annotated[int, Field(ge=1, le=20)] = 1,
) -> dict:
    """Create a new blank editable document. Existing documents remain open."""
    p = dict(width=width, height=height, name=name, color_mode=color_mode, units=units)
    if artboard_count != 1:
        p["artboard_count"] = artboard_count
    return await bridge.call("create_document", p, operation_id)


@mcp.tool(annotations=CREATE)
async def illona_create_elements(
    document_id: DocId, elements: Annotated[list[Element], Field(min_length=1, max_length=500)],
    layer_name: Annotated[str, Field(min_length=1, max_length=200)] = "Illona",
    units: Units = "mm", artboard_index: BoardIndex = 0, operation_id: OperationId | None = None,
) -> dict:
    """Draw editable rectangles, ellipses, Bézier paths, live text and official image assets in a validated batch.

    Path points accept left/right control handles and smooth flags. Stroke width and text size are always points.
    Text x/y refers to the top-left geometric frame. Set both width and height for area text; omit both for point text.
    Images require width/height and a PNG/JPEG path inside the configured output folder; fit is contain or cover.
    """
    return await bridge.call("create_elements", dict(document_id=document_id, elements=[drawing_payload(e) for e in elements],
        layer_name=layer_name, units=units, artboard_index=artboard_index), operation_id)


@mcp.tool(annotations=EDIT)
async def illona_update_objects(
    document_id: DocId, changes: Annotated[list[ObjectChange], Field(min_length=1, max_length=500)],
    units: Units = "mm", artboard_index: BoardIndex = 0, operation_id: OperationId | None = None,
) -> dict:
    """Update explicit object UUIDs: position, size, paint, text, name or typography.

    Inspect before changing. Replacing all text may reset mixed character formatting. Whole-batch atomic rollback is not guaranteed.
    """
    return await bridge.call("update_objects", dict(document_id=document_id, changes=[drawing_payload(c) for c in changes],
        units=units, artboard_index=artboard_index), operation_id)


@mcp.tool(annotations=READ)
async def illona_plan_brochure(
    format: Literal["trifold", "bifold"] = "trifold", width_mm: Dimension = 297, height_mm: Dimension = 210,
    margin_mm: Annotated[float, Field(ge=1, le=30)] = 6,
    bleed_mm: Annotated[float, Field(ge=0, le=20)] = 3,
    fold_compensation_mm: Annotated[float, Field(ge=0, le=10)] = 2,
) -> dict:
    """Calculate brochure panels, fold positions, safe margins and bleed before creating artwork.

    Trifold is a roll fold with a narrower inner flap; confirm the fold and dimensions with the printer.
    """
    return await bridge.call("plan_brochure", dict(format=format, width_mm=width_mm, height_mm=height_mm,
        margin_mm=margin_mm, bleed_mm=bleed_mm, fold_compensation_mm=fold_compensation_mm))


@mcp.tool(annotations=CREATE)
async def illona_create_brochure(
    panels: Annotated[list[Panel], Field(min_length=1, max_length=6)],
    name: str = "Illona — Brochure", title: str = "Ideas take shape",
    format: Literal["trifold", "bifold"] = "trifold", width_mm: Dimension = 297, height_mm: Dimension = 210,
    margin_mm: Annotated[float, Field(ge=1, le=30)] = 6,
    bleed_mm: Annotated[float, Field(ge=0, le=20)] = 3,
    fold_compensation_mm: Annotated[float, Field(ge=0, le=10)] = 2,
    palette: Palette | None = None, font: str | None = None, heading_font: str | None = None,
    operation_id: OperationId | None = None,
) -> dict:
    """Create a new editable two-sided brochure with layers, area text, fold and safe-area guides.

    Trifold panel content order: outside flap/back/front; inside left/middle/right.
    Bifold content order: outside back/front; inside left/right. Fit warnings are estimates, not an overset guarantee.
    """
    p = dict(panels=[panel.model_dump() for panel in panels], name=name, title=title, format=format,
        width_mm=width_mm, height_mm=height_mm, margin_mm=margin_mm, bleed_mm=bleed_mm,
        fold_compensation_mm=fold_compensation_mm, palette=(palette or Palette()).model_dump())
    if font: p["font"] = font
    if heading_font: p["heading_font"] = heading_font
    return await bridge.call("create_brochure", p, operation_id)


@mcp.tool(annotations=CREATE)
async def illona_create_illustration(
    name: str = "Illona — Botanical landscape", title: str = "A quieter kind of growth",
    width_mm: Dimension = 210, height_mm: Dimension = 260, palette: Palette | None = None,
    operation_id: OperationId | None = None,
) -> dict:
    """Create a new layered editable botanical landscape as a design starting point.

    This is a deterministic vector composition, not a general image-generation model. Refine paths using create_elements and update_objects.
    """
    return await bridge.call("create_illustration", dict(name=name, title=title, width_mm=width_mm, height_mm=height_mm,
        palette=(palette or Palette()).model_dump()), operation_id)


@mcp.tool(annotations=CREATE)
async def illona_create_icon_set(
    name: str = "Illona — Icon collection", title: str = "Small things, thoughtfully made",
    labels: Annotated[list[str], Field(min_length=1, max_length=6)] | None = None,
    width_mm: Dimension = 210, height_mm: Dimension = 180, palette: Palette | None = None,
    operation_id: OperationId | None = None,
) -> dict:
    """Create a new coordinated collection of six editable vector icons with live text labels."""
    p = dict(name=name, title=title, width_mm=width_mm, height_mm=height_mm, palette=(palette or Palette()).model_dump())
    if labels: p["labels"] = labels
    return await bridge.call("create_icon_set", p, operation_id)


@mcp.tool(annotations=READ)
async def illona_preflight_document(
    document_id: DocId, min_effective_ppi: Annotated[float, Field(ge=1, le=2400)] = 250,
) -> dict:
    """Inspect artwork for supported production issues and report unverified checks explicitly.

    Advisory checks do not certify PDF/X compliance, exact text overflow, color accuracy or printer acceptance.
    """
    return await bridge.call("preflight_document", dict(document_id=document_id, min_effective_ppi=min_effective_ppi))


@mcp.tool(annotations=CREATE, structured_output=False)
async def illona_preview_document(
    document_id: DocId, artboard_index: BoardIndex = 0,
    width_px: Annotated[int, Field(ge=200, le=3000)] = 1400,
) -> list:
    """Render the requested artboard to a PNG and return its image for visual review."""
    import uuid
    path = bridge.output_path(f"previews/{uuid.uuid4().hex}.png", ".png")
    result = await bridge.call("preview_document", dict(document_id=document_id, artboard_index=artboard_index,
        width_px=width_px, path=str(path)))
    return [json.dumps(result, ensure_ascii=False), Image(path=str(path))]


@mcp.tool(annotations=CREATE)
async def illona_export_document(
    document_id: DocId, filename: str, format: Literal["png", "svg", "pdf", "ai"],
    artboard_index: BoardIndex = 0, overwrite: bool = False,
    pdf_preset: str | None = None, bleed_mm: Annotated[float, Field(ge=0, le=20)] = 3,
    operation_id: OperationId | None = None,
) -> dict:
    """Export a copy of one artboard inside Illona's output directory, without changing the source path.

    PNG renders the board; vector/PDF copies may omit document-level metadata or unsupported features. Inspect returned warnings.
    Existing files are protected unless overwrite is explicitly true. PDF preset must exist in Illustrator.
    PDF output verifies trim/bleed boxes, includes physical bleed, and omits crop marks and Illustrator-specific editability.
    """
    path = bridge.output_path(filename, "." + format)
    p = dict(document_id=document_id, path=str(path), format=format, artboard_index=artboard_index,
        overwrite=overwrite, bleed_mm=bleed_mm)
    if pdf_preset: p["pdf_preset"] = pdf_preset
    return await bridge.call("export_document", p, operation_id)


@mcp.tool(annotations=EDIT)
async def illona_save_document(
    document_id: DocId, filename: str, overwrite: bool = False, operation_id: OperationId | None = None,
) -> dict:
    """Save the FULL editable document as .ai in Illona's output folder. This updates its native file path.

    Includes all artboards and layers. Use export_document for a single-artboard copy that leaves source identity unchanged.
    """
    path = bridge.output_path(filename, ".ai")
    return await bridge.call("save_document", dict(document_id=document_id, path=str(path), overwrite=overwrite), operation_id)


@mcp.tool(annotations=READ)
async def illona_operation_status(operation_id: OperationId) -> dict:
    """Recover a completed operation's receipt without re-running it. Use after a timeout or interrupted response."""
    return bridge.operation_status(operation_id)


@mcp.resource("illona://design-guide")
def design_guide() -> str:
    """Illona workflow and coordinate reference."""
    return """Illona 0.4 — stable Illustrator, macOS, local stdio. 86 tools: 16 original, 66 pinned IE3 functions and 4 Creold tools.
Creold catalog includes 104 fixed originals. Use creold_action for 14 parameterized adaptations; their geometry is native POINTS, Y up.
Creold originals usually require a native dialog. Read creold-guide, launch by fixed script_id and recover the same operation ID after the dialog closes.
Advanced illona_pro_ tools use POINTS (pt), unlike original creation/editing tools that default to mm.
Advanced coordinates default to artboard-web (top-left, Y down); set_workflow or explicit coordinate_system can override.
Point text in advanced tools uses its baseline for Y; original Illona text uses top-left geometric bounds.
Use document_id for document-specific advanced tools and target_artboard to choose a temporary active board.
Both tool families use the same native UUIDs. Reads do not modify user notes.
Native advanced PDF options are advisory; original export_document independently verifies physical PDF bleed.
Workflow: status → inspect → plan → create/edit → preview → refine → preflight → save/export.
Always use the explicit document ID returned by status or creation. IDs last for the Illustrator scripting session.
Object IDs are Illustrator UUIDs. Coordinates for creation/editing: top-left of artboard, x right, y down; mm or pt.
Inspection bounds: native document points, x right, y up. Font size, leading and stroke width are points.
Trifold panel content order: outer flap / back / cover; inside left / middle / right. Fold compensation is configurable.
Brochure guides do not print; supplied bleed is a design parameter, not a printer-approved specification.
All output is written to the configured output directory. Native AI save changes the document path; export-copy does not.
Full text replacement can reset mixed formatting. Preview and inspect after editing.
Timed-out writes may continue in Illustrator. Keep operation IDs and recover receipts before proceeding.
Do not claim certified print compliance or autonomous professional quality from a success response.
"""


def main():
    mcp.run(transport="stdio")


from .ie3 import register_advanced_tools

advanced = register_advanced_tools(mcp, bridge)
from .ie3_prompts import register_prompts
register_prompts(mcp)
from .learning import register_learning
register_learning(mcp)
from .creold import register_creold
creold = register_creold(mcp, bridge, READ, CREATE, EDIT)


if __name__ == "__main__":
    main()

