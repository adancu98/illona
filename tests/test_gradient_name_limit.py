"""Guard the native gradient-name boundary that previously left partial artwork.

The real Python integration, bundled Node handler and MCP catalog are exercised.
Native execution is either mocked or made unreachable by using a nonexistent app.
"""

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from illona_mcp.bridge import BridgeError, IllonaBridge
from illona_mcp.ie3 import IE3Integration


ROOT = Path(__file__).resolve().parent.parent
TOOL = "illona_pro_create_gradient"
STOPS = [
    {"position": 0, "color": {"type": "rgb", "r": 130, "g": 106, "b": 71}},
    {"position": 43, "color": {"type": "rgb", "r": 196, "g": 162, "b": 99}},
    {"position": 66, "color": {"type": "rgb", "r": 229, "g": 204, "b": 149}},
    {"position": 100, "color": {"type": "rgb", "r": 156, "g": 125, "b": 77}},
]


@pytest.mark.parametrize("name", ["", "demo-back-diagram-brass-gradient"])
def test_invalid_gradient_name_stops_before_jobs_adapter_or_native(tmp_path, monkeypatch, name):
    async def check():
        bridge = IllonaBridge(state_dir=tmp_path / "state", output_dir=tmp_path / "output")
        native = AsyncMock(side_effect=AssertionError("Native execution must remain unreachable"))
        monkeypatch.setattr(bridge, "call", native)
        integration = IE3Integration(bridge)
        adapter = AsyncMock(side_effect=AssertionError("Invalid input must not start Node"))
        monkeypatch.setattr(integration, "_start", adapter)
        try:
            with pytest.raises(BridgeError, match="Invalid advanced tool arguments"):
                await integration.invoke(TOOL, {
                    "document_id": "doc-must-not-dispatch", "name": name,
                    "stops": STOPS, "operation_id": "invalid-gradient-name",
                })
            native.assert_not_awaited()
            adapter.assert_not_awaited()
            assert not (bridge.state_dir / "jobs").exists()
        finally:
            await integration.close()

    asyncio.run(check())


def test_31_character_name_reaches_real_handler_unchanged(tmp_path, monkeypatch):
    async def check():
        name = "demo-back-diagram-clay-gradient"
        assert len(name) == 31
        bridge = IllonaBridge(state_dir=tmp_path / "state", output_dir=tmp_path / "output")

        async def native_result(operation, params, operation_id=None):
            assert operation == "ie3_execute"
            assert params["tool_name"] == "create_gradient"
            assert params["document_id"] == "doc-explicit"
            assert params["params"]["name"] == name
            assert len(params["params"]["stops"]) == 4
            return {"result": {"success": True, "name": name, "stopCount": 4}}

        native = AsyncMock(side_effect=native_result)
        monkeypatch.setattr(bridge, "call", native)
        integration = IE3Integration(bridge)
        try:
            result = await integration.invoke(TOOL, {
                "document_id": "doc-explicit", "name": name, "stops": STOPS,
                "operation_id": "gradient-name-31",
            })
            assert not result.isError
            data = json.loads(next(c.text for c in result.content if c.type == "text"))
            assert data["name"] == name
            native.assert_awaited_once()
        finally:
            await integration.close()

    asyncio.run(check())


def test_actual_mcp_catalog_advertises_native_gradient_name_bounds(tmp_path):
    async def check():
        params = StdioServerParameters(
            command=str(ROOT / "run.sh"), cwd=str(ROOT), env={
                **os.environ,
                "ILLONA_STATE_DIR": str(tmp_path / "state"),
                "ILLONA_OUTPUT_DIR": str(tmp_path / "output"),
                "ILLONA_APP_PATH": str(tmp_path / "must-never-launch-Illustrator.app"),
            },
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert len(tools) == 86
                tool = next(t for t in tools if t.name == TOOL)
                name_schema = tool.inputSchema["properties"]["name"]
                assert name_schema["type"] == "string"
                assert name_schema["minLength"] == 1
                assert name_schema["maxLength"] == 31
                assert "name" in tool.inputSchema["required"]
        assert not (tmp_path / "state" / "jobs").exists()

    asyncio.run(check())
