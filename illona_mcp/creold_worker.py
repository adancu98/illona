"""Detached owner of a single native ScriptUI execution; no public script input."""
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack,asynccontextmanager
from .bridge import HOST,BridgeError,IllonaBridge


@asynccontextmanager
async def startup_transaction(bridge, operation_id):
    # The detached process can import quickly enough to catch its launcher's
    # final metadata commit. Wait for that lock; never retry a native operation.
    async with AsyncExitStack() as stack:
        for attempt in range(100):
            try:
                await stack.enter_async_context(bridge.transaction(root_operation=operation_id))
                break
            except BridgeError as exc:
                if "Another Illona process" not in str(exc) or attempt == 99:
                    raise
                await asyncio.sleep(0.1)
        yield


async def execute(operation_id):
    bridge=IllonaBridge();job=bridge._job(operation_id)
    request=job/"request.json";receipt=job/"result.json"
    meta=json.loads(request.read_text())
    if not meta["operation"].startswith("creold:"):raise RuntimeError("Not a fixed Creold job")
    async with startup_transaction(bridge,operation_id):
        if receipt.exists():return
        meta["status"]="waiting_for_user";request.write_text(json.dumps(meta))
        bridge.timeout=3605
        bridge.runner_path=HOST/"creold_interactive.applescript"
        child=meta["native_steps"][0]
        try:
            result=await bridge.call("creold_script",meta["native_params"],child)
            envelope={"ok":True,"data":result}
        except Exception as exc:
            if bridge.operation_status(child)["status"] in {"pending","uncertain"}:
                meta["status"]="uncertain";request.write_text(json.dumps(meta));return
            envelope={"ok":False,"error":{"code":"CREOLD_ERROR","message":str(exc)}}
        staged=receipt.with_suffix(".pending.json");staged.write_text(json.dumps(envelope));os.replace(staged,receipt)
        meta["status"]="completed";request.write_text(json.dumps(meta))


if __name__=="__main__":asyncio.run(execute(sys.argv[1]))
