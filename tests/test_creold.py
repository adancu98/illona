"""Verify fixed Creold catalog and execution contracts without Illustrator.

Vendor scripts are read only as data. Native execution and detached workers are
replaced in launcher tests, and the stdio catalog uses a nonexistent app path.
"""

import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from illona_mcp.bridge import BridgeError, IllonaBridge
from illona_mcp.creold import AUTOMATIC, CreoldIntegration


ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "illona_mcp" / "creold_runtime"
SOURCE = ROOT / "research" / "creold-illustrator-scripts"
COMMIT = "9b3e3eeade9ba748f41612ec4697bb6a5c2489c2"
CREOLD_TOOLS = {
    "illona_creold_catalog", "illona_creold_script_info",
    "illona_creold_run_script", "illona_creold_action",
}


def catalog_data():
    return json.loads((RUNTIME / "catalog.json").read_text())


def make_bridge(tmp_path):
    bridge = IllonaBridge(state_dir=tmp_path / "state", output_dir=tmp_path / "output")
    bridge.app_path = tmp_path / "Must never launch Illustrator.app"
    return bridge


def fake_target_calls(monkeypatch, bridge, *, path=None, documents=None):
    calls = []

    async def call(operation, params, operation_id=None):
        calls.append((operation,params,operation_id))
        if operation == "inspect_document":
            return {"id":params["document_id"],"path":path,"artboards":[]}
        if operation == "status":
            return {"documents":documents or []}
        if operation == "creold_script":
            return {"script_id":params["script_id"],"status":"script_returned",
                    "modification_verified":False,"messages":[],"operation_id":operation_id}
        raise AssertionError(f"Unexpected native operation: {operation}")

    monkeypatch.setattr(bridge,"call",call)
    return calls


def test_catalog_includes_every_loose_and_archived_original_exactly_once():
    catalog = catalog_data()
    loose = SOURCE / "jsx" if (SOURCE / "jsx").is_dir() else RUNTIME / "scripts"
    archives = SOURCE / "jsx" if (SOURCE / "jsx").is_dir() else RUNTIME / "archives"
    expected = {path.stem for path in loose.glob("*.jsx")}
    assert len(expected) == 99
    for archive in archives.glob("*.zip"):
        with ZipFile(archive) as source:
            expected.update(Path(name).stem for name in source.namelist() if name.endswith(".jsx"))
    scripts = catalog["scripts"]
    assert len(scripts) == 104
    assert len({script["script_id"] for script in scripts}) == 104
    assert {script["script_id"] for script in scripts} == expected
    assert catalog["upstream"]["commit"] == COMMIT
    assert catalog["upstream"]["script_count"] == 104
    assert catalog["upstream"]["archive_jsx_count"] == 5
    assert catalog["upstream"]["license"] == "MIT"


def test_catalog_hashes_match_packaged_bytes_and_the_pinned_original_sources():
    catalog = catalog_data()
    for entry in catalog["scripts"] + catalog["assets"]:
        packaged = (RUNTIME / entry["filename"]).resolve()
        assert packaged.is_relative_to(RUNTIME.resolve())
        assert not packaged.is_symlink()
        data = packaged.read_bytes()
        assert len(data) == entry["size_bytes"], entry["filename"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], entry["filename"]
        if not SOURCE.is_dir():
            continue  # Packaged bytes are always validated; checkout comparison is optional.
        origin = entry["source_path"]
        if "!/" in origin:
            archive, member = origin.split("!/", 1)
            with ZipFile(SOURCE / archive) as original:
                assert data == original.read(member), origin
        else:
            assert data == (SOURCE / origin).read_bytes(), origin


def test_offset_objects_keeps_its_required_style_asset_and_text_toggles_are_individual_ids():
    catalog = catalog_data()
    scripts = {entry["script_id"]: entry for entry in catalog["scripts"]}
    offset = scripts["OffsetObjects"]
    style = RUNTIME / Path(offset["filename"]).parent / "OffsetObjects_Style.ai"
    assert style.is_file()
    assert style.relative_to(RUNTIME).as_posix() in {asset["filename"] for asset in catalog["assets"]}
    assert {"ToggleTextBold", "ToggleTextItalic", "ToggleTextStrikethrough", "ToggleTextUnderline"} <= scripts.keys()
    assert all(entry["headless_validated"] is False for entry in scripts.values())


def test_original_catalog_declares_application_scopes_and_static_analysis_limits():
    catalog = catalog_data()
    scripts = {entry["script_id"]: entry for entry in catalog["scripts"]}
    for name in ("SaveAllDocs", "SyncGlobalColorsNames", "DocumentSwitcher", "BatchTrace", "Export-selection-as-AI", "OffsetObjects"):
        assert scripts[name]["global_scope"] is True, name
        assert scripts[name]["scope"] != "document", name
    for entry in scripts.values():
        assert entry["read_only"] is False
        assert entry["read_only_status"] == "not_asserted_for_original_script"
        assert entry["documentation_url"].startswith("https://github.com/creold/illustrator-scripts/blob/" + COMMIT + "/md/")
    assert "not a security proof" in catalog["analysis"]["limits"]


def test_stdio_exposes_four_fixed_creold_tools_with_no_arbitrary_script_input(tmp_path):
    async def check():
        env = {**os.environ, "ILLONA_STATE_DIR":str(tmp_path / "state"),
               "ILLONA_OUTPUT_DIR":str(tmp_path / "output"),
               "ILLONA_APP_PATH":str(tmp_path / "Must never launch Illustrator.app")}
        params = StdioServerParameters(command=str(ROOT / "run.sh"), cwd=str(ROOT), env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
        by_name = {tool.name:tool for tool in tools}
        assert len(tools) == len(by_name) == 86
        assert CREOLD_TOOLS <= by_name.keys()
        for name in CREOLD_TOOLS:
            properties = by_name[name].inputSchema.get("properties", {})
            assert not {"jsx", "code", "script", "script_path", "file_path", "jsx_path"} & properties.keys(), name
        launcher = by_name["illona_creold_run_script"].inputSchema
        assert {"document_id", "script_id"} <= set(launcher.get("required", []))
        assert set(launcher["properties"]["mode"]["enum"]) == {"interactive", "automatic"}
        actions = by_name["illona_creold_action"].inputSchema["properties"]["action"]["enum"]
        assert len(actions) == len(set(actions)) == 14
        assert not list((tmp_path / "state").rglob("request.jsx"))

    asyncio.run(check())


def record_job(bridge, operation_id, *, operation="creold:AlignTextBaseline", status="queued", native_steps=None, result=None):
    job = bridge._job(operation_id)
    job.mkdir(parents=True)
    metadata = {"operation":operation, "status":status, "created_at":0}
    if native_steps is not None:
        metadata["native_steps"] = native_steps
    (job / "request.json").write_text(json.dumps(metadata))
    if result is not None:
        (job / "result.json").write_text(json.dumps(result))
    return job


@pytest.mark.parametrize("status", ["queued", "waiting_for_user", "uncertain"])
def test_interactive_root_guard_blocks_new_native_mutations_before_dispatch(tmp_path, monkeypatch, status):
    bridge = make_bridge(tmp_path)
    bridge.app_path.mkdir()
    record_job(bridge, "original-interactive", status=status, native_steps=["original-child"])
    native_calls = []

    async def forbidden_native(*args, **kwargs):
        native_calls.append(args)
        raise AssertionError("A queued or open interactive script must retain its native guard.")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_native)
    monkeypatch.setattr(bridge, "_bundle", lambda *args: "// no native code in this test")
    with pytest.raises(BridgeError, match="(?i)(interactive|uncertain|pending|queued|operation)"):
        asyncio.run(bridge.call("create_document", {"width":100,"height":100}, "blocked-new-request"))
    assert native_calls == []
    assert not (bridge._job("blocked-new-request") / "request.jsx").exists()


def test_interactive_root_with_late_completed_native_step_is_recoverable(tmp_path):
    bridge = make_bridge(tmp_path)
    record_job(bridge, "root-interactive", status="uncertain", native_steps=["child-interactive"])
    record_job(bridge, "child-interactive", operation="creold_script", status="completed", result={
        "ok":True,"data":{"script_returned":True,"verified":False}})
    status = bridge.operation_status("root-interactive")
    assert status["status"] == "recoverable", status
    assert len(status["native_steps"]) == 1
    assert status["native_steps"][0]["status"] == "completed"
    assert status["native_steps"][0]["result"]["data"]["verified"] is False


def test_completed_interactive_failure_receipt_releases_guard_without_real_native_process(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path)
    bridge.app_path.mkdir()
    record_job(bridge, "failed-interactive", status="uncertain", result={
        "ok":False,"error":{"code":"SCRIPT_FAILED","message":"Known launcher failure"}})
    dispatches = []

    class NativeReceiptProcess:
        returncode = 0

        def __init__(self, job):
            self.job = job

        async def communicate(self):
            (self.job / "result.json").write_text(json.dumps({"ok":True,"data":{"id":"doc-fake"}}))
            return b"",b""

    async def fake_native(*args, **kwargs):
        assert args[0] == "/usr/bin/osascript"
        dispatches.append(args)
        return NativeReceiptProcess(Path(args[-1]).parent)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_native)
    monkeypatch.setattr(bridge, "_bundle", lambda *args: "// receipt-only mocked native operation")
    result = asyncio.run(bridge.call("create_document", {"width":100,"height":100}, "after-known-failure"))
    assert result["id"] == "doc-fake"
    assert len(dispatches) == 1
    assert bridge.operation_status("failed-interactive")["status"] == "completed"


def test_service_catalog_queries_and_info_do_not_dispatch_native_calls(tmp_path, monkeypatch):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    service = CreoldIntegration(bridge)
    all_scripts = service.list_scripts(limit=150)
    assert all_scripts["total"] == all_scripts["matched"] == len(all_scripts["scripts"]) == 104
    assert all_scripts["truncated"] is False
    matches = service.list_scripts(query="gradient",limit=2)
    assert matches["matched"] > len(matches["scripts"]) == 2
    assert matches["truncated"] is True
    text = service.list_scripts(category="text",limit=150)
    assert text["scripts"] and all(item["category"] == "Text" for item in text["scripts"])
    assert service.list_scripts(query="definitely-not-a-script")["scripts"] == []
    info = service.script_info("CycleGradientForward")
    assert info["automatic_original"] is True
    assert info["sha256"]
    assert "not verified" in info["result_contract"]
    assert calls == []
    assert not bridge.state_dir.exists()


@pytest.mark.parametrize("script_id", [
    "../SaveAllDocs", "/tmp/example.jsx", "CycleGradientForward.jsx",
    "app.activeDocument.close()", "CycleGradientForward\n", "not-a-catalog-id",
])
def test_only_exact_fixed_catalog_ids_are_accepted_before_native_dispatch(tmp_path,monkeypatch,script_id):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    service = CreoldIntegration(bridge)
    with pytest.raises(BridgeError,match="(?i)(fixed|script_id|catalog)"):
        service.script_info(script_id)
    with pytest.raises(BridgeError,match="(?i)(fixed|script_id|catalog)"):
        asyncio.run(service.run_script("doc-explicit",script_id,["native-1"],mode="automatic"))
    assert calls == []
    assert not (bridge.state_dir / "jobs").exists()


def test_automatic_originals_are_strictly_allowlisted_and_every_other_original_rejects_early(tmp_path,monkeypatch):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    service = CreoldIntegration(bridge)
    assert AUTOMATIC == {"CycleGradientBackward","CycleGradientForward","CycleGradientRandom",
                         "DistributeGradientStops","RemoveGradientStops"}
    for script_id,entry in service.scripts.items():
        if script_id in AUTOMATIC:
            assert not any(entry[key] for key in ("has_dialog","has_palette","prompts","confirms","alerts","file_writes"))
        else:
            with pytest.raises(BridgeError,match="interactive mode"):
                asyncio.run(service.run_script("doc-explicit",script_id,["native-1"],mode="automatic"))
    assert calls == []


@pytest.mark.parametrize("changes", [
    {"document_id":""}, {"mode":"untrusted"}, {"selection_mode":"wrong"},
    {"object_ids":[]}, {"object_ids":["same","same"]}, {"object_ids":[""]},
    {"object_ids":["x"*201]}, {"object_ids":[str(i) for i in range(501)]},
])
def test_invalid_targeting_is_rejected_before_inspecting_or_launching_a_script(tmp_path,monkeypatch,changes):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    service = CreoldIntegration(bridge)
    args={"document_id":"doc-explicit","script_id":"CycleGradientForward",
          "object_ids":["native-1"],"mode":"automatic",**changes}
    with pytest.raises(BridgeError):
        asyncio.run(service.run_script(**args))
    assert calls == []
    assert not (bridge.state_dir / "jobs").exists()


@pytest.mark.parametrize("tamper", ["bytes","symlink"])
def test_source_integrity_and_runtime_confinement_are_checked_before_native_dispatch(tmp_path,monkeypatch,tamper):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    runtime = tmp_path / "runtime"
    shutil.copytree(RUNTIME,runtime)
    target = runtime / "scripts" / "CycleGradientForward.jsx"
    if tamper == "bytes":
        target.write_bytes(target.read_bytes()+b"\n// unexpected package modification")
    else:
        outside = tmp_path / "outside-source.jsx"
        outside.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(outside)
    service = CreoldIntegration(bridge,runtime_dir=runtime)
    with pytest.raises(BridgeError,match="(?i)(integrity|escapes)"):
        asyncio.run(service.run_script("doc-explicit","CycleGradientForward",["native-1"],mode="automatic"))
    assert calls == []
    assert not (bridge.state_dir / "jobs").exists()


def test_automatic_execution_uses_fixed_staged_source_and_durable_unverified_result(tmp_path,monkeypatch):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    service = CreoldIntegration(bridge)
    result = asyncio.run(service.run_script("doc-explicit","CycleGradientForward",["native-1"],
                                           mode="automatic",operation_id="automatic-original"))
    assert result["status"] == "script_returned"
    assert result["modification_verified"] is False
    assert result["operation_id"] == "automatic-original"
    assert [op for op,_,_ in calls] == ["inspect_document","creold_script"]
    _,params,child = calls[-1]
    assert params["document_id"] == "doc-explicit" and params["object_ids"] == ["native-1"]
    assert params["mode"] == "automatic" and params["selection_mode"] == "replace"
    source = Path(params["script_path"])
    assert source.resolve().is_relative_to(bridge._job("automatic-original").resolve())
    assert source.name == "CycleGradientForward.jsx"
    assert source.read_text(encoding="utf-8-sig").startswith("(function(){")
    assert "var alert=function" in source.read_text(encoding="utf-8-sig")
    assert {"kind":"Boolean","key":"ShowExternalJSXWarning"} in params["preference_keys"]
    root = json.loads((bridge._job("automatic-original") / "request.json").read_text())
    assert root["native_steps"] == [child]
    assert bridge.operation_status("automatic-original")["status"] == "completed"
    replay = asyncio.run(service.run_script("doc-explicit","CycleGradientForward",["native-1"],
                                           mode="automatic",operation_id="automatic-original"))
    assert replay["replayed"] is True
    assert len(calls) == 2, "A completed original must replay without native re-execution."


@pytest.mark.parametrize("tamper", ["bytes", "symlink", "unlisted", "missing"])
def test_companion_assets_are_verified_before_staging_original(tmp_path, tamper):
    bridge = make_bridge(tmp_path)
    runtime = tmp_path / "runtime"
    shutil.copytree(RUNTIME, runtime)
    style = runtime / "scripts" / "OffsetObjects" / "OffsetObjects_Style.ai"
    if tamper == "bytes":
        style.write_bytes(style.read_bytes() + b"unexpected modification")
    elif tamper == "symlink":
        outside = tmp_path / "outside.ai"
        outside.write_bytes(style.read_bytes())
        style.unlink()
        style.symlink_to(outside)
    elif tamper == "missing":
        style.unlink()
    else:
        (style.parent / "unexpected.dat").write_bytes(b"unlisted dependency")
    service = CreoldIntegration(bridge, runtime_dir=runtime)
    job = bridge._job("bad-companion")
    job.mkdir(parents=True)
    with pytest.raises(BridgeError, match="companion asset integrity"):
        service._prepare(service.script_info("OffsetObjects"), job, "interactive")
def test_interactive_launcher_is_detached_and_retains_a_durable_parent_guard(tmp_path,monkeypatch):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    service = CreoldIntegration(bridge)
    launched=[]
    monkeypatch.setattr(service,"_launch_worker",lambda operation_id,job:launched.append((operation_id,job)) or 4321)
    result = asyncio.run(service.run_script("doc-explicit","AlignTextBaseline",["native-text"],
                                           mode="interactive",operation_id="interactive-original"))
    assert result["status"] == "queued"
    assert result["modification_verified"] is False
    assert [op for op,_,_ in calls] == ["inspect_document"]
    assert launched == [("interactive-original",bridge._job("interactive-original"))]
    job=bridge._job("interactive-original")
    metadata=json.loads((job/"request.json").read_text())
    assert metadata["operation"] == "creold:AlignTextBaseline"
    assert metadata["status"] == "queued" and metadata["worker_pid"] == 4321
    assert len(metadata["native_steps"]) == 1
    assert not (job/"result.json").exists()
    again = asyncio.run(service.run_script("doc-explicit","AlignTextBaseline",["native-text"],
                                          mode="interactive",operation_id="interactive-original"))
    assert again["status"] == "queued"
    assert len(launched) == 1 and len(calls) == 1


def test_worker_waits_for_launcher_lock_before_one_native_dispatch(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    from illona_mcp import creold_worker
    bridge=make_bridge(tmp_path)
    job=record_job(bridge,"worker-startup",native_steps=["worker-child"])
    meta=json.loads((job/"request.json").read_text())
    meta["native_params"]={"script_id":"ChangeOpacity"}
    (job/"request.json").write_text(json.dumps(meta))
    attempts=[];native=[]
    @asynccontextmanager
    async def transaction(root_operation=None):
        attempts.append(root_operation)
        if len(attempts)<3:
            raise BridgeError("Another Illona process is using Illustrator. Wait and try again.")
        yield
    async def call(operation,params,operation_id=None):
        native.append(operation)
        return {"status":"script_returned","modification_verified":False}
    async def no_delay(seconds):
        pass
    monkeypatch.setattr(bridge,"transaction",transaction)
    monkeypatch.setattr(bridge,"call",call)
    monkeypatch.setattr(creold_worker,"IllonaBridge",lambda:bridge)
    monkeypatch.setattr(creold_worker.asyncio,"sleep",no_delay)
    asyncio.run(creold_worker.execute("worker-startup"))
    assert attempts==["worker-startup"]*3
    assert native==["creold_script"]
    assert json.loads((job/"result.json").read_text())["ok"] is True


def test_application_scope_requires_explicit_opt_in_before_inspection(tmp_path,monkeypatch):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    service = CreoldIntegration(bridge)
    for script_id in ("SaveAllDocs","SyncGlobalColorsNames","DocumentSwitcher","BatchTrace","OffsetObjects"):
        with pytest.raises(BridgeError,match="application_scope"):
            asyncio.run(service.run_script("doc-explicit",script_id,mode="interactive"))
    assert calls == []


def test_application_scope_rejects_saved_documents_outside_output_before_launch(tmp_path,monkeypatch):
    bridge = make_bridge(tmp_path)
    outside=tmp_path/"existing-user-document.ai"
    outside.write_bytes(b"not an Illustrator document; only path checks run")
    calls = fake_target_calls(monkeypatch,bridge,documents=[{"id":"other-doc","path":str(outside)}])
    service = CreoldIntegration(bridge)
    launched=[]
    monkeypatch.setattr(service,"_launch_worker",lambda *args:launched.append(args) or 4321)
    with pytest.raises(BridgeError,match="inside"):
        asyncio.run(service.run_script("doc-explicit","SaveAllDocs",application_scope=True,
                                       operation_id="outside-document"))
    assert [op for op,_,_ in calls] == ["inspect_document","status"]
    assert launched == []
    assert not (bridge._job("outside-document")/"request.json").exists()


def test_a_second_interactive_launch_cannot_stage_another_guard_while_first_is_queued(tmp_path,monkeypatch):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    service = CreoldIntegration(bridge)
    launched=[]
    monkeypatch.setattr(service,"_launch_worker",lambda *args:launched.append(args) or 4321)
    asyncio.run(service.run_script("doc-explicit","AlignTextBaseline",["native-text"],operation_id="first-window"))
    with pytest.raises(BridgeError,match="(?i)(pending|queued|operation|interactive)"):
        asyncio.run(service.run_script("doc-explicit","ColorCorrector",["native-path"],operation_id="second-window"))
    assert len(launched) == 1
    assert len(calls) == 1, "Reject a second queued launcher before inspecting or staging another job."
    assert not (bridge._job("second-window")/"request.json").exists()


@pytest.mark.parametrize("native_ok", [True,False])
def test_same_interactive_request_recovers_completed_child_without_repeating_original(tmp_path,monkeypatch,native_ok):
    bridge = make_bridge(tmp_path)
    calls = fake_target_calls(monkeypatch,bridge)
    service = CreoldIntegration(bridge)
    launched=[]
    monkeypatch.setattr(service,"_launch_worker",lambda *args:launched.append(args) or 4321)
    args={"document_id":"doc-explicit","script_id":"AlignTextBaseline","object_ids":["native-text"],
          "operation_id":"late-child-receipt"}
    asyncio.run(service.run_script(**args))
    root=bridge._job(args["operation_id"])
    metadata=json.loads((root/"request.json").read_text())
    child=metadata["native_steps"][0]
    envelope={"ok":True,"data":{"script_id":"AlignTextBaseline","status":"script_returned","modification_verified":False}}
    if not native_ok:
        envelope={"ok":False,"error":{"code":"NATIVE_CREOLD_ERROR","message":"known original failure"}}
    record_job(bridge,child,operation="creold_script",status="completed",result=envelope)
    assert bridge.operation_status(args["operation_id"])["status"] == "recoverable"
    if native_ok:
        recovered=asyncio.run(service.run_script(**args))
        assert recovered["status"] == "script_returned"
        assert recovered["modification_verified"] is False
        assert recovered["replayed"] is True
    else:
        with pytest.raises(BridgeError,match="known original failure"):
            asyncio.run(service.run_script(**args))
    assert (root/"result.json").exists(), "Reconcile the parent receipt so its guard is actually released."
    status=bridge.operation_status(args["operation_id"])
    assert status["status"] == "completed"
    assert status["result"]["ok"] is native_ok
    assert len(calls) == len(launched) == 1


@pytest.mark.parametrize("success", [True,False])
def test_action_partial_native_failure_is_an_mcp_error_with_original_json_preserved(tmp_path,monkeypatch,success):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import CallToolResult,ToolAnnotations
    from illona_mcp.creold import register_creold

    bridge=make_bridge(tmp_path)
    payload={"success":success,"partial":not success,"changed_count":1,
             "errors":[] if success else [{"object_id":"native-path","message":"setter failed"}]}
    calls=[]

    async def fake_call(operation,params,operation_id=None):
        calls.append((operation,params,operation_id))
        return payload

    monkeypatch.setattr(bridge,"call",fake_call)
    server=FastMCP("Creold result contract test")
    annotations=ToolAnnotations()
    register_creold(server,bridge,annotations,annotations,annotations)
    result=asyncio.run(server.call_tool("illona_creold_action",{
        "document_id":"doc-explicit","action":"change_opacity","object_ids":["native-path"],
        "options":{"value":40},"operation_id":"action-result"}))
    assert isinstance(result,CallToolResult)
    assert result.isError is (not success)
    assert len(result.content)==1 and result.content[0].type=="text"
    assert json.loads(result.content[0].text)==payload
    assert len(calls)==1 and calls[0][0]=="creold_action"
