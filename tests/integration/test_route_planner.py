"""
Integration Test for RoutePlannerAgent with Real Google Maps MCP Server.
"""

import asyncio
import json
import os
from datetime import datetime

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.helpers.env import load_env_and_verify_api_key
from app.agents.fleet_safety.route_planner_agent import RoutePlannerAgent


def print_json(data):
    print(json.dumps(data, indent=2, default=str))


async def main():
    print("Starting RoutePlannerAgent integration test (real MCP)")
    print("=" * 60)

    # Load environment variables
    try:
        load_env_and_verify_api_key(require_maps_key=True)
    except ValueError as e:
        print(f"Environment error: {e}")
        return

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    print(f"API key loaded: {api_key[:4]}...{api_key[-4:]} (length: {len(api_key)})")

    # Connect to Google Maps MCP server
    print("Connecting to Google Maps MCP server...")

    # Configure the MCP connection
    # We use 'uv' to run the server command to ensure it uses the project environment
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "google-maps-mcp-server"],
        env={
            "GOOGLE_MAPS_API_KEY": os.environ["GOOGLE_MAPS_API_KEY"],
            # "PATH": os.environ.get("PATH") # Pass PATH to ensure tools are found
        },
    )

    # Create the MCP Client/Toolset
    try:
        # Using standard MCP python client:
        async with (
            stdio_client(server_params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()

            # Create a wrapper that matches what RoutePlannerAgent expects
            class MCPClientWrapper:
                def __init__(self, session):
                    self.session = session

                async def call_tool(self, server_name, tool_name, arguments):
                    # MCP ClientSession.call_tool expects (name, arguments).
                    # 'server_name' is ignored as we are connected to a single server.

                    print(f"Calling Tool: {tool_name}")
                    result = await self.session.call_tool(tool_name, arguments)

                    # Normalise result into a JSON string to match the agent expectations.
                    if result.content and hasattr(result.content[0], "text"):
                        return result.content[0].text

                    # Fallback if it's already a dict/object (unlikely if standard MCP)
                    return json.dumps(result.model_dump())

            mcp_wrapper = MCPClientWrapper(session)

            # Initialise agent
            agent = RoutePlannerAgent(mcp_client=mcp_wrapper)

            # Test data
            request = {
                "origin": "Manchester, UK",
                "destination": "London, UK",
                "vehicle_type": "heavy_truck",
            }

            print(f"Request: {request}")

            # --- Step 1: validation ---
            print("\n--- Step 1: Validation ---")
            validation = await agent.validate_route_request(
                request["origin"],
                request["destination"],
                request["vehicle_type"],
                datetime.now().isoformat(),
            )
            print_json(validation)

            if not validation.get("valid"):
                print("Validation failed")
                return

            # --- Step 2: generate options ---
            print("\n--- Step 2: Generate options ---")
            options = await agent.generate_route_options(request)
            print(f"Routes Found: {options.get('route_count')}")

            # --- Step 3: enrich routes (fuel and stops) ---
            print("\n--- Step 3: Enrich routes (fuel and stops) ---")
            routes = options.get("routes", [])
            for i, route in enumerate(routes[:2]):  # Limit to first 2 for brevity
                print(f"\nProcessing Route {i + 1}: {route.get('summary')}")

                # Calculate distance in miles (from metres)
                distance_meters = route.get("distance_meters", 0)
                distance_miles = distance_meters * 0.000621371

                # Fuel (pass polyline for EV elevation calculation)
                polyline = route.get("polyline")
                if not polyline:
                    polyline = route.get("overview_polyline", {}).get("points", "")
                fuel = await agent.calculate_fuel_cost(
                    distance_miles, request["vehicle_type"], route_polyline=polyline
                )
                route["fuel_cost"] = fuel
                cost_key = "total_fuel_cost" if "total_fuel_cost" in fuel else "total_energy_cost"
                print(f"  Fuel Cost: £{fuel.get(cost_key, 0)}")

                # Stops - mocked polyline if needed, or use real one if available
                polyline = route.get("polyline")
                if not polyline:
                    polyline = route.get("overview_polyline", {}).get("points", "")

                if not polyline:
                    print("  No polyline found in response.")
                    # Create a dummy polyline from origin to destination to allow testing
                    # This is a fallback so the 'find_required_stops' path is exercised
                    try:
                        import polyline as polyline_lib

                        # Approximate coordinates for Manchester -> London for testing
                        mock_points = [(53.4808, -2.2426), (51.5074, -0.1278)]
                        polyline = polyline_lib.encode(mock_points)
                        print("  Generated synthetic polyline for testing stops logic.")
                    except ImportError:
                        print("  Could not generate mock polyline (polyline module missing).")

                if polyline:
                    stops = await agent.find_required_stops(
                        polyline,
                        distance_miles,
                        route.get("duration_seconds", 0) / 3600,  # Convert seconds to hours
                        request["vehicle_type"],
                    )
                    route["stops"] = stops
                    print(f"  Stops Required: {stops['stops_required']}")

            # --- Step 4: ranking ---
            print("\n--- Step 4: Ranking ---")
            ranking = await agent.rank_routes(routes)
            print(
                "Recommended Route Summary:",
                ranking.get("recommendation", {}).get("summary"),
            )
            print("Recommendation reason:", ranking.get("recommendation_reason"))

            print("\nRoutePlannerAgent integration test complete")

    except Exception as e:
        print(f"\nError during integration test: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
