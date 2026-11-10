"""Exercise confinement and ambiguous-result recovery without launching Illustrator."""

import asyncio
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from illona_mcp.bridge import BridgeError, ENCODER, IllonaBridge


@pytest.fixture
def bridge(tmp_path):
    result = IllonaBridge(state_dir=tmp_path / "state", output_dir=tmp_path / "output")
    result.app_path = tmp_path / "Illustrator.app"
    result.app_path.mkdir()
    return result


def record(bridge, operation_id, operation="create_document", params=None, status="pending", result=None):
    params = {} if params is None else params
    job = bridge._job(operation_id)
    job.mkdir(parents=True)
    digest = hashlib.sha256(json.dumps([operation, params], sort_keys=True, allow_nan=False).encode()).hexdigest()
    (job / "request.json").write_text(json.dumps({"operation": operation, "digest": digest, "status": status}))
    if result is not None:
        (job / "result.json").write_text(json.dumps(result))
    return job


def node():
    candidate = shutil.which("node") or str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")
    if not Path(candidate).is_file():
        pytest.skip("Node is unavailable for the independent ES3-host encoder check")
    return candidate


def test_output_path_confines_traversal_absolute_paths_and_symlink_targets(bridge, tmp_path):
    bridge.output_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (bridge.output_dir / "escape").symlink_to(outside, target_is_directory=True)
    for filename in ("../outside/x.ai", str(outside / "x.ai"), "escape/x.ai", "."):
        with pytest.raises(BridgeError):
            bridge.output_path(filename)
    assert list(outside.iterdir()) == []
    safe = bridge.output_path("nested/ready.PNG", ".png")
    assert safe == bridge.output_dir / "nested/ready.PNG"
    assert safe.parent.is_dir()
    with pytest.raises(BridgeError):
        bridge.output_path("wrong.jpg", ".png")


def test_operation_ids_cannot_escape_state_directory(bridge):
    for operation_id in ("../escape", "a/b", "", "a" * 101, "white space", "foo\n"):
        with pytest.raises(BridgeError):
            bridge.operation_status(operation_id)


def test_completed_receipt_replays_without_subprocess_even_when_metadata_uncertain(bridge, monkeypatch):
    record(bridge, "same-id", status="uncertain", result={"ok": True, "data": {"id": "doc-1"}})
    spawn = AsyncMock(side_effect=AssertionError("a replay must not execute Illustrator"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    result = asyncio.run(bridge.call("create_document", {}, "same-id"))
    assert result == {"id": "doc-1", "operation_id": "same-id", "replayed": True}
    spawn.assert_not_called()
    assert bridge.operation_status("same-id")["status"] == "completed"


def test_changed_payload_with_same_operation_id_is_rejected(bridge, monkeypatch):
    record(bridge, "same-id", params={"width": 210}, result={"ok": True, "data": {}})
    spawn = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(BridgeError, match="different request"):
        asyncio.run(bridge.call("create_document", {"width": 297}, "same-id"))
    spawn.assert_not_called()


def test_uncertain_operation_blocks_new_mutations_but_receipt_can_be_recovered(bridge, monkeypatch):
    job = record(bridge, "uncertain-one", status="uncertain")
    spawn = AsyncMock()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(BridgeError, match="uncertain outcome"):
        asyncio.run(bridge.call("create_document", {}, "new-one"))
    assert not bridge._job("new-one").exists()
    spawn.assert_not_called()
    (job / "result.json").write_text(json.dumps({"ok": True, "data": {"id": "later"}}))
    result = asyncio.run(bridge.call("create_document", {}, "uncertain-one"))
    assert result["id"] == "later" and result["replayed"] is True


def test_partially_written_receipt_does_not_unblock_mutations(bridge, monkeypatch):
    job = record(bridge, "still-writing", status="uncertain")
    (job / "result.json").write_text('{"ok":')
    assert bridge.operation_status("still-writing")["status"] == "uncertain"
    monkeypatch.setattr(bridge, "_bundle", lambda *args: "// must never execute")
    spawn = AsyncMock(side_effect=AssertionError("an incomplete receipt must keep the queue blocked"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(BridgeError, match="uncertain outcome"):
        asyncio.run(bridge.call("create_document", {}, "blocked-new-operation"))
    spawn.assert_not_called()


def test_es3_encoder_round_trips_quotes_backslashes_controls_and_unicode():
    payload = {"quote\"and\\key": "\"\\" + "".join(map(chr, range(32))) + "\u2028\u2029România 😊", "array": [1, True, None, {"x": "y"}]}
    source = ENCODER + "\nprocess.stdout.write(illonaStringify(JSON.parse(process.argv[1])));"
    completed = subprocess.run([node(), "-e", source, json.dumps(payload, ensure_ascii=True)], text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout) == payload
    assert completed.stderr == ""


def test_receipt_wins_over_subprocess_exit_and_no_stdout_is_printed(bridge, monkeypatch, capsys):
    monkeypatch.setattr(bridge, "_bundle", lambda *args: "// a bounded host job")

    class Process:
        returncode = 1

        async def communicate(self):
            job = bridge._job("receipt-id")
            (job / "result.json").write_text(json.dumps({"ok": True, "data": {"created": 3}}))
            return b"unrelated native stdout", b"native error after completed receipt"

    spawn = AsyncMock(return_value=Process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    result = asyncio.run(bridge.call("create_elements", {"text": "`$(shell)\"\\"}, "receipt-id"))
    assert result["created"] == 3 and result["replayed"] is False
    assert bridge.operation_status("receipt-id")["status"] == "completed"
    assert spawn.await_args.args[0] == "/usr/bin/osascript"
    assert "shell" not in spawn.await_args.kwargs
    assert capsys.readouterr().out == ""


def test_timeout_is_uncertain_and_same_operation_cannot_be_executed_again(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "_bundle", lambda *args: "// bounded host job")
    bridge.timeout = 0.001

    class Process:
        returncode = None

        async def communicate(self):
            if self.returncode is None:
                await asyncio.sleep(1)
            return b"", b""

        def kill(self):
            self.returncode = -9

    spawn = AsyncMock(return_value=Process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(BridgeError, match="may still finish"):
        asyncio.run(bridge.call("create_document", {}, "timeout-id"))
    assert bridge.operation_status("timeout-id")["status"] == "uncertain"
    with pytest.raises(BridgeError, match="inspect operation status"):
        asyncio.run(bridge.call("create_document", {}, "timeout-id"))
    spawn.assert_awaited_once()


def test_host_core_mock_checks_run_without_illustrator():
    script = Path(__file__).with_name("host_core_test.cjs")
    completed = subprocess.run([node(), str(script)], text=True, capture_output=True, check=True)
    assert "Host mock checks passed" in completed.stdout
    assert completed.stderr == ""
