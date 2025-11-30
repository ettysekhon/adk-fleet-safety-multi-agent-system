import asyncio
import logging
import os
from contextlib import AsyncExitStack
from typing import Any

from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import DatabaseSessionService
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from .analytics_agent import AnalyticsAgent
from .dynamic_rerouter_agent import DynamicRerouterAgent
from .orchestrator import FleetSafetyOrchestrator
from .risk_monitor_agent import RiskMonitorAgent
from .route_planner_agent import RoutePlannerAgent
from .safety_scorer_agent import SafetyScorerAgent


def setup_logging(log_file="logs/trace.log"):
    """Configure debug logging for observability showcase."""
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    if os.path.exists(log_file):
        os.remove(log_file)

    logging.basicConfig(
        filename=log_file,
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )
    print(f"Debug logging enabled: {log_file}")


setup_logging()


class MCPClientWrapper:
    """
    Wraps MCP client to handle async connection lifecycle and tool calls.
    Initiates connection lazily on first tool call.
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

            print("Connecting to Google Maps MCP Server...")
            api_key = os.getenv("GOOGLE_MAPS_API_KEY")
            server_params = StdioServerParameters(
                command="uv",
                args=["run", "google-maps-mcp-server"],
                env={"GOOGLE_MAPS_API_KEY": api_key} if api_key else {},
            )

            # Manually enter the context managers
            self.exit_stack = AsyncExitStack()
            try:
                # Enter stdio_client context
                stdio_ctx = stdio_client(server_params)
                read, write = await self.exit_stack.enter_async_context(stdio_ctx)

                # Enter ClientSession context
                session_ctx = ClientSession(read, write)
                self.session = await self.exit_stack.enter_async_context(session_ctx)

                await self.session.initialize()
                print("Connected to MCP Server.")
            except Exception as e:
                print(f"Failed to connect to MCP Server: {e}")
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


# Initialise MCP Wrapper
mcp_client = MCPClientWrapper()

# Specialist Agents
route_planner = RoutePlannerAgent(mcp_client=mcp_client)
safety_scorer = SafetyScorerAgent(mcp_client=mcp_client)
risk_monitor = RiskMonitorAgent(mcp_client=mcp_client)
analytics = AnalyticsAgent(mcp_client=mcp_client)
rerouter = DynamicRerouterAgent(mcp_client=mcp_client)

# Orchestrator (Root Agent)
root_agent = FleetSafetyOrchestrator()
root_agent.register_agents(
    {
        "route_planner": route_planner,
        "safety_scorer": safety_scorer,
        "risk_monitor": risk_monitor,
        "analytics": analytics,
        "rerouter": rerouter,
    }
)

# Initialise Mock State for Demo
root_agent.fleet_state["vehicles"]["v001"] = {
    "id": "v001",
    "type": "HGV",
    "status": "active",
}
root_agent.fleet_state["drivers"]["d001"] = {
    "id": "d001",
    "name": "Demo Driver",
    "safety_record": "good",
}

# Initialise Services for Session and Memory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
data_dir = os.path.join(BASE_DIR, "data")
os.makedirs(data_dir, exist_ok=True)

db_path = os.path.join(data_dir, "fleet_safety.db")
print(f"Database path: {db_path}")

session_service = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{db_path}")
memory_service = InMemoryMemoryService()

# Alias for compatibility
agent = root_agent
