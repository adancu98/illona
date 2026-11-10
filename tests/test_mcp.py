"""Verify the actual stdio boundary and advertised schemas without opening Illustrator."""

import asyncio
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_catalog_and_validation():
    async def check():
        root = Path(__file__).resolve().parent.parent
        async with stdio_client(StdioServerParameters(command=str(root / "run.sh"), cwd=str(root))) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "Illona"
                tools = (await session.list_tools()).tools
                names = {t.name for t in tools}
                assert {"illona_create_brochure", "illona_create_elements", "illona_preview_document", "illona_operation_status"} <= names
                assert len(tools) == 86
                assert next(t for t in tools if t.name == "illona_status").annotations.readOnlyHint
                invalid = await session.call_tool("illona_create_elements", {"document_id": "unknown", "elements": [{"type": "rect", "width": -1}]})
                assert invalid.isError  # Fails input validation before any Illustrator call.
                resource = await session.read_resource("illona://design-guide")
                assert "Coordinates" in resource.contents[0].text
                lesson = await session.read_resource("illona://learning-playbook")
                text = lesson.contents[0].text
                assert "https://www.adobe.com/uk/learn/illustrator" in text
                assert "nu modificări ale modelului AI" in text
                assert "Pathfinder Divide/Unite" in text
    asyncio.run(check())

