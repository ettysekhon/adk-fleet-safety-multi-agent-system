"""
Test script for SafetyScorerAgent using mock data.
Focuses on the parallel evaluation logic and safety scoring factors.
"""

import asyncio
import json

from app.agents.fleet_safety.safety_scorer_agent import SafetyScorerAgent


class MockMCPClient:
    """Mock MCP client for safety scoring tests."""

    async def call_tool(self, server_name, tool_name, arguments):
        print(f"Mock MCP call: {server_name}.{tool_name} with args: {arguments}")
        return json.dumps({"status": "success", "data": {}})


async def test_agent():
    print("Starting SafetyScorerAgent test")
    print("=" * 60)

    # Initialise mock client and agent
    mock_client = MockMCPClient()
    agent = SafetyScorerAgent(mcp_client=mock_client)

    # Define test route (simulating a route object from RoutePlanner)
    route = {
        "route_id": "route_123",
        "summary": "I-5 South",
        "distance_miles": 450,
        "duration_minutes": 420,
        "polyline": "mock_polyline_string",
        "steps": [],
    }

    # Define driver profile
    driver_profile = {
        "driver_id": "driver_007",
        "name": "James Bond",
        "years_experience": 8,  # Expert (+10)
        "times_driven_route": 15,  # Familiar (+5)
        "incidents_per_100k_miles": 0.2,  # Excellent (+5)
    }

    # Define current conditions
    current_conditions = {
        "time_of_day": 22,  # 10 PM = Night (-15)
        "weather": "rain",  # Rain (-10 * 1.1 = -11 approx)
        "traffic_level": "light",
    }

    print(f"Route: {route['summary']} ({route['distance_miles']} miles)")
    print(
        f"Driver: {driver_profile['name']} ({driver_profile['years_experience']} years experience)"
    )
    print(
        f"Conditions: Time {current_conditions['time_of_day']}:00, Weather {current_conditions['weather']}"
    )

    print("\n--- Running safety score evaluation ---")
    result = await agent.score_route(route, driver_profile, current_conditions)

    print(f"\nSafety score: {result['safety_score']}/100")
    print(f"Risk Level: {result['risk_level']}")

    print("\nComponent scores:")
    for component, analysis in result["component_scores"].items():
        print(f"  - {component}: Impact {analysis.get('score_impact', 0)}")

    print("\nTop risk factors:")
    for risk in result["top_risk_factors"]:
        print(f"  {risk['factor']} (impact: {risk['impact']})")
        print(f"    Details: {risk.get('details', '')}")

    print("\nRecommendations:")
    for rec in result["recommendations"]:
        print(f"  [{rec.get('priority', 'medium').upper()}] {rec['action']}")
        print(f"    Reason: {rec['reason']}")

    print("\nSafetyScorerAgent test complete")


if __name__ == "__main__":
    asyncio.run(test_agent())
