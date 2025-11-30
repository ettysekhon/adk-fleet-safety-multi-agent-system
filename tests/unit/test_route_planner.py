"""
Test script for RoutePlannerAgent using a mock MCP client.
Exercised to validate the sequential flow, fuel calculation and ranking logic without a live Google Maps MCP server.
"""

import asyncio
import json

from app.agents.fleet_safety.route_planner_agent import RoutePlannerAgent


class MockMCPClient:
    """Mock implementation of the Google Maps MCP client for unit tests."""

    async def call_tool(self, server_name, tool_name, arguments):
        print(f"Mock MCP call: {server_name}.{tool_name} with args: {arguments}")

        if tool_name == "geocode_address":
            address = arguments.get("address", "")
            if "London" in address:
                return json.dumps(
                    {
                        "data": {
                            "formatted_address": "London, UK",
                            "location": {"lat": 51.5074, "lng": -0.1278},
                        }
                    }
                )
            elif "Manchester" in address:
                return json.dumps(
                    {
                        "data": {
                            "formatted_address": "Manchester, UK",
                            "location": {"lat": 53.4808, "lng": -2.2426},
                        }
                    }
                )
            else:
                return json.dumps(
                    {
                        "data": {
                            "formatted_address": address,
                            "location": {"lat": 0.0, "lng": 0.0},
                        }
                    }
                )

        elif tool_name == "get_directions":
            # Return mock routes matching the real MCP server structure
            return json.dumps(
                {
                    "data": {
                        "routes": [
                            {
                                "summary": "M40",
                                "legs": [
                                    {"distance": {"miles": 200}, "duration": {"value": 14400}}
                                ],  # 4 hours
                                "distance_meters": 321868,  # 200 miles in meters
                                "distance_miles": 200,
                                "duration_seconds": 14400,
                                "estimated_duration_minutes": 240,
                                "polyline": "mock_polyline_m40",
                            },
                            {
                                "summary": "M1",
                                "legs": [
                                    {"distance": {"miles": 210}, "duration": {"value": 13800}}
                                ],  # 3h 50m
                                "distance_meters": 337961,  # 210 miles in meters
                                "distance_miles": 210,
                                "duration_seconds": 13800,
                                "estimated_duration_minutes": 230,
                                "polyline": "mock_polyline_m1",
                            },
                            {
                                "summary": "A1(M)",
                                "legs": [
                                    {"distance": {"miles": 220}, "duration": {"value": 15000}}
                                ],
                                "distance_meters": 354055,  # 220 miles in meters
                                "distance_miles": 220,
                                "duration_seconds": 15000,
                                "estimated_duration_minutes": 250,
                                "polyline": "mock_polyline_a1",
                            },
                        ],
                    }
                }
            )

        elif tool_name == "find_nearby_places":
            return json.dumps(
                {
                    "places": [
                        {
                            "name": "Mock Gas Station",
                            "rating": 4.5,
                            "vicinity": "M40 Services",
                            "place_id": "mock_place_id_123",
                        }
                    ],
                }
            )
        elif tool_name == "get_place_details":
            return json.dumps(
                {
                    "data": {
                        "name": "Mock Gas Station",
                        "rating": 4.5,
                        "formatted_address": "M40 Services, UK",
                    }
                }
            )
        elif tool_name == "get_route_elevation_gain":
            # Mock elevation data for testing
            return json.dumps({"total_gain": 500})  # 500 meters elevation gain

        return json.dumps({"error": "Tool not found"})


async def test_agent():
    print("Starting RoutePlannerAgent test with mock MCP client")
    print("=" * 60)

    # Initialise mock client and agent
    mock_client = MockMCPClient()
    agent = RoutePlannerAgent(mcp_client=mock_client)

    # Define test request
    request = {
        "origin": "London, UK",
        "destination": "Manchester, UK",
        "vehicle_type": "heavy_truck",
        "departure_time": "2023-10-27T08:00:00",
    }

    print(f"📋 Request: {request}")

    print("\n--- Step 1: Validation ---")
    validation = await agent.validate_route_request(
        request["origin"],
        request["destination"],
        request["vehicle_type"],
        request["departure_time"],
    )
    print(f"Validation Result: {json.dumps(validation, indent=2)}")

    if not validation.get("valid"):
        print("Validation failed")
        return

    print("\n--- Step 2: Generate options ---")
    options = await agent.generate_route_options(request)
    print(f"Routes Found: {options.get('route_count')}")

    print("\n--- Step 3: Enrich Routes (Fuel & Stops) ---")
    routes = options.get("routes", [])
    for i, route in enumerate(routes):
        print(f"\nProcessing Route {i + 1}: {route.get('summary')}")

        # Fuel (pass polyline for EV elevation calculation)
        polyline = route.get("polyline", "")
        fuel = await agent.calculate_fuel_cost(
            route["distance_miles"], request["vehicle_type"], route_polyline=polyline
        )
        route["fuel_cost"] = fuel
        cost_key = "total_fuel_cost" if "total_fuel_cost" in fuel else "total_energy_cost"
        print(f"  Fuel Cost: £{fuel.get(cost_key, 0)}")

        # Stops
        polyline = route.get("polyline", "mock_polyline")
        stops = await agent.find_required_stops(
            polyline,
            route["distance_miles"],
            route["estimated_duration_minutes"] / 60,
            request["vehicle_type"],
        )
        route["stops"] = stops
        print(f"  Stops Required: {stops['stops_required']}")

    print("\n--- Step 4: Ranking ---")
    ranking = await agent.rank_routes(routes)
    print(f"Ranking Result: {json.dumps(ranking, indent=2)}")

    print("\nTest Complete")


if __name__ == "__main__":
    asyncio.run(test_agent())
