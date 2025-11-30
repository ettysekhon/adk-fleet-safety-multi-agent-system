"""
Test script for RiskMonitorAgent and InterventionAgent.
"""

import asyncio
import json
from datetime import datetime, timedelta

from app.agents.fleet_safety.risk_monitor_agent import InterventionAgent, RiskMonitorAgent


def print_json(data):
    print(json.dumps(data, indent=2, default=str))


async def test_risk_monitor():
    print("Starting RiskMonitorAgent test")
    print("=" * 60)

    # Initialise agents with no external MCP dependency
    monitor = RiskMonitorAgent(mcp_client=None)
    intervention = InterventionAgent(mcp_client=None)

    # --- Test 1: telemetry analysis (speeding) ---
    print("\nTest 1: Analyse telemetry (speeding)")
    telemetry = {
        "speed": 88,
        "speed_limit": 70,
        "acceleration": 0.1,
        "location": {"lat": 51.5, "lng": -0.1},
    }

    analysis = await monitor.analyze_telemetry("vehicle_001", telemetry)
    print_json(analysis)

    if analysis.get("requires_intervention"):
        print("High risk detected, checking for intervention...")

        # --- Test 2: calculate risk score ---
        print("\nTest 2: Calculate risk score")
        score_result = await monitor.calculate_risk_score(
            "vehicle_001",
            [analysis],  # pass the recent event
        )
        print_json(score_result)

        # --- Test 3: intervention ---
        print("\nTest 3: Execute intervention")
        if score_result["risk_level"] in ["high", "critical"]:
            alert_result = await intervention.alert_driver(
                "vehicle_001",
                "driver_001",
                "speeding",
                "Please reduce speed immediately. You are 18mph over limit.",
                "high",
            )
            print_json(alert_result)

            if alert_result["alert_sent"]:
                print("Driver alert sent")

    # --- Test 4: fatigue check ---
    print("\nTest 4: Check driver fatigue")

    # Simulate time 12 hours after shift start
    current_time = (datetime.now() + timedelta(hours=12)).isoformat()
    fatigue_check = await monitor.check_driver_fatigue("driver_001", current_time)
    print_json(fatigue_check)

    if fatigue_check.get("fatigue_risk") == "critical":
        print("Critical fatigue correctly identified (hours > 11)")

    print("\nRiskMonitorAgent test complete")


if __name__ == "__main__":
    asyncio.run(test_risk_monitor())
