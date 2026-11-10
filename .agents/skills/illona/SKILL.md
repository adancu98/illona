---
name: illona
description: Create, inspect, and refine editable vector illustrations, logos, typography, and brochure layouts in Adobe Illustrator through the local Illona MCP server. Use for native Illustrator artwork and exports; ordinary raster photo editing belongs in an image editor.
---

# Illona Illustrator

Use the connected Illona tools for the user's requested artwork. The current server exposes 86 tools: 16 original tools, 66 `illona_pro_` tools, and four Creold tools. `illona_creold_action` offers 14 parameterized actions; the original Creold catalog contains 104 scripts. Consult the actual schemas rather than treating a catalog entry as proof that every original supports unattended execution.

Read the relevant MCP resource when planning the work:

- `illona://design-guide`: document targeting, coordinates, drawing, and exports.
- `illona://learning-playbook`: procedures for illustration, logos, typography, alignment, and color.
- `illona://creold-guide`: direct actions and original scripts with native dialogs.

## Target and units

Get a current `document_id` from `illona_status` or document creation. Inspect an existing document before editing it, and address objects by the returned native UUIDs. An active window or a filename is not a substitute for an explicit document ID. IDs can change after reopening, duplication, outlining, embedding, or tracing; use the new IDs returned by those operations.

Keep the coordinate families distinct:

| Interface | Geometry and origin |
| --- | --- |
| Original drawing/editing tools | Default mm; artboard top-left, X right and Y down. Use explicit `units` and zero-based `artboard_index`. |
| `illona_pro_` | Points; default `artboard-web` is top-left with Y down. An explicit `coordinate_system="document"` uses native points with Y up. `target_artboard` is zero-based. |
| Inspection and Creold direct geometry | Native document points with Y up; options ending in `_pt` do not mean mm. |

Use `1 mm = 72 / 25.4 pt`. Font sizes, leading, and stroke widths are in points. Pro point text uses its baseline for Y; original text placement uses its geometric top-left. Area text requires a frame. Resolve the installed PostScript font name before creating live text.

## Work and recover

Build within the user's brief and authorized scope. Keep a usable editable master, and organize layers and groups by their role in the artwork. In `group_objects`, the first UUID is the back item and the last is the front item; a clipping group's final UUID is its mask.

Use stable `operation_id` values for mutations. Check `isError` and partial-result diagnostics. After a timeout or interruption, use `illona_operation_status` with the same ID and reconcile its receipt before another edit. States such as `queued`, `waiting_for_user`, `pending`, and `uncertain` do not prove failure; do not repeat the mutation under a fresh ID. If the tool offers same-request recovery, preserve its arguments and ID.

For a Creold original, read `illona_creold_script_info` first. Complete or cancel its Illustrator dialog and then inspect the recorded result. `script_returned` is not verified artwork modification. Apply application-wide or multi-document scripts only when that scope is covered by the user's request.

When the user stops, stop issuing new artwork commands and halt only orchestration you started when needed. A native operation may already be finishing; do not discard documents or quit Illustrator as a substitute for cancellation. Creating artwork does not itself authorize publishing, sharing, uploading, or messaging.

## Artwork decisions

- **Illustration:** establish silhouette, perspective, light direction, and a coherent palette. Use deliberate Bézier handles and purposeful detail. Check geometry and the rendered result together, including strokes after gradient or scale changes.
- **Logo:** preserve the requested wording, inspect letter spacing and negative space, and check a small-size and monochrome view. Keep editable paths/text in the master; create outlined copies only for a delivery need.
- **Brochure:** establish page order, folds if any, a consistent grid, margins, and typographic hierarchy. Keep body text readable, use the supplied content accurately, and inspect every face. For ordinary print brochures, 3 mm bleed is a starting value only when the brief or printer does not specify another value.

Use `illona_preview_document` after meaningful stages and inspect the image before proceeding to delivery. A successful operation or extracted PDF text does not prove that text is visible, unclipped, or correctly layered. Revise observed problems rather than assuming the first render is finished.

## Vectors, images, and delivery

Distinguish editable vector paths, live text, and embedded or linked bitmap images. `trace_images` expands an image into paths, but tracing is an approximation and does not recover missing photographic detail. Use an installed tracing preset; inspect the returned group, replacement IDs, bounds, and raster/placed/plugin counts. Removing white can also remove artwork and change bounds.

If the user requires a wholly vector deliverable, verify the final native artwork and exported file rather than inferring this from an `.ai`, `.svg`, or `.pdf` extension. Check for residual images, raster effects, or page image resources. Describe any retained bitmap content accurately.

Save the full native master with `illona_save_document`; single-artboard export copies have different preservation limits. Keep outputs inside the configured output directory. For print PDFs, verify page count, intended dimensions, TrimBox/BleedBox, and rendered pages. Preflight is advisory: report supported checks and material gaps without claiming PDF/X certification, exact overset detection, or printer approval. Deliver the requested files and concise evidence of what was checked.
