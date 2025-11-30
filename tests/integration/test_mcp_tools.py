import asyncio
import os

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.helpers.env import load_env_and_verify_api_key


async def test_mcp_connection():
    """Test connectivity to the Google Maps MCP server."""

    try:
        load_env_and_verify_api_key(require_maps_key=True)
    except ValueError as e:
        print(f"Skipping MCP test: {e}")
        return

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "google-maps-mcp-server"],
        env={"GOOGLE_MAPS_API_KEY": api_key},
    )

    try:
        async with (
            stdio_client(server_params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            # List tools to verify connection
            tools_result = await session.list_tools()
            tools = {t.name for t in tools_result.tools}

            assert "get_directions" in tools
            assert "geocode_address" in tools

            # Simple tool call
            result = await session.call_tool("geocode_address", {"address": "London, UK"})

            assert result.content
            assert "London" in result.content[0].text

    except Exception as e:
        raise AssertionError(f"MCP connection failed: {e}") from e


def test_mcp_tools_integration():
    """Pytest wrapper for async test"""
    asyncio.run(test_mcp_connection())
