"""
Test script for AnalyticsAgent using internal mock data.
"""

import asyncio
import json

from app.agents.fleet_safety.analytics_agent import AnalyticsAgent


def print_json(data):
    print(json.dumps(data, indent=2, default=str))


async def test_agent():
    print("Starting AnalyticsAgent test")
    print("=" * 60)

    # Initialise agent (no external MCP client needed for internal data analysis)
    agent = AnalyticsAgent(mcp_client=None)

    # --- Test 1: Driver patterns ---
    print("\nTest 1: Analyse driver patterns")
    # Pick a driver from initialised data
    driver_id = agent.historical_data["trips"][0]["driver_id"]
    print(f"Analyzing Driver: {driver_id}")

    driver_analysis = await agent.analyze_driver_patterns(driver_id, days_lookback=90)
    print_json(driver_analysis)

    if driver_analysis.get("error"):
        print("Driver analysis failed")
    else:
        print(
            f"Driver analysis complete. Performance tier: {driver_analysis.get('performance_tier')}"
        )

    # --- Test 2: Risk corridors ---
    print("\nTest 2: Identify risk corridors")
    corridor_analysis = await agent.identify_risk_corridors(min_incidents=1)

    print(f"Corridors Analyzed: {corridor_analysis.get('corridors_analyzed')}")
    print("High Risk Corridors:")
    print_json(corridor_analysis.get("high_risk_corridors"))

    if corridor_analysis.get("high_risk_corridors"):
        print("Risk corridors identified")
    else:
        print("No high risk corridors found (may be due to random data generation)")

    # --- Test 3: Incident prediction ---
    print("\nTest 3: Predict incident probability")
    prediction = await agent.predict_incident_probability(
        driver_id=driver_id,
        route_type="highway",
        time_of_day=23,  # Night driving
        weather="rain",
    )
    print_json(prediction)

    if prediction.get("risk_classification") in ["high", "elevated", "moderate"]:
        print(f"Prediction returned risk: {prediction.get('risk_classification')}")
    else:
        print(f"Prediction returned low risk: {prediction.get('risk_classification')}")

    # --- Test 4: ROI calculation ---
    print("\nTest 4: Calculate ROI")
    roi = await agent.calculate_roi_metrics(intervention_cost=50000)
    print_json(roi)
    print(f"ROI: {roi.get('roi_percentage')}%")

    print("\nAnalyticsAgent test complete")


if __name__ == "__main__":
    asyncio.run(test_agent())
