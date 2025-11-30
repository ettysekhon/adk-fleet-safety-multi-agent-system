"""
Integration Test for FleetSafetyOrchestrator with Real Google Maps MCP Server.
Tests end-to-end coordination with real external data.
"""

import asyncio
import json
import os

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.helpers.env import load_env_and_verify_api_key
from app.agents.fleet_safety.analytics_agent import AnalyticsAgent
from app.agents.fleet_safety.dynamic_rerouter_agent import DynamicRerouterAgent
from app.agents.fleet_safety.orchestrator import FleetSafetyOrchestrator
from app.agents.fleet_safety.risk_monitor_agent import RiskMonitorAgent
from app.agents.fleet_safety.route_planner_agent import RoutePlannerAgent
from app.agents.fleet_safety.safety_scorer_agent import SafetyScorerAgent


# Helper to print JSON nicely
def print_json(data):
    print(json.dumps(data, indent=2, default=str))


async def main():
    print("Starting Orchestrator integration test (real MCP)")
    print("=" * 60)

    # Load environment variables
    try:
        load_env_and_verify_api_key(require_maps_key=True)
    except ValueError as e:
        print(f"Environment error: {e}")
        return

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    print(f"API key loaded: {api_key[:4]}...{api_key[-4:]} (length: {len(api_key)})")

    # Configure the MCP connection
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "google-maps-mcp-server"],
        env={"GOOGLE_MAPS_API_KEY": os.environ["GOOGLE_MAPS_API_KEY"]},
    )

    try:
        async with (
            stdio_client(server_params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            # --- MCP wrapper ---
            class MCPClientWrapper:
                def __init__(self, session):
                    self.session = session

                async def call_tool(self, server_name, tool_name, arguments):
                    print(f"Calling Tool: {tool_name}")
                    result = await self.session.call_tool(tool_name, arguments)
                    if result.content and hasattr(result.content[0], "text"):
                        return result.content[0].text
                    return json.dumps(result.model_dump())

            mcp_wrapper = MCPClientWrapper(session)

            # 1. Initialise agents with real MCP client
            print("\nInitialising agents...")
            orchestrator = FleetSafetyOrchestrator()

            # Agents using real MCP
            route_planner = RoutePlannerAgent(mcp_client=mcp_wrapper)
            safety_scorer = SafetyScorerAgent(mcp_client=mcp_wrapper)
            rerouter = DynamicRerouterAgent(mcp_client=mcp_wrapper)

            # Agents using mostly internal data (but connected for future use)
            risk_monitor = RiskMonitorAgent(mcp_client=mcp_wrapper)
            analytics = AnalyticsAgent(mcp_client=mcp_wrapper)

            # 2. Register agents
            orchestrator.register_agents(
                {
                    "route_planner": route_planner,
                    "safety_scorer": safety_scorer,
                    "risk_monitor": risk_monitor,
                    "analytics": analytics,
                    "rerouter": rerouter,
                }
            )

            # Mock minimal fleet state
            orchestrator.fleet_state["vehicles"]["vehicle_001"] = {
                "id": "vehicle_001",
                "type": "heavy_truck",
                "status": "active",
            }
            orchestrator.fleet_state["drivers"]["driver_001"] = {
                "id": "driver_001",
                "name": "Integration Driver",
            }

            print("Agents registered")

            # 3. Run end-to-end workflow: route planning
            print("\nTest: Request route plan (London -> Cambridge)")
            print("   This triggers RoutePlanner (real API) then SafetyScorer (real analysis)")

            plan_result = await orchestrator.request_route_plan(
                origin="London, UK",
                destination="Cambridge, UK",
                driver_id="driver_001",
                vehicle_id="vehicle_001",
                priority="safety",
            )

            print(f"\nStatus: {plan_result.get('status')}")

            if plan_result.get("status") == "success":
                rec = plan_result["recommended_route"]
                print(f"Recommendation: {rec.get('summary')}")
                print(f"   Distance: {rec.get('distance_miles', 0):.1f} miles")
                print(f"   Duration: {rec.get('estimated_duration_minutes', 0):.0f} mins")

                safety = rec.get("safety_analysis", {})
                print(f"   Safety Score: {safety.get('safety_score')}/100")
                print(f"   Risk Level: {safety.get('risk_level')}")
                print(f"   Rationale: {plan_result.get('selection_criteria')}")

                # Check alternatives
                alts = plan_result.get("alternative_routes", [])
                print(f"\n   Analysed {len(alts) + 1} total routes.")
            else:
                print("Planning failed")
                print_json(plan_result)

            # 4. Run dashboard generation (aggregated data)
            print("\nTest: Generate executive dashboard")
            dashboard = await orchestrator.generate_executive_dashboard()

            if dashboard.get("generated_at"):
                print("Dashboard generated successfully")
                print(f"   Fleet size: {dashboard['fleet_overview']['fleet_size']}")
                print(f"   System health: {dashboard['system_health']}")
            else:
                print("Dashboard generation failed")

            print("\nOrchestrator integration test complete")

    except Exception as e:
        print(f"\nError during integration test: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
