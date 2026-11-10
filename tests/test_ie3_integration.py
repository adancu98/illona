"""Check the full compatibility boundary without launching or editing Illustrator.

The real stdio server and bundled Node handlers are used.  Invalid native calls
run with an intentionally nonexistent Illustrator path, so an accidental bridge
dispatch cannot reach a user's open document.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from illona_mcp.bridge import BridgeError, IllonaBridge
from illona_mcp.ie3 import IE3Integration


ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ROOT / "research" / "ie3jp-illustrator-mcp-server"
PREFIX = "illona_pro_"
BASE_TOOLS = {
    "illona_status", "illona_inspect_document", "illona_inspect_selection",
    "illona_list_fonts", "illona_create_document", "illona_create_elements",
    "illona_update_objects", "illona_plan_brochure", "illona_create_brochure",
    "illona_create_illustration", "illona_create_icon_set", "illona_preflight_document",
    "illona_preview_document", "illona_export_document", "illona_save_document",
    "illona_operation_status",
    "illona_creold_catalog", "illona_creold_script_info",
    "illona_creold_run_script", "illona_creold_action",
}


def upstream_tool_names():
    names = set()
    for path in (UPSTREAM / "src" / "tools").rglob("*.ts"):
        names.update(re.findall(r"registerTool\(\s*['\"]([^'\"]+)['\"]", path.read_text()))
    if not names:
        catalog = json.loads((ROOT / "illona_mcp" / "ie3_runtime" / "catalog.json").read_text())
        names = {tool["name"] for tool in catalog["tools"]}
    return names


@asynccontextmanager
async def live_stdio(tmp_path):
    env = {
        **os.environ,
        "ILLONA_STATE_DIR": str(tmp_path / "state"),
        "ILLONA_OUTPUT_DIR": str(tmp_path / "output"),
        "ILLONA_APP_PATH": str(tmp_path / "must-never-launch-Illustrator.app"),
    }
    params = StdioServerParameters(command=str(ROOT / "run.sh"), cwd=str(ROOT), env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def response_text(result):
    return "\n".join(item.text for item in result.content if item.type == "text")


def response_json(result):
    assert not result.isError, response_text(result)
    for item in result.content:
        if item.type == "text":
            try:
                return json.loads(item.text)
            except ValueError:
                pass
    raise AssertionError(f"Expected a JSON text response: {result}")


def test_stdio_exposes_every_upstream_tool_alongside_original_illona_tools(tmp_path):
    async def check():
        source_names = upstream_tool_names()
        assert len(source_names) == 66, "Update the compatibility fixture deliberately when upgrading the pinned upstream."
        async with live_stdio(tmp_path) as session:
            tools = (await session.list_tools()).tools
        names = [tool.name for tool in tools]
        assert len(names) == len(set(names)), "A compatibility alias must not shadow a base Illona tool."
        assert set(names) == BASE_TOOLS | {PREFIX + name for name in source_names}
        assert len(names) == 86

    asyncio.run(check())


def test_compatibility_schemas_bind_documents_without_exposing_arbitrary_jsx(tmp_path):
    async def check():
        async with live_stdio(tmp_path) as session:
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
        for name in ("get_document_info", "get_selection", "modify_object", "export_pdf", "preflight_check", "close_document"):
            tool = tools[PREFIX + name]
            schema = tool.inputSchema
            assert "document_id" in schema["properties"], name
            assert "document_id" in schema.get("required", []), name
        for tool in tools.values():
            if tool.name.startswith(PREFIX):
                assert tool.description, tool.name
                assert not ({"script", "jsx", "jsx_code", "code", "toolScript"} & set(tool.inputSchema.get("properties", {}))), tool.name
        assert not ({PREFIX + "run_script", PREFIX + "execute_jsx", PREFIX + "execute_script"} & set(tools))

    asyncio.run(check())


def test_missing_document_id_is_rejected_at_stdio_validation_boundary(tmp_path):
    async def check():
        async with live_stdio(tmp_path) as session:
            for name, args in (("get_selection", {}), ("export_pdf", {"output_path": str(tmp_path / "output" / "x.pdf")})):
                result = await session.call_tool(PREFIX + name, args)
                assert result.isError, (name, result)
                message = response_text(result)
                assert "document_id" in message, message
                assert "Illustrator was not found" not in message, "Missing-document validation must happen before native dispatch."
        assert not (tmp_path / "state" / "jobs").exists()

    asyncio.run(check())


@pytest.mark.parametrize("tool,args", [
    ("export", {"target": "artboard:0", "format": "png", "output_path": "../escape.png"}),
    ("export_pdf", {"output_path": "../escape.pdf"}),
    ("save_document", {"mode": "save_as", "path": "../escape.ai"}),
    ("manage_datasets", {"action": "export", "file_path": "../escape.xml"}),
    ("extract_design_tokens", {"format": "json", "output_path": "../escape.json"}),
])
def test_compatibility_output_paths_cannot_escape_before_native_dispatch(tmp_path, tool, args):
    async def check():
        async with live_stdio(tmp_path) as session:
            result = await session.call_tool(PREFIX + tool, {"document_id": "doc-never-dispatch", **args})
            assert result.isError, result
            message = response_text(result)
            assert "Illustrator was not found" not in message, "Unsafe output paths must be checked before the host is called."
            assert any(word in message.lower() for word in ("output", "inside", "absolute", "path", "confine")), message
        assert not (tmp_path / "state" / "jobs").exists()
        assert not list(tmp_path.glob("escape.*"))

    asyncio.run(check())


def test_workflow_settings_persist_across_node_handler_calls(tmp_path):
    async def check():
        async with live_stdio(tmp_path) as session:
            set_result = response_json(await session.call_tool(PREFIX + "set_workflow", {"workflow": "print"}))
            assert set_result["workflow"] == "print"
            assert set_result["coordinateSystem"] == "document"
            queried = response_json(await session.call_tool(PREFIX + "set_workflow", {}))
            assert queried["currentWorkflow"] == "print"
            assert queried["currentCoordinateSystem"] == "document"
            cleared = response_json(await session.call_tool(PREFIX + "set_workflow", {"clear": True}))
            assert cleared["status"] == "cleared"
            queried = response_json(await session.call_tool(PREFIX + "set_workflow", {}))
            assert queried["currentWorkflow"] is None
            assert queried["currentCoordinateSystem"] is None
        assert not list((tmp_path / "state").rglob("request.jsx")), "Workflow configuration must not execute native scripts."
        for request in (tmp_path / "state").rglob("request.json"):
            assert json.loads(request.read_text())["operation"] != "ie3_execute"

    asyncio.run(check())


def make_bridge(tmp_path):
    bridge = IllonaBridge(state_dir=tmp_path / "state", output_dir=tmp_path / "output")
    bridge.app_path = tmp_path / "must-never-launch-Illustrator.app"
    return bridge


def illona_metadata(result):
    for item in result.content:
        if item.type == "text":
            try:
                payload = json.loads(item.text)
            except ValueError:
                continue
            if "illona" in payload:
                return payload["illona"]
    raise AssertionError("The advanced result must include Illona recovery/document metadata.")


def test_real_node_handler_uses_explicit_document_and_replays_without_native_execution(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path)
        native_calls = []

        async def native(operation, params, operation_id=None):
            native_calls.append((operation, params, operation_id))
            return {"result": {"uuid": "native-item-42", "verified": {"uuid": "native-item-42"}}}

        monkeypatch.setattr(bridge, "call", native)
        integration = IE3Integration(bridge)
        args = {"document_id": "doc-explicit", "target_artboard": 1, "operation_id": "rectangle-once",
                "x": 12, "y": 18, "width": 90, "height": 40, "coordinate_system": "artboard-web"}
        try:
            result = await integration.invoke(PREFIX + "create_rectangle", args)
            assert response_json(result)["uuid"] == "native-item-42"
            assert len(native_calls) == 1
            operation, params, step_id = native_calls[0]
            assert operation == "ie3_execute"
            assert params["document_id"] == "doc-explicit"
            assert params["target_artboard"] == 1
            assert params["tool_name"] == "create_rectangle"
            assert params["params"]["width"] == 90
            assert params["creates_document"] is False
            assert isinstance(params["script"], str) and "rectangle" in params["script"]
            assert step_id and step_id != "rectangle-once"
            assert illona_metadata(result)["native_steps"] == 1
            replayed = await integration.invoke(PREFIX + "create_rectangle", args)
            assert replayed.model_dump() == result.model_dump()
            assert len(native_calls) == 1, "A committed operation must not execute Illustrator twice."
            with pytest.raises(BridgeError, match="different request"):
                await integration.invoke(PREFIX + "create_rectangle", {**args, "width": 91})
            assert len(native_calls) == 1
        finally:
            await integration.close()

    asyncio.run(check())


def test_new_document_metadata_is_registered_and_returned_with_upstream_result(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path)
        calls = []

        async def native(operation, params, operation_id=None):
            calls.append(params)
            return {"result": {"success": True, "fileName": "Created.ai", "width": 400, "height": 300},
                    "document": {"id": "doc-created", "name": "Created.ai", "artboard_count": 1}}

        monkeypatch.setattr(bridge, "call", native)
        integration = IE3Integration(bridge)
        try:
            result = await integration.invoke("create_document", {"width": 400, "height": 300, "operation_id": "create-once"})
            assert response_json(result)["success"] is True
            assert calls[0]["creates_document"] is True
            assert calls[0]["document_id"] is None
            assert illona_metadata(result)["document_id"] == "doc-created"
            assert illona_metadata(result)["documents"][0]["name"] == "Created.ai"
        finally:
            await integration.close()

    asyncio.run(check())


def test_partial_native_failure_preserves_counts_and_ids_as_mcp_error(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path)
        partial = {"success": False, "movedCount": 1, "notFound": ["missing-native-id"],
                   "verified": [{"uuid": "moved-native-id"}], "errors": []}

        async def native(*args, **kwargs):
            return {"result": partial}

        monkeypatch.setattr(bridge, "call", native)
        integration = IE3Integration(bridge)
        try:
            result = await integration.invoke("move_to_layer", {"document_id": "doc-explicit", "uuids": ["moved-native-id", "missing-native-id"], "target_layer": "Destination"})
            assert result.isError
            data = json.loads(result.content[0].text)
            assert data["movedCount"] == 1
            assert data["notFound"] == ["missing-native-id"]
            assert data["verified"] == [{"uuid": "moved-native-id"}]
        finally:
            await integration.close()

    asyncio.run(check())


def test_preflight_retains_node_postprocessing_and_incomplete_coverage(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path)
        unsupported = tmp_path / "linked.pdf"
        unsupported.write_bytes(b"%PDF-1.7\n")

        async def native(*args, **kwargs):
            return {"result": {"checkCount": 0, "results": [],
                    "coverage": {"low_resolution": {"status": "checked"}, "transparency": {"status": "checked"}},
                    "placedImageData": [{"uuid": "linked-native-id", "name": "Linked PDF", "filePath": str(unsupported), "widthPt": 72, "heightPt": 72, "matrixScaleX": 1, "matrixScaleY": 1}],
                    "minDPI": 300, "targetPdfProfile": "x1a",
                    "pdfxSummary": {"hasRGBItems": False, "hasTransparencyItems": True, "hasSpotColors": False, "colorProfileName": "", "isCMYKDoc": True}}}

        monkeypatch.setattr(bridge, "call", native)
        integration = IE3Integration(bridge)
        try:
            result = await integration.invoke("preflight_check", {"document_id": "doc-explicit", "coordinate_system": "document", "target_pdf_profile": "x1a"})
            data = response_json(result)
            assert any(item["category"] == "pdfx_compliance" for item in data["results"])
            assert data["coverage"]["low_resolution"]["status"] == "partial"
            assert data["coverage"]["transparency"]["status"] == "partial"
            assert "placedImageData" not in data, "Host postprocessing must consume the private image payload."
        finally:
            await integration.close()

    asyncio.run(check())


@pytest.mark.parametrize("field,value", [
    ("request_id", "another-invocation"),
    ("execution_id", "another-invocation:1"),
    ("jsx", {"unexpected": "object"}),
    ("params", ["unexpected", "array"]),
    ("app_path", "/tmp/untrusted-application.app"),
])
def test_python_broker_rejects_malformed_or_foreign_native_events_before_dispatch(tmp_path, monkeypatch, field, value):
    async def check():
        bridge = make_bridge(tmp_path)
        native_calls = []

        async def native(*args, **kwargs):
            native_calls.append((args, kwargs))
            return {"result": {"count": 0, "items": []}}

        monkeypatch.setattr(bridge, "call", native)
        integration = IE3Integration(bridge)
        lines = asyncio.Queue()

        class Stream:
            async def readline(self):
                return await lines.get()

        class Process:
            returncode = None
            stdout = Stream()

            def terminate(self):
                self.returncode = 0

            async def wait(self):
                return self.returncode

        async def start():
            integration._process = Process()

        async def send(message):
            if message.get("method") == "invoke":
                event = {"event": "execute_jsx", "request_id": message["id"], "execution_id": message["id"] + ":1",
                         "jsx": "writeResultFile(RESULT_PATH, {count: 0, items: []});", "params": {},
                         "options": {"activate": False, "heavy": False, "timeout_ms": 30000}, "app_path": None}
                event[field] = value
                await lines.put((json.dumps(event) + "\n").encode())
                # An unguarded implementation would dispatch the invalid event,
                # then see EOF. This makes the test fail quickly and safely.
                await lines.put(b"")

        monkeypatch.setattr(integration, "_start", start)
        monkeypatch.setattr(integration, "_send", send)
        try:
            with pytest.raises(BridgeError):
                await integration.invoke("get_selection", {"document_id": "doc-explicit", "operation_id": "invalid-broker-event"})
            assert native_calls == [], f"Malformed broker field {field} must not reach the native bridge."
        finally:
            await integration.close()

    asyncio.run(check())


def test_native_wrapper_keeps_early_returns_and_native_ids_without_writing_notes():
    node = os.getenv("ILLONA_TEST_NODE") or shutil.which("node")
    if not node:
        node = str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
    if not Path(node).is_file():
        pytest.skip("Node is unavailable for the isolated native-wrapper check")
    program = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const context = {
  app: {userInteractionLevel: 'original'},
  UserInteractionLevel: {DONTDISPLAYALERTS: 'silent'},
  _versionWarning: null,
  Illona: {fail: function(code, message) {throw new Error(code + ': ' + message);}}
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const result = context.illonaRunIe3({
  document_id: null, tool_name: 'isolated-wrapper-test', params: {}, creates_document: false,
  script: 'var item={uuid:"native-42",note:"original user note"};' +
          'writeResultFile(RESULT_PATH,{uuid:ensureUUID(item),note:item.note});' +
          'return;' +
          'throw new Error("Code after early return must not execute");'
});
assert.equal(result.result.uuid, 'native-42');
assert.equal(result.result.note, 'original user note');
assert.equal(context.app.userInteractionLevel, 'original');
process.stdout.write('Native wrapper early-return/UUID checks passed');
'''
    completed = subprocess.run([node, "-e", program, str(ROOT / "illona_mcp" / "host" / "ie3.jsx")],
                               capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    assert "early-return/UUID checks passed" in completed.stdout


def test_configuration_receipt_replay_restores_session_after_adapter_restart(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path)

        async def forbidden_native(*args, **kwargs):
            raise AssertionError("Workflow recovery must not execute Illustrator.")

        monkeypatch.setattr(bridge, "call", forbidden_native)
        args = {"workflow": "print", "operation_id": "durable-workflow"}
        original = IE3Integration(bridge)
        try:
            response_json(await original.invoke("set_workflow", args))
        finally:
            await original.close()
        restored = IE3Integration(bridge)
        try:
            replay = response_json(await restored.invoke("set_workflow", args))
            assert replay["coordinateSystem"] == "document"
            query = response_json(await restored.invoke("set_workflow", {}))
            assert query["currentWorkflow"] == "print"
            assert query["currentCoordinateSystem"] == "document"
            await restored.close()
            # A crashed/restarted adapter must receive the saved Node session,
            # rather than silently returning to its module-level defaults.
            query = response_json(await restored.invoke("set_workflow", {}))
            assert query["currentWorkflow"] == "print"
        finally:
            await restored.close()

    asyncio.run(check())
