"""All pinned IE3 tools, with Illona document targeting and durable native steps.

The Node adapter owns upstream validation and postprocessing. It cannot launch
Illustrator: every native request comes back through this bridge and its lock.
"""

import asyncio
import copy
import hashlib
import json
import os
import shutil
import time
import uuid
from pathlib import Path

from jsonschema import Draft202012Validator
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations
from pypdf import PdfReader

from .bridge import APP_PATH, OP_ID, IE3_FILES, BridgeError, IllonaBridge

INTEGRATION = IE3_FILES
PREFIX = "illona_pro_"
GLOBAL_TOOLS = {"create_document", "open_document", "list_fonts", "set_workflow", "set_illustrator_version"}
INPUT_PATHS = {"open_document": "path", "place_image": "file_path", "import_svg_as_editable": "file_path", "manage_linked_images": "new_path"}


class IE3Integration:
    def __init__(self, bridge: IllonaBridge):
        self.bridge = bridge
        raw = json.loads((INTEGRATION / "catalog.json").read_text())
        self.catalog = {t["name"]: t for t in (raw["tools"] if isinstance(raw, dict) else raw)}
        self._process = None
        self._stderr_task = None
        self._workflow_coordinate = "artboard-web"
        self._session = {"workflow": None, "coordinate_system": None, "illustrator_version": None}

    def list_tools(self) -> list[Tool]:
        tools = []
        for name, entry in self.catalog.items():
            schema = copy.deepcopy(entry["inputSchema"])
            schema.setdefault("type", "object")
            props = schema.setdefault("properties", {})
            props["operation_id"] = {"type": "string", "pattern": OP_ID.pattern,
                "description": "Stable operation ID. Recover with illona_operation_status after interruption; never blindly repeat a mutation."}
            if name not in GLOBAL_TOOLS:
                props["document_id"] = {"type": "string", "minLength": 1, "maxLength": 200,
                    "description": "Explicit Illona session document ID from illona_status. Never infer from the active window."}
                schema.setdefault("required", []).append("document_id")
                props["target_artboard"] = {"type": "integer", "minimum": 0, "maximum": 999,
                    "description": "Optional zero-based artboard to activate only while executing this tool. Upstream artboard_index filters retain their meaning."}
            schema["additionalProperties"] = False
            description = ("Illona advanced tool. Geometry is in POINTS, never millimetres. Default coordinates: artboard top-left, X right/Y down; set_workflow or coordinate_system can override. UUIDs are the same native IDs as the original Illona tools. "
                + entry["description"].replace("active document", "explicitly targeted document"))
            if name == "export_pdf":
                description += " Native PDF marks/profile/bleed options vary by Illustrator version. Returned geometry is advisory; use illona_export_document for physically verified single-artboard bleed. No PDF/X certification."
            if name == "create_gradient":
                props["name"]["minLength"] = 1
                props["name"]["maxLength"] = 31
                props["name"]["description"] = "Native Illustrator gradient name, 1–31 characters. Longer names are rejected before creating artwork."
                props["angle"]["description"] = "Absolute linear-gradient direction in native document degrees (positive counterclockwise). Illona transforms the fill without moving artwork, fits the directional span, and reports matrix/bounds verification. Inspect the preview for visual quality."
                description += " Linear direction uses a native fill-only transform; gradient_direction reports the effective angle and geometry preservation."
            tools.append(Tool(name=PREFIX + name, title=entry.get("title"), description=description,
                inputSchema=schema, annotations=ToolAnnotations(**entry.get("annotations", {}))))
        return tools

    def _validate(self, name: str, arguments: dict) -> None:
        if name not in self.catalog:
            raise BridgeError("Unknown advanced Illona tool")
        if not isinstance(arguments, dict) or len(json.dumps(arguments, allow_nan=False)) > 2_000_000:
            raise BridgeError("Tool arguments must be a bounded JSON object")
        schema = next(t.inputSchema for t in self.list_tools() if t.name == PREFIX + name)
        errors = sorted(Draft202012Validator(schema).iter_errors(arguments), key=lambda e: str(e.path))
        if errors:
            raise BridgeError("Invalid advanced tool arguments: " + errors[0].message[:1200])
        if name == "close_document" and "save" in arguments and type(arguments["save"]) is not bool:
            raise BridgeError("close_document save must be an explicit boolean")

    def _input_path(self, value: str) -> str:
        path = Path(value).expanduser()
        if not path.is_absolute() or "\0" in value or not path.is_file():
            raise BridgeError("Input must be an existing absolute local file")
        if path.stat().st_size > 200 * 1024 * 1024:
            raise BridgeError("Input file exceeds the 200 MB limit")
        return str(path.resolve())

    def _prepare_paths(self, name: str, params: dict, operation_id: str) -> dict:
        params = copy.deepcopy(params)
        if name in INPUT_PATHS and params.get(INPUT_PATHS[name]) is not None:
            key = INPUT_PATHS[name]
            params[key] = self._input_path(params[key])
        extensions = {"export_pdf": ".pdf", "export": "." + params.get("format", "svg")}
        if name in extensions:
            suffix = extensions[name]
            filename = params.get("output_path") or f"advanced/{name}-{operation_id}{suffix}"
            if not Path(filename).suffix:
                filename += suffix
            params["output_path"] = str(self.bridge.output_path(filename, suffix))
        if name == "extract_design_tokens" and params.get("output_path"):
            params["output_path"] = str(self.bridge.output_path(params["output_path"]))
        if name == "save_document" and params.get("mode", "save") == "save_as":
            params["path"] = str(self.bridge.output_path(params.get("path") or f"advanced/document-{operation_id}.ai", ".ai"))
        if name == "manage_datasets" and params.get("file_path"):
            if params.get("action") == "export":
                path = self.bridge.output_path(params["file_path"], ".xml")
                if path.exists():
                    raise BridgeError("Dataset export refuses to replace an existing XML file; choose a new filename")
                params["file_path"] = str(path)
            else:
                params["file_path"] = self._input_path(params["file_path"])
        return params

    def _verify_outputs(self, name, params, output):
        """Read exported bytes after native execution; never repeat a write to verify it."""
        expected = []
        if name in {"export_pdf", "extract_design_tokens"} and params.get("output_path"):
            expected.append(params["output_path"])
        if name == "export":
            # Native SVG export may rename even one artboard; verify actual paths.
            def paths(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key in {"output_path", "path"} and isinstance(child, str):
                            expected.append(child)
                        else:
                            paths(child)
                elif isinstance(value, list):
                    for child in value: paths(child)
            for content in output.content:
                if content.type == "text":
                    try: paths(json.loads(content.text))
                    except ValueError: pass
            if not expected:
                raise BridgeError("Export did not return any output files")
        if name == "save_document" and params.get("mode") == "save_as": expected.append(params["path"])
        if name == "manage_datasets" and params.get("action") == "export": expected.append(params["file_path"])
        for filename in set(expected):
            path = self.bridge.output_path(filename)
            if not path.is_file() or not path.stat().st_size:
                raise BridgeError("Expected output file was not produced: " + str(path))
            with path.open("rb") as stream: header = stream.read(1024)
            suffix = path.suffix.lower()
            if suffix == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
                raise BridgeError("Exported PNG has an invalid header")
            if suffix in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8"):
                raise BridgeError("Exported JPEG has an invalid header")
            if suffix in {".pdf", ".ai"} and not header.startswith((b"%PDF-", b"%!PS")):
                raise BridgeError("Saved PDF/AI has an invalid header")
            if suffix == ".pdf":
                try:
                    reader = PdfReader(path)
                    if not len(reader.pages): raise BridgeError("Exported PDF contains no pages")
                    geometry = [{"media_pt": list(map(float, page.mediabox)), "trim_pt": list(map(float, page.trimbox)),
                        "bleed_pt": list(map(float, page.bleedbox))} for page in reader.pages]
                except Exception as exc:
                    raise BridgeError("Exported PDF is not readable: " + str(exc)) from exc
                output.content.append(TextContent(type="text", text=json.dumps({"pdf_verification": {
                    "readable": True, "page_count": len(reader.pages), "geometry": geometry,
                    "physical_bleed_verified": False, "pdfx_certified": False,
                    "note": "Native PDF options are advisory. Use illona_export_document for independently verified physical bleed on a single-artboard copy."}})))

    async def _start(self):
        if self._process is not None and self._process.returncode is None:
            return
        node = os.getenv("ILLONA_NODE") or shutil.which("node")
        if not node:
            bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
            node = str(bundled) if bundled.is_file() else None
        if not node:
            raise BridgeError("Illona advanced tools require Node.js 20 or later. Set ILLONA_NODE to its absolute path.")
        adapter = INTEGRATION / "adapter.cjs"
        if not adapter.is_file():
            raise BridgeError("Illona advanced adapter is not built. Run node build.mjs in integrations/ie3 after npm ci --ignore-scripts.")
        self._process = await asyncio.create_subprocess_exec(node, str(adapter), cwd=str(INTEGRATION),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            limit=16 * 1024 * 1024)
        process = self._process
        async def drain():
            while await process.stderr.read(4096):
                pass
        self._stderr_task = asyncio.create_task(drain())

    async def close(self):
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), 3)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        if self._stderr_task:
            await self._stderr_task
        self._process = None

    async def _send(self, value):
        self._process.stdin.write((json.dumps(value, ensure_ascii=True, allow_nan=False) + "\n").encode())
        await self._process.stdin.drain()

    async def invoke(self, name: str, arguments: dict) -> CallToolResult:
        name = name.removeprefix(PREFIX)
        self._validate(name, arguments)
        original = copy.deepcopy(arguments)
        operation_id = arguments.get("operation_id") or uuid.uuid4().hex
        params = {k: v for k, v in arguments.items() if k not in {"operation_id", "document_id", "target_artboard"}}
        digest = hashlib.sha256(json.dumps([name, original], sort_keys=True, allow_nan=False).encode()).hexdigest()
        job = self.bridge._job(operation_id)
        async with self.bridge.transaction(root_operation=operation_id):
            request = job / "request.json"
            receipt = job / "result.json"
            if request.exists():
                meta = json.loads(request.read_text())
                if meta["digest"] != digest:
                    raise BridgeError("This operation_id belongs to a different request")
                if receipt.exists():
                    data = json.loads(receipt.read_text())["data"]
                    saved = data["upstream_result"]
                    if name in {"set_workflow", "set_illustrator_version"} and data.get("session"):
                        self._session = data["session"]
                        self._workflow_coordinate = self._session["coordinate_system"] or "artboard-web"
                        selected = self._session["illustrator_version"]
                        self.bridge.app_path = Path(f"/Applications/Adobe Illustrator {selected}/Adobe Illustrator.app") if selected else Path(os.getenv("ILLONA_APP_PATH", APP_PATH))
                    return CallToolResult.model_validate(saved)
            else:
                meta = {"operation": "pro:" + name, "digest": digest, "created_at": time.time(), "status": "pending"}
            params = copy.deepcopy(meta["prepared_params"]) if meta.get("prepared_params") is not None else self._prepare_paths(name, params, operation_id)
            job.mkdir(parents=True, exist_ok=True, mode=0o700)
            request.write_text(json.dumps(meta))
            step = 0
            ambiguous = False
            documents = []
            sub_ids = []
            try:
                # Native save/close may otherwise write outside the configured output directory.
                allowed_save_path = None
                if (name == "save_document" and params.get("mode", "save") == "save") or (name == "close_document" and params.get("save") is True):
                    current = await self.bridge.call("inspect_document", {"document_id": arguments["document_id"], "limit": 1})
                    if not current.get("path"):
                        raise BridgeError("Save the unsaved document with save_as before saving or closing with save=true")
                    allowed_save_path = str(self.bridge.output_path(current["path"], ".ai"))
                await self._start()
                if "coordinate_system" in self.catalog[name]["inputSchema"].get("properties", {}) and name != "set_workflow":
                    params.setdefault("coordinate_system", self._workflow_coordinate)
                call_session = copy.deepcopy(meta.get("session", self._session))
                meta["prepared_params"] = copy.deepcopy(params)
                meta["session"] = call_session
                request.write_text(json.dumps(meta))
                call_id = uuid.uuid4().hex
                await self._send({"id": call_id, "method": "invoke", "params": {"name": name, "arguments": params, "session": call_session}})
                while True:
                    line = await asyncio.wait_for(self._process.stdout.readline(), max(self.bridge.timeout + 20, 80))
                    if not line:
                        raise BridgeError("Advanced adapter stopped before a result; inspect the operation receipt before retrying")
                    event = json.loads(line)
                    if event.get("event") == "execute_jsx":
                        if (event.get("request_id") != call_id or event.get("execution_id") != f"{call_id}:{step + 1}"
                            or not isinstance(event.get("jsx"), str) or len(event["jsx"]) > 2_000_000
                            or not isinstance(event.get("params"), dict) or not isinstance(event.get("options"), dict)):
                            raise BridgeError("Invalid or out-of-order advanced native request")
                        selected_app = event.get("app_path")
                        selected_version = call_session.get("illustrator_version")
                        expected_app = f"/Applications/Adobe Illustrator {selected_version}/Adobe Illustrator.app" if selected_version else None
                        if selected_app != expected_app:
                            raise BridgeError("Advanced adapter requested an unexpected Illustrator application")
                        step += 1
                        native = {"document_id": arguments.get("document_id"), "tool_name": name,
                            "script": event["jsx"], "params": event.get("params") or {},
                            "creates_document": name in {"create_document", "open_document"}}
                        if "target_artboard" in arguments:
                            native["target_artboard"] = arguments["target_artboard"]
                        if allowed_save_path:
                            native["allowed_save_path"] = allowed_save_path
                        sub_id = "pro_" + hashlib.sha256(operation_id.encode()).hexdigest()[:32] + "_" + str(step)
                        sub_ids.append(sub_id)
                        meta["native_steps"] = sub_ids[:]
                        request.write_text(json.dumps(meta))
                        old_app = self.bridge.app_path
                        if event.get("app_path"):
                            self.bridge.app_path = Path(event["app_path"])
                        try:
                            result = await self.bridge.call("ie3_execute", native, sub_id)
                            if result.get("document"):
                                documents.append(result["document"])
                            response = {"execution_id": event["execution_id"], "result": result["result"]}
                        except BridgeError as exc:
                            status = self.bridge.operation_status(sub_id)["status"]
                            ambiguous = ambiguous or status in {"pending", "uncertain", "finishing"}
                            response = {"execution_id": event["execution_id"], "error": {"message": str(exc)}}
                        finally:
                            self.bridge.app_path = old_app
                        await self._send({"method": "jsx_result", "params": response})
                        continue
                    if event.get("id") != call_id:
                        raise BridgeError("Unexpected advanced adapter protocol response")
                    if event.get("error"):
                        raise BridgeError(str(event["error"]))
                    if event.get("session"):
                        self._session = event["session"]
                        self._workflow_coordinate = self._session["coordinate_system"] or "artboard-web"
                    output = CallToolResult.model_validate(event["result"])
                    if ambiguous:
                        raise BridgeError(f"Operation {operation_id} has an uncertain native step. Use illona_operation_status before continuing.")
                    if not output.isError:
                        if name == "set_workflow":
                            if params.get("clear"):
                                self._workflow_coordinate = "artboard-web"
                            elif params.get("workflow") or params.get("coordinate_system"):
                                self._workflow_coordinate = params.get("coordinate_system") or ("document" if params.get("workflow") == "print" else "artboard-web")
                        if name == "set_illustrator_version":
                            if params.get("clear"):
                                self.bridge.app_path = Path(os.getenv("ILLONA_APP_PATH", APP_PATH))
                            elif params.get("version"):
                                self.bridge.app_path = Path(f"/Applications/Adobe Illustrator {params['version']}/Adobe Illustrator.app")
                        if name == "manage_datasets" and params.get("action") == "export" and not Path(params["file_path"]).is_file():
                            raise BridgeError("Illustrator did not produce the requested dataset XML")
                        self._verify_outputs(name, params, output)
                    info = {"operation_id": operation_id, "native_steps": step}
                    if documents:
                        info["documents"] = documents
                        info["document_id"] = documents[-1]["id"]
                    output.content.append(TextContent(type="text", text=json.dumps({"illona": info})))
                    staged = receipt.with_suffix(".pending.json")
                    staged.write_text(json.dumps({"ok": True, "data": {"upstream_result": output.model_dump(mode="json"), "session": self._session}}, ensure_ascii=True))
                    os.replace(staged, receipt)
                    meta["status"] = "completed"
                    request.write_text(json.dumps(meta))
                    return output
            except BaseException as exc:
                if isinstance(exc, BridgeError) and sub_ids and not ambiguous and all(self.bridge.operation_status(s)["status"] in {"completed", "not_started", "unknown"} for s in sub_ids):
                    failure = CallToolResult(isError=True, content=[TextContent(type="text", text=json.dumps({
                        "error": str(exc), "operation_id": operation_id, "native_steps": step,
                        "outcome": "known_failure", "message": "Completed native steps are recorded. Inspect artwork before making further edits; this request will not be repeated."}))])
                    staged = receipt.with_suffix(".pending.json")
                    staged.write_text(json.dumps({"ok": True, "data": {"upstream_result": failure.model_dump(mode="json"), "session": self._session}}))
                    os.replace(staged, receipt)
                    meta["status"] = "completed"
                    request.write_text(json.dumps(meta))
                    await self.close()
                    return failure
                meta["status"] = "uncertain" if step else "not_started"
                request.write_text(json.dumps(meta))
                await self.close()
                raise


def register_advanced_tools(mcp, bridge):
    integration = IE3Integration(bridge)
    old_list = mcp.list_tools
    old_call = mcp.call_tool

    @mcp._mcp_server.list_tools()
    async def list_tools():
        return [*await old_list(), *integration.list_tools()]

    @mcp._mcp_server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        if name.startswith(PREFIX):
            return await integration.invoke(name, arguments)
        return await old_call(name, arguments)
    return integration
