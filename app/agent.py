import asyncio
import os
import warnings
from contextlib import AsyncExitStack
from typing import Any

from google.adk.apps import App
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.agents.fleet_safety.analytics_agent import AnalyticsAgent
from app.agents.fleet_safety.dynamic_rerouter_agent import DynamicRerouterAgent
from app.agents.fleet_safety.orchestrator import FleetSafetyOrchestrator
from app.agents.fleet_safety.risk_monitor_agent import RiskMonitorAgent
from app.agents.fleet_safety.route_planner_agent import RoutePlannerAgent
from app.agents.fleet_safety.safety_scorer_agent import SafetyScorerAgent
from app.helpers.env import load_env_and_verify_api_key

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

load_env_and_verify_api_key(require_maps_key=True)


# --- MCP Client ---
class MCPClientWrapper:
    """
    Wraps MCP client to handle async connection lifecycle and tool calls.
    Supports both Local (Stdio) and Remote (SSE) connections.
    """

    def __init__(self):
        self.session: ClientSession | None = None
        self.exit_stack = None
        self.lock = asyncio.Lock()

    async def ensure_connected(self):
        if self.session:
            return

        async with self.lock:
            if self.session:
                return

            self.exit_stack = AsyncExitStack()

            # 1. Check for Remote MCP Server (e.g. Cloud Run)
            mcp_server_url = os.getenv("MCP_SERVER_URL")
            if mcp_server_url:
                print(f"Connecting to remote MCP server at {mcp_server_url}...")
                try:
                    sse_ctx = sse_client(mcp_server_url)
                    read, write = await self.exit_stack.enter_async_context(sse_ctx)
                    session_ctx = ClientSession(read, write)
                    self.session = await self.exit_stack.enter_async_context(session_ctx)
                    await self.session.initialize()
                    print("Connected to Remote MCP Server via SSE.")
                    return
                except Exception as e:
                    print(f"Failed to connect to remote MCP Server: {e}")
                    if self.exit_stack:
                        await self.exit_stack.aclose()
                    self.session = None
                    raise

            # 2. Fallback to Local Subprocess (Stdio)
            print("Connecting to Local MCP Server (subprocess)...")
            api_key = os.getenv("GOOGLE_MAPS_API_KEY")

            # Determine command: use 'uv' if available, else python module
            import shutil
            import sys

            if shutil.which("uv"):
                command = "uv"
                args = ["run", "google-maps-mcp-server"]
            else:
                # Fallback for production containers where 'uv' might not be in PATH
                # but the package is installed
                command = sys.executable
                args = ["-m", "google_maps_mcp_server"]

            server_params = StdioServerParameters(
                command=command,
                args=args,
                env={"GOOGLE_MAPS_API_KEY": api_key} if api_key else {},
            )

            try:
                stdio_ctx = stdio_client(server_params)
                read, write = await self.exit_stack.enter_async_context(stdio_ctx)
                session_ctx = ClientSession(read, write)
                self.session = await self.exit_stack.enter_async_context(session_ctx)
                await self.session.initialize()
                print("Connected to Local MCP Server via Stdio.")
            except Exception as e:
                print(f"Failed to connect to Local MCP Server: {e}")
                if self.exit_stack:
                    await self.exit_stack.aclose()
                self.session = None
                raise

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        await self.ensure_connected()
        if not self.session:
            raise RuntimeError("MCP Session not available")

        print(f"MCP Tool Call: {tool_name}")
        result = await self.session.call_tool(tool_name, arguments)

        # Unpack result text
        if result.content and hasattr(result.content[0], "text"):
            return result.content[0].text
        return str(result)


# --- Agent Initialisation ---

# Initialise MCP
mcp_client = MCPClientWrapper()

# Initialise Specialist Agents
print("Initializing Fleet Safety Agents...")
route_planner = RoutePlannerAgent(mcp_client=mcp_client)
safety_scorer = SafetyScorerAgent(mcp_client=mcp_client)
risk_monitor = RiskMonitorAgent(mcp_client=mcp_client)
analytics = AnalyticsAgent(mcp_client=mcp_client)
rerouter = DynamicRerouterAgent(mcp_client=mcp_client)

# Initialise Orchestrator
orchestrator = FleetSafetyOrchestrator()
orchestrator.register_agents(
    {
        "route_planner": route_planner,
        "safety_scorer": safety_scorer,
        "risk_monitor": risk_monitor,
        "analytics": analytics,
        "rerouter": rerouter,
    }
)

# Initialise Mock State (Demo Data)
orchestrator.fleet_state["vehicles"]["v001"] = {
    "id": "v001",
    "type": "HGV",
    "status": "active",
}
orchestrator.fleet_state["drivers"]["d001"] = {
    "id": "d001",
    "name": "Demo Driver",
    "safety_record": "good",
}

# --- App Definition (The "AdkApp") ---

# The official "Agent" instance
agent = orchestrator

# The ADK App instance (wrapper)
# This is what 'adk web' or 'adk run' looks for
app = App(
    name="fleet_safety_agent",
    root_agent=orchestrator,
)

# For local testing / running directly
if __name__ == "__main__":
    print("This file defines the agent. Run via 'make run' or 'python -m app.agent'")
