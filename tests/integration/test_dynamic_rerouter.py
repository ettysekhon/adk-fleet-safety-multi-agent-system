"""
Integration Test for DynamicRerouterAgent with Real Google Maps MCP Server.
"""

import asyncio
import json
import os

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.helpers.env import load_env_and_verify_api_key
from app.agents.fleet_safety.dynamic_rerouter_agent import DynamicRerouterAgent
from app.agents.fleet_safety.route_planner_agent import RoutePlannerAgent


# Helper to print JSON nicely
def print_json(data):
    print(json.dumps(data, indent=2, default=str))


async def main():
    print("Starting DynamicRerouter integration test (real MCP)")
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

            # --- Initialise agents ---
            route_planner = RoutePlannerAgent(mcp_client=mcp_wrapper)
            rerouter = DynamicRerouterAgent(mcp_client=mcp_wrapper)

            # --- Step 1: set up active trip ---
            print("\nStep 1: Setting up active trip (London -> Manchester)")
            # First get a real route to have valid polyline/duration data
            request = {
                "origin": "London, UK",
                "destination": "Manchester, UK",
                "vehicle_type": "heavy_truck",
            }

            route_options = await route_planner.generate_route_options(request)
            if not route_options.get("routes"):
                print("No routes found to set up trip")
                return

            initial_route = route_options["routes"][0]
            print(f"Initial route: {initial_route.get('summary')}")

            # Create trip object
            trip = {
                "trip_id": "trip_test_001",
                "vehicle_id": "vehicle_001",
                "driver_id": "driver_001",
                "origin": {"lat": 51.5074, "lng": -0.1278},  # London approx
                "destination": "Manchester, UK",
                "current_location": {"lat": 51.5074, "lng": -0.1278},  # Still at origin
                "current_route": initial_route,
                "planned_route_polyline": initial_route.get("polyline")
                or initial_route.get("overview_polyline", {}).get("points", ""),
                "remaining_route_polyline": initial_route.get("polyline")
                or initial_route.get("overview_polyline", {}).get("points", ""),
                "planned_remaining_duration_minutes": initial_route.get(
                    "duration_in_traffic_minutes", 200
                ),
            }

            # Normalise trip duration if missing (from previous issues)
            if not trip["planned_remaining_duration_minutes"] and initial_route.get("legs"):
                val = initial_route["legs"][0].get("duration_in_traffic", {}).get("value")
                if val:
                    trip["planned_remaining_duration_minutes"] = val / 60
                else:
                    trip["planned_remaining_duration_minutes"] = 240  # fallback to 4h

            rerouter.add_active_trip(trip)
            print("Trip added to monitoring")

            # --- Step 2: monitor trip ---
            print("\nStep 2: Monitoring trip (checking conditions)")

            # Run one monitoring cycle
            monitor_result = await rerouter.monitor_active_trips()

            print("\nMonitoring result:")
            print_json(monitor_result)

            # Verify details
            if monitor_result["trip_details"]:
                details = monitor_result["trip_details"][0]
                cond = details["conditions"]
                print(f"\nCondition check: traffic level = {cond.get('traffic_level')}")
                print(f"Reroute recommended: {cond.get('reroute_recommended')}")
                if cond.get("reasons"):
                    print(f"Reasons: {cond['reasons']}")

            # --- Step 3: simulate emergency reroute ---
            print("\nStep 3: Testing emergency reroute")
            emergency_result = await rerouter.emergency_reroute(
                vehicle_id="vehicle_001", reason="Simulated road closure ahead"
            )

            if emergency_result["success"]:
                print("Emergency reroute successful")
                print(
                    f"New Route Polyline Length: {len(emergency_result['new_route'].get('polyline') or emergency_result['new_route'].get('overview_polyline', {}).get('points', ''))}"
                )
                print(f"Notification: {emergency_result['notification']['message'][:50]}...")
            else:
                print(f"Emergency reroute failed: {emergency_result.get('error')}")

            print("\nDynamicRerouter integration test complete")

    except Exception as e:
        print(f"\nError during integration test: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
