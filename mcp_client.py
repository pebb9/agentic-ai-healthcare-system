import json
import sys
import time
import uuid

from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

MCP_SERVER_URL = "http://127.0.0.1:8000/mcp"

# Session ID for this process — groups all calls from one agent run together
SESSION_ID = str(uuid.uuid4())[:8]



async def call_tool(tool_name: str, arguments: dict) -> dict:

    t0 = time.perf_counter()

    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)

    duration_ms = (time.perf_counter() - t0) * 1000
    print(f"  [MCP client] {tool_name}  round-trip: {duration_ms:.0f}ms", file=sys.stderr)
    

    return json.loads(result.content[0].text)

    