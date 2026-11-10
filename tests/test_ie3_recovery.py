"""Exercise root/native receipt recovery and exported bytes without Illustrator.

Real bundled upstream handlers run in Node. Only the osascript subprocess is
replaced: no test can launch, save, close, or edit an Illustrator document.
"""

import asyncio
import json
from pathlib import Path

import pytest
from mcp.types import CallToolResult, TextContent
from pypdf import PdfWriter
from pypdf.errors import PdfReadError

from illona_mcp.bridge import BridgeError, IllonaBridge
from illona_mcp.ie3 import IE3Integration


def make_bridge(tmp_path, *, installed=False):
    bridge = IllonaBridge(state_dir=tmp_path / "state", output_dir=tmp_path / "output")
    bridge.app_path = tmp_path / "Fake Illustrator.app"
    if installed:
        bridge.app_path.mkdir()
    return bridge


def text_result(result):
    return "\n".join(item.text for item in result.content if item.type == "text")


def first_json(result):
    for item in result.content:
        if item.type == "text":
            try:
                return json.loads(item.text)
            except ValueError:
                pass
    raise AssertionError("Expected a JSON text response")


def rectangle_args(operation_id):
    return {"document_id": "doc-test-explicit", "operation_id": operation_id,
            "coordinate_system": "artboard-web", "x": 10, "y": 20, "width": 60, "height": 40}


def completed_error(status):
    assert status["status"] == "completed", status
    saved = status["result"]["data"]["upstream_result"]
    assert saved["isError"] is True
    return saved


def test_missing_illustrator_is_committed_as_known_root_failure_and_does_not_poison_queue(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path)
        actual_spawn = asyncio.create_subprocess_exec
        native_dispatches = []

        async def spawn(*args, **kwargs):
            if args[0] == "/usr/bin/osascript":
                native_dispatches.append(args)
                raise AssertionError("A nonexistent Illustrator installation cannot be launched.")
            return await actual_spawn(*args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        integration = IE3Integration(bridge)
        args = rectangle_args("missing-app-root")
        try:
            result = await integration.invoke("create_rectangle", args)
            assert result.isError
            assert "Illustrator was not found" in text_result(result)
            assert first_json(result)["outcome"] == "known_failure"
            completed_error(bridge.operation_status("missing-app-root"))
            assert native_dispatches == []

            async def forbidden_restart():
                raise AssertionError("A completed error receipt must replay without invoking Node or Illustrator.")

            monkeypatch.setattr(integration, "_start", forbidden_restart)
            replayed = await integration.invoke("create_rectangle", args)
            assert replayed.model_dump() == result.model_dump()
            # The installation error remains, but there must be no spurious
            # uncertain-outcome block left by the failed advanced request.
            with pytest.raises(BridgeError, match="Illustrator was not found"):
                await bridge.call("create_document", {"width": 100, "height": 100}, "later-request")
        finally:
            await integration.close()

    asyncio.run(check())


def test_completed_native_error_receipt_does_not_permanently_block_later_requests(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path, installed=True)
        actual_spawn = asyncio.create_subprocess_exec
        native_jobs = []

        class NativeErrorProcess:
            returncode = 1

            def __init__(self, job):
                self.job = job

            async def communicate(self):
                (self.job / "result.json").write_text(json.dumps({"ok": False, "error": {
                    "code": "DOCUMENT_CLOSED", "message": "The requested document has closed."}}))
                return b"", b"error after native failure receipt"

        async def spawn(*args, **kwargs):
            if args[0] == "/usr/bin/osascript":
                job = Path(args[-1]).parent
                native_jobs.append(job)
                return NativeErrorProcess(job)
            return await actual_spawn(*args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        integration = IE3Integration(bridge)
        try:
            for root_id in ("closed-document-one", "closed-document-two"):
                result = await integration.invoke("create_rectangle", rectangle_args(root_id))
                assert result.isError
                assert "DOCUMENT_CLOSED" in text_result(result)
                completed_error(bridge.operation_status(root_id))
            assert len(native_jobs) == 2, "The first known failure must not block a later independent request."
            for job in native_jobs:
                assert bridge.operation_status(job.name)["status"] == "completed"
        finally:
            await integration.close()

    asyncio.run(check())


def test_uncertain_native_step_resumes_from_late_receipt_without_reapplying_mutation(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path, installed=True)
        bridge.timeout = 0.005
        actual_spawn = asyncio.create_subprocess_exec
        native_jobs = []

        class TimedOutNativeProcess:
            returncode = None

            async def communicate(self):
                if self.returncode is None:
                    await asyncio.sleep(1)
                return b"", b""

            def kill(self):
                self.returncode = -9

        async def spawn(*args, **kwargs):
            if args[0] == "/usr/bin/osascript":
                native_jobs.append(Path(args[-1]).parent)
                return TimedOutNativeProcess()
            return await actual_spawn(*args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        integration = IE3Integration(bridge)
        args = rectangle_args("late-native-root")
        try:
            with pytest.raises(BridgeError, match="uncertain|may still finish|did not finish"):
                await integration.invoke("create_rectangle", args)
            assert len(native_jobs) == 1
            native_job = native_jobs[0]
            assert bridge.operation_status(native_job.name)["status"] == "uncertain"
            assert bridge.operation_status("late-native-root")["status"] == "uncertain"

            with pytest.raises(BridgeError, match="uncertain"):
                await integration.invoke("create_rectangle", args)
            assert len(native_jobs) == 1, "An unresolved native step must never be dispatched again."
            with pytest.raises(BridgeError, match="uncertain outcome"):
                await bridge.call("create_document", {"width": 100, "height": 100}, "blocked-independent-write")
            assert len(native_jobs) == 1

            # Illustrator may finish after the osascript timeout. Only the
            # receipt is added; the mutation is not rerun to discover its result.
            (native_job / "result.json").write_text(json.dumps({"ok": True, "data": {"result": {
                "uuid": "native-completed-late", "verified": {"uuid": "native-completed-late"}}}}))
            assert bridge.operation_status(native_job.name)["status"] == "completed"
            assert bridge.operation_status("late-native-root")["status"] == "recoverable"
            result = await integration.invoke("create_rectangle", args)
            assert not result.isError, text_result(result)
            assert first_json(result)["uuid"] == "native-completed-late"
            assert bridge.operation_status("late-native-root")["status"] == "completed"
            assert len(native_jobs) == 1
            replayed = await integration.invoke("create_rectangle", args)
            assert replayed.model_dump() == result.model_dump()
            assert len(native_jobs) == 1
        finally:
            await integration.close()

    asyncio.run(check())


def test_root_transaction_is_reentrant_for_its_native_steps_and_exclusive_across_instances(tmp_path):
    async def check():
        first = make_bridge(tmp_path)
        second = make_bridge(tmp_path)
        async with first.transaction(root_operation="multi-step-root"):
            async with first.transaction():
                assert first._root_operation.get() == "multi-step-root"
            with pytest.raises(BridgeError, match="Another Illona process"):
                async with second.transaction(root_operation="other-root"):
                    raise AssertionError("Another transaction cannot enter while the root owns the native lock.")
        async with second.transaction(root_operation="other-root"):
            assert second._root_operation.get() == "other-root"

    asyncio.run(check())


def test_pending_root_resumes_after_completed_child_receipt_without_second_native_dispatch(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path, installed=True)
        actual_spawn = asyncio.create_subprocess_exec
        native_jobs = []

        class CompletedNativeProcess:
            returncode = 0

            def __init__(self, job):
                self.job = job

            async def communicate(self):
                (self.job / "result.json").write_text(json.dumps({"ok": True, "data": {"result": {
                    "uuid": "already-created-native-item", "verified": {"uuid": "already-created-native-item"}}}}))
                return b"", b""

        async def spawn(*args, **kwargs):
            if args[0] == "/usr/bin/osascript":
                job = Path(args[-1]).parent
                native_jobs.append(job)
                return CompletedNativeProcess(job)
            return await actual_spawn(*args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        args = rectangle_args("interrupted-root-commit")
        integration = IE3Integration(bridge)
        try:
            original = await integration.invoke("create_rectangle", args)
            assert not original.isError
        finally:
            await integration.close()
        assert len(native_jobs) == 1
        assert bridge.operation_status(native_jobs[0].name)["status"] == "completed"
        # Model a parent crash after the durable child receipt, but before its
        # final response was committed. Recovery must consume the child receipt.
        root_job = bridge._job(args["operation_id"])
        (root_job / "result.json").unlink()
        request = json.loads((root_job / "request.json").read_text())
        request["status"] = "pending"
        (root_job / "request.json").write_text(json.dumps(request))
        assert bridge.operation_status(args["operation_id"])["status"] == "recoverable"
        restarted = IE3Integration(bridge)
        try:
            recovered = await restarted.invoke("create_rectangle", args)
            assert recovered.model_dump() == original.model_dump()
            assert bridge.operation_status(args["operation_id"])["status"] == "completed"
            assert len(native_jobs) == 1
        finally:
            await restarted.close()

    asyncio.run(check())


@pytest.mark.parametrize("file_state", ["missing", "truncated"])
def test_output_validation_failure_is_committed_without_repeating_export_or_poisoning_queue(tmp_path, monkeypatch, file_state):
    async def check():
        bridge = make_bridge(tmp_path, installed=True)
        path = bridge.output_path("invalid-output.pdf")
        actual_spawn = asyncio.create_subprocess_exec
        native_dispatches = []

        class ExportedProcess:
            returncode = 0

            def __init__(self, job):
                self.job = job

            async def communicate(self):
                if file_state == "truncated":
                    path.write_bytes(b"%PDF-1.7\ntruncated output without trailer or pages")
                (self.job / "result.json").write_text(json.dumps({"ok": True, "data": {"result": {
                    "success": True, "output_path": str(path)}}}))
                return b"", b""

        async def spawn(*args, **kwargs):
            if args[0] == "/usr/bin/osascript":
                native_dispatches.append(args)
                return ExportedProcess(Path(args[-1]).parent)
            return await actual_spawn(*args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        integration = IE3Integration(bridge)
        args = {"document_id": "doc-explicit", "output_path": str(path), "operation_id": "invalid-export-root"}
        try:
            failed = await integration.invoke("export_pdf", args)
            assert failed.isError
            completed_error(bridge.operation_status("invalid-export-root"))
            assert len(native_dispatches) == 1
            replayed = await integration.invoke("export_pdf", args)
            assert replayed.model_dump() == failed.model_dump()
            assert len(native_dispatches) == 1, "Verification errors must never repeat an export."
            configured = await integration.invoke("set_workflow", {"workflow": "web"})
            assert not configured.isError
        finally:
            await integration.close()

    asyncio.run(check())


def test_omitted_print_coordinates_recover_in_fresh_process_from_saved_session(tmp_path, monkeypatch):
    async def check():
        bridge = make_bridge(tmp_path, installed=True)
        bridge.timeout = 0.005
        actual_spawn = asyncio.create_subprocess_exec
        native_jobs = []
        mode = {"timeout": True}

        class TimeoutProcess:
            returncode = None

            async def communicate(self):
                if self.returncode is None:
                    await asyncio.sleep(1)
                return b"", b""

            def kill(self):
                self.returncode = -9

        class CompletedProcess:
            returncode = 0

            def __init__(self, job):
                self.job = job

            async def communicate(self):
                (self.job / "result.json").write_text(json.dumps({"ok": True, "data": {"result": {
                    "uuid": "new-after-recovery", "verified": {"uuid": "new-after-recovery"}}}}))
                return b"", b""

        async def spawn(*args, **kwargs):
            if args[0] == "/usr/bin/osascript":
                job = Path(args[-1]).parent
                native_jobs.append(job)
                return TimeoutProcess() if mode["timeout"] else CompletedProcess(job)
            return await actual_spawn(*args, **kwargs)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        args = rectangle_args("omitted-print-coordinates")
        del args["coordinate_system"]
        original = IE3Integration(bridge)
        try:
            configured = await original.invoke("set_workflow", {"workflow": "print"})
            assert not configured.isError
            with pytest.raises(BridgeError):
                await original.invoke("create_rectangle", args)
        finally:
            await original.close()
        assert len(native_jobs) == 1
        meta = json.loads((bridge._job(args["operation_id"]) / "request.json").read_text())
        assert meta["prepared_params"]["coordinate_system"] == "document"
        assert meta["session"]["workflow"] == "print"
        (native_jobs[0] / "result.json").write_text(json.dumps({"ok": True, "data": {"result": {
            "uuid": "completed-in-print-coordinates", "coordinateSystem": "document"}}}))

        # A new bridge/integration simulates the Python MCP process restarting;
        # its local defaults begin in artboard-web and must not alter the replay.
        fresh_bridge = make_bridge(tmp_path)
        fresh_bridge.timeout = 0.005
        restarted = IE3Integration(fresh_bridge)
        mode["timeout"] = False
        try:
            recovered = await restarted.invoke("create_rectangle", args)
            assert not recovered.isError, text_result(recovered)
            assert first_json(recovered)["coordinateSystem"] == "document"
            assert len(native_jobs) == 1, "Saved print-coordinate steps must replay rather than dispatch under new defaults."
            current = first_json(await restarted.invoke("set_workflow", {}))
            assert current["currentWorkflow"] == "print"
            assert current["currentCoordinateSystem"] == "document"

            next_args = rectangle_args("after-print-recovery")
            del next_args["coordinate_system"]
            following = await restarted.invoke("create_rectangle", next_args)
            assert not following.isError
            next_meta = json.loads((fresh_bridge._job(next_args["operation_id"]) / "request.json").read_text())
            assert next_meta["prepared_params"]["coordinate_system"] == "document", "Python and Node session defaults must agree after recovery."
            assert len(native_jobs) == 2
        finally:
            await restarted.close()

    asyncio.run(check())


def output_result(payload=None):
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload or {"success": True}))])


@pytest.mark.parametrize("filename,data,message", [
    ("missing.png", None, "not produced"),
    ("empty.png", b"", "not produced"),
    ("wrong.png", b"this is not a PNG", "PNG"),
    ("wrong.jpg", b"this is not a JPEG", "JPEG"),
    ("wrong.pdf", b"this is not a PDF", "PDF/AI"),
    ("wrong.ai", b"this is not an AI document", "PDF/AI"),
])
def test_output_verification_rejects_missing_empty_or_wrong_format_files(tmp_path, filename, data, message):
    bridge = make_bridge(tmp_path)
    integration = IE3Integration(bridge)
    path = bridge.output_path(filename)
    if data is not None:
        path.write_bytes(data)
    tool = "export_pdf" if path.suffix == ".pdf" else "save_document" if path.suffix == ".ai" else "export"
    params = {"path": str(path), "mode": "save_as"} if tool == "save_document" else {"output_path": str(path), "target": "artboard:0"}
    with pytest.raises(BridgeError, match=message):
        integration._verify_outputs(tool, params, output_result({"success": True, "output_path": str(path)}))


def test_readable_pdf_returns_actual_geometry_without_claiming_physical_bleed_or_pdfx(tmp_path):
    bridge = make_bridge(tmp_path)
    integration = IE3Integration(bridge)
    path = bridge.output_path("readable.pdf")
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=500)
    writer.write(path)
    result = output_result()
    integration._verify_outputs("export_pdf", {"output_path": str(path)}, result)
    verification = json.loads(result.content[-1].text)["pdf_verification"]
    assert verification["readable"] is True
    assert verification["page_count"] == 1
    assert verification["geometry"][0]["media_pt"] == [0, 0, 300, 500]
    assert verification["physical_bleed_verified"] is False
    assert verification["pdfx_certified"] is False


def test_batch_output_verification_rejects_foreign_paths_and_empty_file_lists(tmp_path):
    bridge = make_bridge(tmp_path)
    integration = IE3Integration(bridge)
    params = {"target": "artboard:all", "output_path": str(bridge.output_path("all.png"))}
    with pytest.raises(BridgeError, match="inside"):
        integration._verify_outputs("export", params, output_result({"success": True, "files": [{"output_path": str(tmp_path / "foreign.png")}]}))
    with pytest.raises(BridgeError, match="did not return any output"):
        integration._verify_outputs("export", params, output_result({"success": True, "files": []}))


def test_truncated_pdf_with_valid_magic_is_rejected_by_readability_check(tmp_path):
    bridge = make_bridge(tmp_path)
    integration = IE3Integration(bridge)
    path = bridge.output_path("truncated.pdf")
    path.write_bytes(b"%PDF-1.7\ntruncated bytes, no trailer or pages")
    with pytest.raises((BridgeError, PdfReadError)):
        integration._verify_outputs("export_pdf", {"output_path": str(path)}, output_result())
