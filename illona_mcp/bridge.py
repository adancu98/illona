"""Serial, recoverable AppleScript/JSX execution without shell interpolation."""

import asyncio
import contextvars
from contextlib import asynccontextmanager
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

from .pdf_output import finish_pdf

PROJECT = Path(__file__).resolve().parent.parent
HOST = Path(__file__).resolve().parent / "host"
IE3_FILES = PROJECT / "integrations" / "ie3"
if not (IE3_FILES / "common.jsx").is_file():
    IE3_FILES = Path(__file__).resolve().parent / "ie3_runtime"
APP_PATH = "/Applications/Adobe Illustrator 2026/Adobe Illustrator.app"
OP_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
READ_ONLY = {"status", "inspect_document", "inspect_selection", "list_fonts", "plan_brochure", "preflight_document"}

# ExtendScript does not consistently expose JSON. This encoder supports the plain
# acyclic values returned by our own handlers and escapes all control characters.
ENCODER = r'''
function illonaStringify(v) {
    function q(s) {
        return '"' + String(s).replace(/[\\"\x00-\x1f\u2028\u2029]/g, function(c) {
            if (c == '"') return '\\"';
            if (c == '\\') return '\\\\';
            var h = c.charCodeAt(0).toString(16);
            return '\\u' + ('0000' + h).slice(-4);
        }) + '"';
    }
    if (v === null || typeof v == 'undefined') return 'null';
    if (typeof v == 'string') return q(v);
    if (typeof v == 'number') return isFinite(v) ? String(v) : 'null';
    if (typeof v == 'boolean') return String(v);
    var out = [], k;
    if (v instanceof Array) {
        for (k = 0; k < v.length; k++) out.push(illonaStringify(v[k]));
        return '[' + out.join(',') + ']';
    }
    for (k in v) if (v.hasOwnProperty(k) && typeof v[k] != 'function')
        out.push(q(k) + ':' + illonaStringify(v[k]));
    return '{' + out.join(',') + '}';
}
'''


class BridgeError(RuntimeError):
    pass


class IllonaBridge:
    def __init__(self, state_dir: Path | None = None, output_dir: Path | None = None):
        self.state_dir = Path(state_dir or os.getenv("ILLONA_STATE_DIR", PROJECT / ".illona-state")).resolve()
        self.output_dir = Path(output_dir or os.getenv("ILLONA_OUTPUT_DIR", PROJECT / "output")).resolve()
        self.app_path = Path(os.getenv("ILLONA_APP_PATH", APP_PATH))
        self.timeout = float(os.getenv("ILLONA_TIMEOUT_SECONDS", "45"))
        self.runner_path = HOST / "bridge.applescript"
        self._lock = asyncio.Lock()
        self._transaction_owner = contextvars.ContextVar("illona_transaction_owner", default=None)
        self._root_operation = contextvars.ContextVar("illona_root_operation", default=None)

    @asynccontextmanager
    async def transaction(self, root_operation: str | None = None):
        """Keep a multi-step tool exclusive, including across other MCP processes."""
        task = asyncio.current_task()
        if self._transaction_owner.get() is task:
            yield
            return
        async with self._lock:
            self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            with (self.state_dir / "host.lock").open("a+") as lock_file:
                try:
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise BridgeError("Another Illona process is using Illustrator. Wait and try again.") from exc
                owner = self._transaction_owner.set(task)
                root = self._root_operation.set(root_operation)
                try:
                    yield
                finally:
                    self._root_operation.reset(root)
                    self._transaction_owner.reset(owner)
                    fcntl.flock(lock_file, fcntl.LOCK_UN)

    def output_path(self, filename: str, extension: str | None = None) -> Path:
        requested = Path(filename).expanduser()
        path = (requested if requested.is_absolute() else self.output_dir / requested).resolve()
        if not path.is_relative_to(self.output_dir) or path == self.output_dir:
            raise BridgeError(f"Output must be inside {self.output_dir}")
        if extension and path.suffix.lower() != extension:
            raise BridgeError(f"Output filename must end with {extension}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def asset_path(self, filename: str) -> Path:
        requested = Path(filename).expanduser()
        path = (requested if requested.is_absolute() else self.output_dir / requested).resolve()
        if not path.is_relative_to(self.output_dir):
            raise BridgeError(f"Image assets must be inside {self.output_dir}")
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png"} or not path.is_file():
            raise BridgeError("Image asset must be an existing PNG or JPEG")
        if path.stat().st_size > 40 * 1024 * 1024:
            raise BridgeError("Image asset exceeds the 40 MB limit")
        return path

    def _job(self, operation_id: str) -> Path:
        if not OP_ID.fullmatch(operation_id):
            raise BridgeError("operation_id must contain only letters, digits, hyphens or underscores (1–100)")
        return self.state_dir / "jobs" / operation_id

    def operation_status(self, operation_id: str) -> dict:
        job = self._job(operation_id)
        if not (job / "request.json").exists():
            return {"operation_id": operation_id, "status": "unknown"}
        if (job / "result.json").exists():
            try:
                result = json.loads((job / "result.json").read_text(encoding="utf-8-sig"))
                if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                    raise ValueError("Invalid receipt envelope")
                if result.get("ok") and result.get("data", {}).get("requires_pdf_finalize"):
                    return {"operation_id": operation_id, "status": "finishing",
                            "message": "Native PDF was generated, but print geometry is not verified yet. Repeat the SAME request and operation_id to finish without re-running Illustrator."}
                return {"operation_id": operation_id, "status": "completed", "result": result}
            except (ValueError, OSError):
                pass  # A running host may still be writing its receipt.
        meta = json.loads((job / "request.json").read_text())
        status = meta.get("status", "pending")
        if (job / "result.json").exists():
            status = "uncertain"
        if meta.get("operation", "").startswith(("pro:", "creold:")) and meta.get("native_steps"):
            steps = [self.operation_status(step) for step in meta["native_steps"]]
            resumable = all(step["status"] in {"completed", "unknown", "not_started"} for step in steps)
            if meta["operation"].startswith("creold:"):
                resumable = all(step["status"] == "completed" for step in steps)
            return {"operation_id": operation_id, "status": "recoverable" if resumable else status,
                    "operation": meta["operation"], "native_steps": steps,
                    "message": "Resume the SAME advanced tool request and operation_id to replay recorded native steps without repeating them. Do not use a new ID." if resumable else "A native step may still be running. Wait for its receipt; do not repeat this mutation."}
        return {"operation_id": operation_id, "status": status,
                "operation": meta["operation"], "message": "Do not repeat a mutation until its outcome is reconciled."}

    def _bundle(self, operation: str, params: dict, receipt: Path) -> str:
        modules = ["core.jsx", "drawing.jsx", "layout.jsx", "production.jsx", "gradient_orientation.jsx", "creold.jsx", "creold_actions.jsx"]
        code = '\n'.join((HOST / name).read_text() for name in modules)
        if operation == "ie3_execute":
            helpers = IE3_FILES / "common.jsx"
            code += '\nIllona.ie3ExecuteScript = function(_illonaRequest) {\n' + helpers.read_text() + '\n' + (HOST / "ie3.jsx").read_text() + '\nreturn illonaRunIe3(_illonaRequest);\n};\n'
            code += '\nIllona.ops.ie3_execute = function(p) { return Illona.ie3ExecuteScript(p); };\n'
        args = json.dumps(params, ensure_ascii=True, allow_nan=False)
        # All paths and arguments are JSON literals, never shell or JSX fragments.
        bundle = ('#target illustrator\n#targetengine "illona_mcp"\n' + ENCODER + '\n' + code + '\n' +
                '(function(){\nvar r=Illona.run(' + json.dumps(operation) + ',' + args + ');\n' +
                'var s=illonaStringify(r);\nvar f=new File(' + json.dumps(str(receipt.with_suffix(".pending.json"))) + ');\n' +
                'f.encoding="UTF-8"; if(!f.open("w")) throw new Error("Cannot write Illona receipt");\n' +
                'f.write(s); f.close(); if(!f.rename("result.json")) throw new Error("Cannot commit Illona receipt"); return s;\n})();\n')
        # Illustrator may interpret an unmarked .jsx using the system legacy
        # encoding. ASCII source with JSON Unicode escapes is unambiguous even
        # for literals in our shipped modules, including surrogate pairs.
        return re.sub(r"[^\x00-\x7f]", lambda m: json.dumps(m.group(0), ensure_ascii=True)[1:-1], bundle)

    async def call(self, operation: str, params: dict, operation_id: str | None = None) -> dict:
        operation_id = operation_id or uuid.uuid4().hex
        job = self._job(operation_id)
        digest = hashlib.sha256(json.dumps([operation, params], sort_keys=True, allow_nan=False).encode()).hexdigest()
        async with self.transaction():
            return await self._execute(operation, params, operation_id, job, digest)

    async def _execute(self, operation: str, params: dict, operation_id: str, job: Path, digest: str) -> dict:
        request_file = job / "request.json"
        if request_file.exists():
            request = json.loads(request_file.read_text())
            if request["digest"] != digest:
                raise BridgeError("This operation_id belongs to a different request")
            status = self.operation_status(operation_id)
            if status["status"] == "completed":
                return self._unwrap(status["result"], operation_id, replayed=True)
            if status["status"] == "finishing":
                envelope = json.loads((job / "result.json").read_text(encoding="utf-8-sig"))
                envelope = self._finish_receipt(envelope, job / "result.json")
                request["status"] = "completed"
                request_file.write_text(json.dumps(request))
                return self._unwrap(envelope, operation_id, replayed=True)
            raise BridgeError(f"Operation {operation_id} is {status['status']}; inspect operation status before retrying")
        # An ambiguous previous operation can still be executing after osascript exits.
        for prior in (self.state_dir / "jobs").glob("*/request.json"):
            if prior.parent.name == self._root_operation.get():
                continue
            meta = json.loads(prior.read_text())
            if operation not in READ_ONLY and meta.get("operation") not in READ_ONLY and meta.get("status") in ("pending", "uncertain", "queued", "waiting_for_user") and self.operation_status(prior.parent.name)["status"] != "completed":
                raise BridgeError(f"Operation {prior.parent.name} has an uncertain outcome. Inspect it before more Illustrator calls.")
        if not self.app_path.is_dir():
            raise BridgeError(f"Illustrator was not found at {self.app_path}")
        job.mkdir(parents=True, mode=0o700)
        receipt = job / "result.json"
        script = job / "request.jsx"
        script.write_text(self._bundle(operation, params, receipt), encoding="ascii")
        meta = {"operation": operation, "digest": digest, "created_at": time.time(), "status": "pending"}
        request_file.write_text(json.dumps(meta), encoding="utf-8")
        try:
            proc = await asyncio.create_subprocess_exec(
                "/usr/bin/osascript", str(self.runner_path), str(self.app_path), str(script),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except OSError:
            meta["status"] = "not_started"
            request_file.write_text(json.dumps(meta))
            raise
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            if proc.returncode is None:
                proc.kill()
            try:
                await asyncio.wait_for(proc.communicate(), timeout=3)
            except asyncio.TimeoutError:
                pass
            meta["status"] = "uncertain"
            request_file.write_text(json.dumps(meta))
            raise BridgeError(f"Operation {operation_id} did not finish in time. Illustrator may still finish it. Use illona_operation_status; do not repeat it.") from exc
        if receipt.exists():
            try:
                envelope = json.loads(receipt.read_text(encoding="utf-8-sig"))
            except (ValueError, OSError) as exc:
                meta["status"] = "uncertain"
                request_file.write_text(json.dumps(meta))
                raise BridgeError(f"Invalid host receipt for {operation_id}; do not repeat the operation") from exc
            meta["status"] = "completed"
            envelope = self._finish_receipt(envelope, receipt)
            request_file.write_text(json.dumps(meta))
            return self._unwrap(envelope, operation_id)
        detail = stderr.decode(errors="replace").strip()[-1500:]
        # Compilation/authorization failures cannot have entered our host handlers.
        definite = ": script error:" in detail or any(code in detail for code in ("(-1743)", "(-2740)", "(-2741)", "(-2746)"))
        meta["status"] = "not_started" if definite else "uncertain"
        request_file.write_text(json.dumps(meta))
        raise BridgeError(f"Illustrator call failed ({operation_id}): {detail or stdout.decode(errors='replace')[-1000:]}")

    def _finish_receipt(self, envelope: dict, receipt: Path) -> dict:
        data = envelope.get("data", {})
        if not envelope.get("ok") or not data.get("requires_pdf_finalize"):
            return envelope
        path = self.output_path(data["path"], ".pdf")
        try:
            verified = finish_pdf(path, data["trim_width_pt"], data["trim_height_pt"], data["bleed_pt"])
        except Exception as exc:
            raise BridgeError(f"PDF geometry is not verified: {exc}. Resume this same request/operation_id; Illustrator will not be run again.") from exc
        data.update(verified)
        data.pop("requires_pdf_finalize", None)
        staged = receipt.with_suffix(".finalizing.json")
        staged.write_text(json.dumps(envelope, ensure_ascii=True), encoding="utf-8")
        os.replace(staged, receipt)
        return envelope

    @staticmethod
    def _unwrap(envelope: dict, operation_id: str, replayed: bool = False) -> dict:
        if not envelope.get("ok"):
            error = envelope.get("error", {})
            raise BridgeError(f"{error.get('code', 'ILLUSTRATOR_ERROR')}: {error.get('message', error)} [operation {operation_id}]")
        result = envelope.get("data")
        if not isinstance(result, dict):
            result = {"value": result}
        return {**result, "operation_id": operation_id, "replayed": replayed}

