"""
Integration Test for SafetyScorerAgent with Real Google Maps MCP Server.
Supports both Remote (SSE) and Local (Stdio) MCP connections.

This test performs a full workflow:
1. Generate a route using RoutePlannerAgent (connected to real Google Maps).
2. Pass the generated route to SafetyScorerAgent for evaluation.
"""

import asyncio
import json
import os
from contextlib import AsyncExitStack
from datetime import datetime

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.agents.fleet_safety.route_planner_agent import RoutePlannerAgent
from app.agents.fleet_safety.safety_scorer_agent import SafetyScorerAgent
from app.helpers.env import load_env_and_verify_api_key


# Helper to print JSON nicely
def print_json(data):
    print(json.dumps(data, indent=2, default=str))


# MCP wrapper class
class MCPClientWrapper:
    def __init__(self, session):
        self.session = session

    async def call_tool(self, server_name, tool_name, arguments):
        print(f"Calling Tool: {tool_name}")
        result = await self.session.call_tool(tool_name, arguments)
        if result.content and hasattr(result.content[0], "text"):
            return result.content[0].text
        return json.dumps(result.model_dump())


async def run_safety_scorer_tests(mcp_wrapper):
    """Run the safety scorer tests with the given MCP wrapper."""
    # --- Initialise agents ---
    route_planner = RoutePlannerAgent(mcp_client=mcp_wrapper)
    safety_scorer = SafetyScorerAgent(mcp_client=mcp_wrapper)

    # --- Step 1: generate route (Birmingham -> Watford) ---
    print("\nStep 1: Generating real route (Birmingham -> Watford)")
    request = {
        "origin": "Birmingham, UK",
        "destination": "Watford, UK",
        "vehicle_type": "heavy_truck",
    }

    validation = await route_planner.validate_route_request(
        request["origin"],
        request["destination"],
        request["vehicle_type"],
        datetime.now().isoformat(),
    )

    if not validation.get("valid"):
        print("Route validation failed")
        return

    route_options = await route_planner.generate_route_options(request)
    if not route_options.get("routes"):
        print("No routes found")
        return

    # Pick the first route for analysis
    target_route = route_options["routes"][0]
    print(f"Selected Route: {target_route.get('summary', 'Unknown')}")

    # Normalise route data for scorer if needed
    if "distance_miles" not in target_route:
        dist_meters = target_route.get("distance_meters", 0)
        target_route["distance_miles"] = dist_meters * 0.000621371

    if "duration_minutes" not in target_route:
        dur_seconds = target_route.get("duration_seconds", 0)

        # If duration is a string or dict, handle accordingly
        duration_field = target_route.get("duration")
        if isinstance(duration_field, dict):
            dur_seconds = duration_field.get("value", 0)

        # Fallback to legs if top-level didn't give value
        if not dur_seconds and target_route.get("legs"):
            dur_seconds = target_route["legs"][0].get("duration", {}).get("value", 0)

        target_route["duration_minutes"] = dur_seconds / 60

    # --- Step 2: score route ---
    print("\nStep 2: Scoring route safety")

    driver_profile = {
        "driver_id": "integration_driver",
        "name": "Test Driver",
        "years_experience": 5,
        "times_driven_route": 2,
        "incidents_per_100k_miles": 0.0,
    }

    current_conditions = {
        "time_of_day": 14,  # 2 PM
        "weather": "rain",
        "traffic_level": "moderate",
    }

    score_result = await safety_scorer.score_route(target_route, driver_profile, current_conditions)

    print("\nSafety assessment results:")
    print(f"  Score: {score_result['safety_score']}/100")
    print(f"  Risk level: {score_result['risk_level']}")

    print("\n  Top risk factors:")
    for risk in score_result["top_risk_factors"]:
        print(f"  - {risk['factor']} (impact: {risk['impact']})")

    print("\n  Recommendations:")
    for rec in score_result["recommendations"]:
        print(f"  - {rec['action']}")

    print("\nSafetyScorer integration test complete")


async def main():
    print("Starting SafetyScorer integration test (real MCP)")
    print("=" * 60)

    # Load environment variables
    try:
        load_env_and_verify_api_key(require_maps_key=True)
    except ValueError as e:
        print(f"Environment error: {e}")
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

                mcp_wrapper = MCPClientWrapper(session)
                await run_safety_scorer_tests(mcp_wrapper)
        else:
            # Local stdio connection (for local development)
            api_key = os.getenv("GOOGLE_MAPS_API_KEY")
            print(f"API key loaded: {api_key[:4]}...{api_key[-4:]} (length: {len(api_key)})")

            server_params = StdioServerParameters(
                command="uv",
                args=["run", "google-maps-mcp-server"],
                env={"GOOGLE_MAPS_API_KEY": os.environ["GOOGLE_MAPS_API_KEY"]},
            )

            print("Connecting to Local MCP Server (subprocess)...")
            async with (
                stdio_client(server_params) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                print("Connected to Local MCP Server via Stdio.")

                mcp_wrapper = MCPClientWrapper(session)
                await run_safety_scorer_tests(mcp_wrapper)

    except Exception as e:
        print(f"\nError during integration test: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
