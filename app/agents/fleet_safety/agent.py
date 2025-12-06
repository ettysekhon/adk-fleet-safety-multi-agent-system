"""
Fleet Safety Agent - Entry point for ADK Web
"""

import asyncio
import os
import warnings
from contextlib import AsyncExitStack
from typing import Any

from google.adk.agents import Agent
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client

from .analytics_agent import AnalyticsAgent
from .dynamic_rerouter_agent import DynamicRerouterAgent
from .orchestrator import FleetSafetyOrchestrator
from .risk_monitor_agent import RiskMonitorAgent
from .route_planner_agent import RoutePlannerAgent
from .safety_scorer_agent import SafetyScorerAgent

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


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

            print("Connecting to Local MCP Server (subprocess)...")
            api_key = os.getenv("GOOGLE_MAPS_API_KEY")

            import shutil
            import sys

            if shutil.which("uv"):
                command = "uv"
                args = ["run", "google-maps-mcp-server"]
            else:
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

        if result.content and hasattr(result.content[0], "text"):
            return result.content[0].text
        return str(result)


def _create_agent() -> Agent:
    """Create and configure the Fleet Safety Agent with sub-agents."""
    print("Initializing Fleet Safety Agents...")

    mcp_client = MCPClientWrapper()

    # Create specialist agents
    route_planner = RoutePlannerAgent(mcp_client=mcp_client)
    safety_scorer = SafetyScorerAgent(mcp_client=mcp_client)
    risk_monitor = RiskMonitorAgent(mcp_client=mcp_client)
    analytics = AnalyticsAgent(mcp_client=mcp_client)
    rerouter = DynamicRerouterAgent(mcp_client=mcp_client)

    print("  - Created route_planner_agent")
    print("  - Created safety_scorer_agent")
    print("  - Created risk_monitor_agent")
    print("  - Created analytics_agent")
    print("  - Created rerouter_agent")

    # Create orchestrator and register sub-agents
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

    print(f"  - Registered {len(orchestrator.tools)} tools with orchestrator")
    print(
        "  - AgentTools: route_planner_agent, safety_scorer_agent, risk_monitor_agent, analytics_agent, rerouter_agent"
    )

    # Initialize demo fleet state
    orchestrator.fleet_state["vehicles"]["v001"] = {
        "id": "v001",
        "type": "heavy_truck",
        "status": "active",
        "fuel_type": "diesel",
        "max_range_miles": 500,
    }
    orchestrator.fleet_state["vehicles"]["v002"] = {
        "id": "v002",
        "type": "electric_van",
        "status": "active",
        "fuel_type": "electric",
        "max_range_miles": 180,
        "current_charge_pct": 85,
    }

    orchestrator.fleet_state["drivers"]["d001"] = {
        "id": "d001",
        "name": "John Smith",
        "years_experience": 5,
        "safety_record": "good",
        "times_driven_route": 0,  # For unfamiliar route risk factor
        "incidents_per_100k_miles": 0.3,
    }
    orchestrator.fleet_state["drivers"]["d002"] = {
        "id": "d002",
        "name": "Jane Doe",
        "years_experience": 12,
        "safety_record": "excellent",
        "times_driven_route": 15,
        "incidents_per_100k_miles": 0.1,
    }

    print("Fleet Safety Multi-Agent System initialized successfully!")
    print(
        f"  - Fleet: {len(orchestrator.fleet_state['vehicles'])} vehicles, {len(orchestrator.fleet_state['drivers'])} drivers"
    )

    return orchestrator


# ADK web looks for `root_agent` or `agent`
root_agent = _create_agent()
