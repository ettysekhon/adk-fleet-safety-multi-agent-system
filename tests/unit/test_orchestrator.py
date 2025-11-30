"""
Test script for FleetSafetyOrchestrator.
Exercises coordination between Orchestrator and all specialist agents using a mock MCP client.
"""

import asyncio
import json

from app.agents.fleet_safety.analytics_agent import AnalyticsAgent
from app.agents.fleet_safety.dynamic_rerouter_agent import DynamicRerouterAgent
from app.agents.fleet_safety.orchestrator import FleetSafetyOrchestrator
from app.agents.fleet_safety.risk_monitor_agent import RiskMonitorAgent
from app.agents.fleet_safety.route_planner_agent import RoutePlannerAgent
from app.agents.fleet_safety.safety_scorer_agent import SafetyScorerAgent


# Mock MCP client for unit testing without real Google Maps calls
class MockMCPClient:
    async def call_tool(self, server_name, tool_name, arguments):
        if tool_name == "geocode_address":
            return json.dumps(
                {
                    "data": {
                        "formatted_address": arguments["address"],
                        "location": {"lat": 51.5, "lng": -0.1},
                    }
                }
            )
        elif tool_name == "get_directions":
            return json.dumps(
                {
                    "data": {
                        "routes": [
                            {
                                "summary": "M1 North",
                                "distance_meters": 320000,
                                "distance_miles": 198.8,
                                "duration_seconds": 14400,
                                "estimated_duration_minutes": 240,
                                "polyline": "mock_polyline_1",
                                "legs": [
                                    {"distance": {"value": 320000}, "duration": {"value": 14400}}
                                ],
                            },
                            {
                                "summary": "A1(M)",
                                "distance_meters": 330000,
                                "distance_miles": 204.8,
                                "duration_seconds": 15000,
                                "estimated_duration_minutes": 250,
                                "polyline": "mock_polyline_2",
                                "legs": [
                                    {"distance": {"value": 330000}, "duration": {"value": 15000}}
                                ],
                            },
                        ]
                    }
                }
            )
        elif tool_name == "get_traffic_conditions":
            return json.dumps({"traffic_level": "low"})
        elif tool_name == "calculate_route_safety_factors":
            return json.dumps(
                {
                    "safety_score": 75,
                    "risk_factors": [
                        {
                            "factor": "moderate_speed",
                            "impact": -5,
                            "details": "Average speed 60 mph",
                        }
                    ],
                }
            )
        elif tool_name == "find_nearby_places":
            return json.dumps(
                {
                    "places": [
                        {
                            "name": "Mock Service Station",
                            "place_id": "mock_place_123",
                            "rating": 4.5,
                        }
                    ]
                }
            )
        elif tool_name == "get_place_details":
            return json.dumps(
                {
                    "data": {
                        "name": "Mock Service Station",
                        "rating": 4.5,
                        "formatted_address": "M1 Services, UK",
                    }
                }
            )
        elif tool_name == "get_route_elevation_gain":
            return json.dumps({"total_gain": 300})  # 300 meters elevation gain
        return "{}"


def print_json(data):
    print(json.dumps(data, indent=2, default=str))


async def test_orchestrator():
    print("Starting FleetSafetyOrchestrator test")
    print("=" * 60)

    mock_client = MockMCPClient()

    # 1. Initialise all agents
    print("\nInitialising agents...")
    orchestrator = FleetSafetyOrchestrator()

    route_planner = RoutePlannerAgent(mcp_client=mock_client)
    safety_scorer = SafetyScorerAgent(mcp_client=mock_client)
    risk_monitor = RiskMonitorAgent(mcp_client=mock_client)
    analytics = AnalyticsAgent(mcp_client=mock_client)
    rerouter = DynamicRerouterAgent(mcp_client=mock_client)

    # 2. Register agents with orchestrator
    orchestrator.register_agents(
        {
            "route_planner": route_planner,
            "safety_scorer": safety_scorer,
            "risk_monitor": risk_monitor,
            "analytics": analytics,
            "rerouter": rerouter,
        }
    )

    # Mock fleet state in orchestrator
    orchestrator.fleet_state["vehicles"]["vehicle_001"] = {
        "id": "vehicle_001",
        "type": "truck",
        "status": "active",
    }
    orchestrator.fleet_state["drivers"]["driver_001"] = {"id": "driver_001", "name": "Test Driver"}

    print("Agents registered")

    # 3. Test: request route plan (planner + scorer)
    print("\nTest: Request route plan (London -> Manchester)")
    plan_result = await orchestrator.request_route_plan(
        origin="London, UK",
        destination="Manchester, UK",
        driver_id="driver_001",
        vehicle_id="vehicle_001",
        priority="safety",
    )

    print(f"Status: {plan_result.get('status')}")
    if plan_result.get("status") == "success":
        rec = plan_result["recommended_route"]
        print(f"Recommended: {rec.get('summary')}")
        print(f"Safety Score: {rec.get('safety_analysis', {}).get('safety_score')}")
        print(f"Reason: {plan_result.get('selection_criteria')}")
    else:
        print_json(plan_result)

    # 4. Test: check vehicle safety (RiskMonitor + Analytics)
    print("\nTest: Check vehicle safety")
    safety_status = await orchestrator.check_vehicle_safety("vehicle_001")
    print_json(safety_status)

    if safety_status.get("safety_rating"):
        print("Vehicle safety check completed")

    # 5. Test: executive dashboard (aggregate view)
    print("\nTest: Generate executive dashboard")
    dashboard = await orchestrator.generate_executive_dashboard()

    print("Fleet Overview:")
    print_json(dashboard.get("fleet_overview"))
    print("Key Metrics:")
    print_json(dashboard.get("key_metrics"))

    if dashboard.get("generated_at"):
        print("Dashboard generated")

    print("\nFleetSafetyOrchestrator test complete")


if __name__ == "__main__":
    asyncio.run(test_orchestrator())
