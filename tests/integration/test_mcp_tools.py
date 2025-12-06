"""
Integration Test for MCP Server connectivity.
Supports both Remote (SSE) and Local (Stdio) MCP connections.
"""

import asyncio
import os
from contextlib import AsyncExitStack

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.helpers.env import load_env_and_verify_api_key


async def run_mcp_tests(session):
    """Run MCP connectivity tests with the given session."""
    # List tools to verify connection
    tools_result = await session.list_tools()
    tools = {t.name for t in tools_result.tools}

    print(f"Available tools: {sorted(tools)}")

    assert "get_directions" in tools, "get_directions tool not found"
    assert "geocode_address" in tools, "geocode_address tool not found"

    # Simple tool call
    print("\nTesting geocode_address tool...")
    result = await session.call_tool("geocode_address", {"address": "London, UK"})

    assert result.content, "No content in result"
    assert "London" in result.content[0].text, "London not found in geocode result"

    print(f"Geocode result: {result.content[0].text[:100]}...")
    print("\nMCP connectivity test complete")


async def test_mcp_connection():
    """Test connectivity to the Google Maps MCP server."""
    print("Starting MCP connectivity test")
    print("=" * 60)

    try:
        load_env_and_verify_api_key(require_maps_key=True)
    except ValueError as e:
        print(f"Skipping MCP test: {e}")
        return

    # Check for remote MCP server first (SSE)
    mcp_server_url = os.getenv("MCP_SERVER_URL")

    try:
        if mcp_server_url:
            # Remote SSE connection (for production/GKE)
            print(f"Connecting to remote MCP server at {mcp_server_url}...")
            async with AsyncExitStack() as stack:
                sse_ctx = sse_client(mcp_server_url)
                read, write = await stack.enter_async_context(sse_ctx)
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                print("Connected to Remote MCP Server via SSE.")

                await run_mcp_tests(session)
        else:
            # Local stdio connection (for local development)
            api_key = os.getenv("GOOGLE_MAPS_API_KEY")
            print(f"API key loaded: {api_key[:4]}...{api_key[-4:]} (length: {len(api_key)})")

            server_params = StdioServerParameters(
                command="uv",
                args=["run", "google-maps-mcp-server"],
                env={"GOOGLE_MAPS_API_KEY": api_key},
            )

            print("Connecting to Local MCP Server (subprocess)...")
            async with (
                stdio_client(server_params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                print("Connected to Local MCP Server via Stdio.")

                await run_mcp_tests(session)

    except Exception as e:
        raise AssertionError(f"MCP connection failed: {e}") from e


def test_mcp_tools_integration():
    """Pytest wrapper for async test"""
    asyncio.run(test_mcp_connection())


if __name__ == "__main__":
    asyncio.run(test_mcp_connection())
