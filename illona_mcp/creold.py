"""Pinned Creold originals plus guarded selection-based adaptations for Illona."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .bridge import READ_ONLY, BridgeError, IllonaBridge

RUNTIME = Path(__file__).resolve().parent / "creold_runtime"
AUTOMATIC = {"CycleGradientBackward", "CycleGradientForward", "CycleGradientRandom", "DistributeGradientStops", "RemoveGradientStops"}


class CreoldIntegration:
    def __init__(self, bridge: IllonaBridge, runtime_dir: Path | None = None):
        self.bridge = bridge
        self.runtime = Path(runtime_dir or RUNTIME).resolve()
        self.catalog = json.loads((self.runtime / "catalog.json").read_text())
        self.scripts = {s["script_id"]: s for s in self.catalog["scripts"]}

    def list_scripts(self, query="", category=None, limit=150):
        found = [s for s in self.scripts.values() if (not category or s["category"].lower() == category.lower())
            and query.lower() in (s["script_id"] + " " + s["description"]).lower()]
        return {"upstream": self.catalog["upstream"], "total": len(self.scripts), "matched": len(found),
            "scripts": [{"script_id":s["script_id"],"title":s["title"],"category":s["category"],
                "has_dialog":s["has_dialog"],"scope":s["scope"],"automatic_original":s["script_id"] in AUTOMATIC,
                "description":s["description"]} for s in found[:limit]],"truncated":len(found)>limit}

    def script_info(self, script_id):
        if script_id not in self.scripts:
            raise BridgeError("Unknown fixed Creold script_id. Use illona_creold_catalog; file paths and JSX are not accepted.")
        entry = dict(self.scripts[script_id])
        entry["automatic_original"] = script_id in AUTOMATIC
        entry["result_contract"] = "script_returned is not verified modification; original scripts may catch their own errors."
        return entry

    def _source(self, entry):
        path = (self.runtime / entry["filename"]).resolve()
        if not path.is_relative_to(self.runtime) or not path.is_file():
            raise BridgeError("Creold source is missing or escapes the packaged runtime")
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise BridgeError("Creold source integrity check failed; restore the pinned library")
        return path, data.decode(entry.get("source_encoding", "utf-8")).lstrip("\ufeff")

    def _prepare(self, entry, job, mode):
        source_path, source = self._source(entry)
        payload = job / "original";payload.mkdir(parents=True, exist_ok=True)
        companions = {a["filename"]:a for a in self.catalog.get("assets", [])
            if Path(a["filename"]).parent == Path(entry["filename"]).parent}
        for asset in companions.values():
            asset_path = (self.runtime / asset["filename"]).resolve()
            if (not asset_path.is_relative_to(self.runtime) or not asset_path.is_file()
                or hashlib.sha256(asset_path.read_bytes()).hexdigest() != asset["sha256"]):
                raise BridgeError("Creold companion asset integrity check failed")
        # Preserve sibling dependencies and original filename semantics ($.fileName).
        for sibling in source_path.parent.iterdir():
            if sibling.is_file() and sibling.suffix.lower() != ".jsx":
                relative = sibling.relative_to(self.runtime).as_posix()
                asset = companions.get(relative)
                resolved = sibling.resolve()
                if (not asset or not resolved.is_relative_to(self.runtime)
                    or hashlib.sha256(resolved.read_bytes()).hexdigest() != asset["sha256"]):
                    raise BridgeError("Creold companion asset integrity check failed")
                shutil.copy2(sibling, payload / sibling.name)
        settings = self.bridge.output_path("creold/settings/.keep").parent
        settings.mkdir(parents=True, exist_ok=True)
        output = str(self.bridge.output_dir)
        source = re.sub(r"(?m)^\s*#(?:target|targetengine)\b[^\r\n]*", "", source)
        for prop in ("myDocuments", "userData"):
            source = source.replace("Folder." + prop, "Folder(" + json.dumps(str(settings)) + ")")
        source = source.replace("Folder.desktop", "Folder(" + json.dumps(output) + ")")
        source = source.replace("Folder.selectDialog(", "Illona.creoldSelectFolder(")
        source = source.replace("File.saveDialog(", "Illona.creoldSaveDialog(")
        source = re.sub(r"\bnew\s+Window\s*\(", "new Illona.creoldWindow(", source)
        # Guard known write calls, while leaving read operations and instance types intact.
        source = re.sub(r"\b([A-Za-z_$][\w$\.]*)\.open\(\s*(['\"])([wa][^'\"]*)\2\s*\)",
            lambda m:"Illona.creoldOpenForWrite("+m[1]+","+json.dumps(m[3])+")", source)
        source = re.sub(r"\b([A-Za-z_$][\w$\.]*)\.(saveAs|exportFile)\(",
            lambda m:"Illona.creold"+("SaveAs" if m[2]=="saveAs" else "ExportFile")+"("+m[1]+",", source)
        source = re.sub(r"\b([A-Za-z_$][\w$\.]*)\.save\(\s*\)",r"Illona.creoldSave(\1)",source)
        prefs=[]
        for kind,key in re.findall(r"\.set(Boolean|Integer|Real|String)Preference\(\s*['\"]([^'\"]+)['\"]",source):
            if {"kind":kind,"key":key} not in prefs:prefs.append({"kind":kind,"key":key})
        prelude = ""
        if mode == "automatic":
            prelude = ('var alert=function(m){Illona.creoldMessages.push(String(m));};\n'
                'var confirm=function(){throw new Error("Confirmation requires interactive mode");};\n'
                'var prompt=function(){throw new Error("Prompt requires interactive mode");};\n'
                'var Window=function(){throw new Error("Dialog requires interactive mode");};\n')
        path = payload / source_path.name
        path.write_text("\ufeff(function(){\n" + prelude + source + "\n})();\n",encoding="utf-8")
        return {"script_path":str(path),"script_id":entry["script_id"],"preference_keys":prefs,
                "output_root":output,"job_root":str(job),"mode":mode}

    def _launch_worker(self, operation_id, job):
        with (job / "worker.log").open("ab") as log:
            proc = subprocess.Popen([sys.executable,"-m","illona_mcp.creold_worker",operation_id],
                stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,
                cwd=str(Path(__file__).resolve().parent.parent),close_fds=True,
                env={**os.environ,"ILLONA_STATE_DIR":str(self.bridge.state_dir),"ILLONA_OUTPUT_DIR":str(self.bridge.output_dir),"ILLONA_APP_PATH":str(self.bridge.app_path)})
        return proc.pid

    def _guard_pending_operations(self, operation_id):
        """Do not let queued workers acquire mutually blocking parent guards."""
        for request in (self.bridge.state_dir / "jobs").glob("*/request.json"):
            if request.parent.name == operation_id:
                continue
            try:
                meta = json.loads(request.read_text())
            except (OSError, ValueError) as exc:
                raise BridgeError("An earlier operation has unreadable metadata; inspect its receipt before launching another script") from exc
            if meta.get("operation") in READ_ONLY or meta.get("status") not in {
                "pending", "uncertain", "queued", "waiting_for_user",
            }:
                continue
            if self.bridge.operation_status(request.parent.name)["status"] != "completed":
                raise BridgeError(f"Operation {request.parent.name} is pending. Finish or recover it before launching another script.")

    def _commit_result(self, job, meta, envelope):
        receipt = job / "result.json"
        staged = receipt.with_suffix(".pending.json")
        staged.write_text(json.dumps(envelope))
        os.replace(staged, receipt)
        meta["status"] = "completed"
        (job / "request.json").write_text(json.dumps(meta))

    def _recover_completed_child(self, job, meta):
        """Rebuild a lost parent receipt using a final native receipt only.

        Never relaunch a queued original or infer completion from a worker PID:
        Illustrator can outlive the process that sent its Apple event.
        """
        children = meta.get("native_steps", [])
        if len(children) != 1:
            return False
        status = self.bridge.operation_status(children[0])
        if status["status"] != "completed":
            return False
        try:
            data = self.bridge._unwrap(status["result"], children[0], replayed=True)
            envelope = {"ok": True, "data": data}
        except BridgeError as exc:
            envelope = {"ok": False, "error": {"code": "CREOLD_ERROR", "message": str(exc)}}
        self._commit_result(job, meta, envelope)
        return True

    async def run_script(self, document_id, script_id, object_ids=None, mode="interactive",
                         selection_mode="replace", application_scope=False, operation_id=None):
        entry=self.script_info(script_id)
        if mode not in {"automatic","interactive"} or selection_mode not in {"replace","preserve"}:
            raise BridgeError("Invalid Creold execution/selection mode")
        if mode=="automatic" and script_id not in AUTOMATIC:
            raise BridgeError("This original requires interactive mode. Use a parameterized illona_creold_action for unattended editing.")
        if entry.get("global_scope") and not application_scope:
            raise BridgeError("This script has application or file-system scope. Set application_scope=true only when that complete scope is intended.")
        if not isinstance(document_id,str) or not document_id or len(document_id)>200:
            raise BridgeError("An explicit document_id is required")
        object_ids=list(object_ids or [])
        if len(object_ids)>500 or len(set(object_ids))!=len(object_ids) or any(not isinstance(i,str) or not i or len(i)>200 for i in object_ids):
            raise BridgeError("object_ids must contain at most 500 unique native UUIDs")
        if mode=="automatic" and not object_ids:
            raise BridgeError("Automatic originals require explicit object_ids")
        operation_id=operation_id or uuid.uuid4().hex;job=self.bridge._job(operation_id)
        args={"document_id":document_id,"script_id":script_id,"object_ids":object_ids,"mode":mode,
            "selection_mode":selection_mode,"application_scope":application_scope}
        digest=hashlib.sha256(json.dumps(args,sort_keys=True).encode()).hexdigest()
        async with self.bridge.transaction(root_operation=operation_id):
            request=job/"request.json";receipt=job/"result.json"
            if request.exists():
                meta=json.loads(request.read_text())
                if meta["digest"]!=digest:raise BridgeError("This operation_id belongs to a different request")
                if receipt.exists():return self.bridge._unwrap(json.loads(receipt.read_text()),operation_id,True)
                if self._recover_completed_child(job,meta):
                    return self.bridge._unwrap(json.loads(receipt.read_text()),operation_id,True)
                return self.bridge.operation_status(operation_id)
            self._guard_pending_operations(operation_id)
            # Validate fixed source and target before staging or launching any user code.
            self._source(entry)
            target=await self.bridge.call("inspect_document",{"document_id":document_id,"limit":1})
            if application_scope:
                status=await self.bridge.call("status",{})
                for doc in status["documents"]:
                    if doc.get("path"):self.bridge.output_path(doc["path"])
            if re.search(r"\.(?:save|saveAs|exportFile)\s*\(",self._source(entry)[1]) and target.get("path"):
                self.bridge.output_path(target["path"])
            job.mkdir(parents=True,mode=0o700)
            native={**args,**self._prepare(entry,job,mode)}
            child="creold_"+hashlib.sha256(operation_id.encode()).hexdigest()[:40]
            meta={"operation":"creold:"+script_id,"digest":digest,"status":"queued","created_at":time.time(),
                "native_steps":[child],"native_params":native,"mode":mode}
            request.write_text(json.dumps(meta))
            if mode=="interactive":
                try:meta["worker_pid"]=self._launch_worker(operation_id,job)
                except OSError as exc:
                    meta["status"]="not_started";request.write_text(json.dumps(meta));raise BridgeError("Could not start the interactive worker") from exc
                request.write_text(json.dumps(meta))
                return {"operation_id":operation_id,"status":"queued","script_id":script_id,
                    "message":"Use the script's Illustrator dialog, then illona_operation_status. Do not queue another edit or repeat this launch while it is pending.",
                    "scope":entry["scope"],"modification_verified":False}
            try:
                result=await self.bridge.call("creold_script",native,child)
                envelope={"ok":True,"data":result}
            except BridgeError as exc:
                if self.bridge.operation_status(child)["status"] in {"uncertain","pending"}:
                    meta["status"]="uncertain";request.write_text(json.dumps(meta));raise
                envelope={"ok":False,"error":{"code":"CREOLD_ERROR","message":str(exc)}}
            self._commit_result(job,meta,envelope)
            return self.bridge._unwrap(envelope,operation_id)


def register_creold(mcp,bridge,read_annotations,create_annotations,edit_annotations):
    from typing import Annotated,Literal
    from mcp.types import CallToolResult,TextContent
    from pydantic import Field
    from .creold_models import CreoldActionName,CreoldActionOptions,validate_action_options
    service=CreoldIntegration(bridge)

    @mcp.tool(annotations=read_annotations)
    async def illona_creold_catalog(query:str="",category:str|None=None,limit:Annotated[int,Field(ge=1,le=150)]=104)->dict:
        """Browse all 104 pinned Creold originals. A catalog entry is not a claim of unattended support or verified execution."""
        return service.list_scripts(query,category,limit)

    @mcp.tool(annotations=read_annotations)
    async def illona_creold_script_info(script_id:Annotated[str,Field(min_length=1,max_length=100)])->dict:
        """Read the fixed original's version, scope, source, dependencies and dialog requirements before launching."""
        return service.script_info(script_id)

    @mcp.tool(annotations=edit_annotations)
    async def illona_creold_run_script(document_id:str,script_id:str,object_ids:list[str]|None=None,
        mode:Literal["automatic","interactive"]="interactive",selection_mode:Literal["replace","preserve"]="replace",
        application_scope:bool=False,operation_id:str|None=None)->dict:
        """Launch one fixed Creold original against an explicit document/selection.

        Interactive mode returns queued immediately; complete its native Illustrator dialog and poll illona_operation_status.
        Automatic mode supports only five audited no-dialog originals. Original gradients can affect shared definitions.
        Script return does not prove edits: originals can swallow errors. Inspect/preview afterwards.
        Application/file-system scope requires application_scope=true. Output folders and stored settings stay inside Illona output.
        """
        return await service.run_script(document_id,script_id,object_ids,mode,selection_mode,application_scope,operation_id)

    @mcp.tool(annotations=edit_annotations,structured_output=False)
    async def illona_creold_action(document_id:str,action:CreoldActionName,
        object_ids:Annotated[list[str],Field(max_length=500)],options:CreoldActionOptions|None=None,operation_id:str|None=None)->CallToolResult:
        """Run a parameterized Creold-derived action without dialogs. All geometry uses native document POINTS, Y up.

        Uses explicit UUIDs and action-specific validated options; gradients are cloned to avoid recoloring unselected users.
        Inspect the result and request a preview. These adaptations are distinct from the unchanged original scripts.
        """
        params=validate_action_options(action,options or CreoldActionOptions())
        result = await bridge.call("creold_action",{"document_id":document_id,"action":action,"object_ids":object_ids,"options":params},operation_id)
        return CallToolResult(content=[TextContent(type="text",text=json.dumps(result,ensure_ascii=False))],
                              isError=result.get("success") is False)

    @mcp.resource("illona://creold-guide")
    def creold_guide()->str:
        return """Creold for Illona: 104 fixed MIT originals plus 14 parameterized editing adaptations.
Start with illona_creold_catalog and illona_creold_script_info. Select the intended document and UUIDs explicitly.
For unattended work use illona_creold_action: options use document points, Y up. Gradient adaptations clone definitions.
trace_images accepts at most 10 explicit PlacedItem/RasterItem UUIDs. preset is an exact installed tracing preset (default 16 Colors); ignore_white defaults true.
Tracing always expands to new editable GroupItem/path UUIDs and checks zero raster, placed or plugin descendants. White removal may crop output bounds; this is a vector approximation of the image, not pixel-identical conversion.
Original-script interactive launch is detached: finish its Illustrator dialog, then recover the same operation receipt.
Do not issue another edit while that job is queued, waiting, pending or uncertain. Never blindly repeat an original script.
Some originals act on documents, shared resources, files or the application. Read their declared scope and dependencies.
Original source can catch its own failures: script_returned is not verified modification. Inspect and preview afterwards.
Stored script settings and output folders are redirected/guarded inside Illona output. Original fixed files and licenses are packaged locally.
"""
    return service
