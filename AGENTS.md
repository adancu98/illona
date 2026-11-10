# Working on Illona

Illona is a local stdio MCP server for stable Adobe Illustrator on macOS. Python validates requests and owns document targeting, output paths, serialization, and durable receipts. Fixed ExtendScript handlers perform native work through AppleScript. The packaged Node adapter supplies the 66 Pro tools.

## Repository boundaries

- `illona_mcp/`: server, validation models, native bridge, and reusable workflow resources.
- `illona_mcp/host/`: native handlers and AppleScript runners.
- `illona_mcp/ie3_runtime/`: built Pro adapter, catalog, helpers, provenance, and licenses.
- `illona_mcp/creold_runtime/`: pinned originals, companion assets, integrity catalog, archives, and license.
- `.agents/skills/illona/`: guidance for creating artwork through the server.
- `tests/`: offline validation, stdio contracts, and native-host simulations.

Keep runtime artifacts and private work out of version control: `.illona-state/`, `output/`, `.venv/`, caches, local configuration, credentials, conversation exports, and personal design assets. Add reusable procedures without embedding a user's project history or treating unapproved examples as preferences.

## Implementation invariants

Use explicit document IDs and native object UUIDs. Do not fall back to the active window, write identifiers into artwork notes, or expose caller-supplied JSX or shell code. Validate an entire input batch before its first mutation where supported; report partial native failures honestly.

Preserve the coordinate contract: original tools default to mm and artboard-local Y down; Pro tools use points with explicit coordinate-system handling; native inspection and Creold geometry use document points with Y up. Point text baselines and area-text frames have different placement semantics.

Maintain the per-process and cross-process transaction guards, stable operation IDs, and durable receipts. A timed-out mutation can still be running in Illustrator. Do not automatically retry ambiguous work or weaken the pending-operation guard to make a test pass. Preserve supported same-request receipt recovery.

Keep output-path confinement and source/companion integrity validation in Python. Original-script static metadata and native write guards are not a universal ExtendScript sandbox. Retain upstream copyright notices and licenses; do not patch pinned originals without deliberately updating provenance and integrity metadata. Keep the packaged Pro adapter and its catalog synchronized; avoid hand-editing a generated bundle.

Authored host JSX must remain ECMAScript 3 compatible. Avoid modern JavaScript syntax there. Preserve JSON argument encoding, Unicode behavior, group stacking, native object subtypes, and gradient geometry/stroke read-back. New native operations need bounded inputs and accurate result semantics.

## Offline verification

From the repository root, install dependencies with `sh setup.sh` using a Python 3.11+ interpreter. Node.js 20+ is required for Pro handlers and host simulations. Run checks appropriate to the change:

```sh
.venv/bin/python -m pytest -q
node tests/host_core_test.cjs
node --test tests/creold_host.test.cjs tests/creold_trace.test.cjs
node illona_mcp/ie3_runtime/adapter.cjs --catalog
```

These checks must not launch Illustrator or edit a live document. Use temporary state/output directories and a nonexistent application path when testing rejection paths or mocked native calls. Keep CI offline with respect to Illustrator; list/catalog/schema tests are distinct from native acceptance.

Run native acceptance only for work that actually requires it and within the user's authorized scope. Prefer a new disposable document and preserve unrelated open documents. Inspect geometry and previews, save the requested source/export, and report native verification separately from simulated tests. If the user stops, do not issue further native mutations; reconcile any already-running operation through its receipt rather than blindly repeating it.

Update tool schemas, catalogs, workflow resources, and relevant documentation when behavior changes. Preflight and tracing results have practical limits: tests and successful exports do not certify visual quality, wholly vector content, PDF/X compliance, or printer acceptance. Publishing code or artwork requires user intent for that external action.
