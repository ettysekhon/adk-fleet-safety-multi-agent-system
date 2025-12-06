"""
Risk Monitor Agent - Real-time fleet safety monitoring and intervention
"""

from datetime import datetime, timedelta
from typing import Any

from google.adk.agents import LlmAgent


class RiskMonitorAgent(LlmAgent):
    """
    Continuously monitors fleet for safety risks.
    """

    mcp_client: Any = None
    active_alerts: dict = {}
    memory_bank: dict = {}  # Internal memory simulation

    def __init__(self, mcp_client):
        super().__init__(
            model="gemini-2.5-flash",
            name="risk_monitor_agent",
            description="Real-time fleet safety monitoring that detects speeding, harsh braking, fatigue, and other safety risks from vehicle telemetry data.",
            instruction="""You are a real-time fleet safety monitor. When queried, analyze vehicle telemetry and detect safety risks:

            HIGH RISK (immediate intervention):
            - Harsh braking/acceleration (>0.4g)
            - Speeding >15mph over limit
            - Distracted driving indicators
            - Following distance <2 seconds
            - Fatigue indicators (hours driven, time of day)

            MEDIUM RISK (log and track):
            - Speeding 5-15mph over limit
            - Frequent lane changes
            - Hard cornering

            LOW RISK (baseline tracking):
            - Minor speed variations
            - Normal driving patterns

            For each risk detected, calculate severity score and recommend intervention.
            """,
            tools=[
                self.analyze_telemetry,
                self.calculate_risk_score,
                self.check_driver_fatigue,
                self.get_route_hazards,
            ],
        )
        self.mcp_client = mcp_client
        self.active_alerts = {}
        self.memory_bank = {
            "fleet_risk_patterns": {},
            "driver_shifts": {},  # Store shift start, last break
        }

    async def analyze_telemetry(self, vehicle_id: str, telemetry: dict) -> dict:
        """
        Analyses real-time vehicle telemetry for safety risks.

        Telemetry includes:
        - speed, acceleration, braking force
        - GPS location, heading
        - engine data, fuel level
        - driver ID, shift hours
        """
        risks = []

        # Check speed vs limit
        speed_limit = telemetry.get("speed_limit", 70)
        current_speed = telemetry["speed"]

        if current_speed > speed_limit + 15:
            risks.append(
                {
                    "type": "excessive_speeding",
                    "severity": "high",
                    "details": f"Speed {current_speed}mph in {speed_limit}mph zone",
                }
            )
        elif current_speed > speed_limit + 5:
            risks.append(
                {
                    "type": "speeding",
                    "severity": "medium",
                    "details": f"Speed {current_speed}mph in {speed_limit}mph zone",
                }
            )

        # Check acceleration/braking
        accel = abs(telemetry.get("acceleration", 0))
        if accel > 0.4:  # 0.4g threshold
            event_type = "harsh_braking" if telemetry["acceleration"] < 0 else "harsh_acceleration"
            risks.append(
                {"type": event_type, "severity": "high", "details": f"Force: {accel:.2f}g"}
            )

        # Check following distance (if available)
        following_distance = telemetry.get("following_distance_seconds")
        if following_distance and following_distance < 2.0:
            risks.append(
                {
                    "type": "unsafe_following",
                    "severity": "high",
                    "details": f"Following distance: {following_distance:.1f}s (minimum 2s)",
                }
            )

        return {
            "vehicle_id": vehicle_id,
            "timestamp": datetime.now().isoformat(),
            "risks_detected": len(risks) > 0,
            "risks": risks,
            "requires_intervention": any(r["severity"] == "high" for r in risks),
        }

    async def calculate_risk_score(self, vehicle_id: str, recent_events: list[dict]) -> dict:
        """
        Calculates composite risk score based on recent events.
        """
        # Base score
        risk_score = 0

        # Weight recent events
        for event in recent_events:
            event_time = datetime.fromisoformat(event["timestamp"])
            age_minutes = (datetime.now() - event_time).total_seconds() / 60
            decay_factor = max(0, 1 - (age_minutes / 30))  # Decay over 30 minutes

            severity_weights = {"high": 10, "medium": 5, "low": 1}
            for risk in event.get("risks", []):
                risk_score += severity_weights.get(risk["severity"], 1) * decay_factor

        # Check against historical patterns
        historical_avg = self.memory_bank["fleet_risk_patterns"].get(f"avg_risk_score_{vehicle_id}")
        deviation = 0
        if historical_avg:
            deviation = (risk_score - historical_avg) / historical_avg if historical_avg > 0 else 0
            if deviation > 0.5:  # 50% worse than average
                risk_score *= 1.2  # Amplify score

        # Update historical average (mock update)
        self.memory_bank["fleet_risk_patterns"][f"avg_risk_score_{vehicle_id}"] = (
            risk_score * 0.1 + (historical_avg or 0) * 0.9
        )

        return {
            "vehicle_id": vehicle_id,
            "risk_score": round(risk_score, 1),
            "risk_level": "critical"
            if risk_score > 30
            else "high"
            if risk_score > 15
            else "medium"
            if risk_score > 5
            else "low",
            "deviation_from_average": round(deviation, 2) if historical_avg else None,
        }

    async def check_driver_fatigue(self, driver_id: str, current_time: str = None) -> dict:
        """
        Checks if driver is at risk of fatigue.
        """
        now = datetime.fromisoformat(current_time) if current_time else datetime.now()

        # Get driver's shift data from memory
        shift_data = self.memory_bank["driver_shifts"].get(driver_id, {})
        shift_start = shift_data.get("shift_start")
        last_break = shift_data.get("last_break")
        consecutive_days = shift_data.get("consecutive_days", 0)

        if not shift_start:
            # Initialise shift if not present for demo
            shift_start = (now - timedelta(hours=2)).isoformat()
            self.memory_bank["driver_shifts"][driver_id] = {
                "shift_start": shift_start,
                "last_break": None,
                "consecutive_days": 3,
            }
            # return {'fatigue_risk': 'unknown', 'reason': 'No shift data available'}

        shift_start_dt = datetime.fromisoformat(shift_start)
        hours_driven = (now - shift_start_dt).total_seconds() / 3600

        # Check against HOS (Hours of Service) regulations
        if hours_driven > 11:
            return {
                "fatigue_risk": "critical",
                "reason": f"Driver has been driving for {hours_driven:.1f} hours (max 11)",
                "action": "require_immediate_rest",
            }

        # Check time since last break
        time_since_break = None
        if last_break:
            last_break_dt = datetime.fromisoformat(last_break)
            time_since_break = (now - last_break_dt).total_seconds() / 3600
            if time_since_break > 5:  # 5 hours without break
                return {
                    "fatigue_risk": "high",
                    "reason": f"{time_since_break:.1f} hours since last break",
                    "action": "recommend_break",
                }

        # Check time of day (circadian lows: 2-6am, 2-4pm)
        hour = now.hour
        if 2 <= hour <= 6:
            return {
                "fatigue_risk": "high",
                "reason": "Circadian low period (2-6am)",
                "action": "increase_monitoring",
            }

        # Check consecutive days
        if consecutive_days > 6:
            return {
                "fatigue_risk": "medium",
                "reason": f"{consecutive_days} consecutive days worked",
                "action": "monitor_closely",
            }

        return {
            "fatigue_risk": "low",
            "hours_driven": round(hours_driven, 1),
            "time_since_break": round(time_since_break, 1) if time_since_break else None,
        }

    async def get_route_hazards(
        self, current_location: dict, destination: dict, weather_conditions: dict
    ) -> dict:
        """
        Identifies hazards along route.
        Integrates with traffic and weather APIs.
        """
        hazards = []

        # Check weather hazards
        if weather_conditions.get("conditions") in ["rain", "snow", "ice", "fog"]:
            hazards.append(
                {
                    "type": "weather",
                    "severity": "high"
                    if weather_conditions["conditions"] in ["snow", "ice"]
                    else "medium",
                    "description": f"Adverse weather: {weather_conditions['conditions']}",
                    "recommendation": "Reduce speed, increase following distance",
                }
            )

        # Simulate traffic/historical hazards (since we don't have traffic_api tool yet)
        # In real scenario: await self.mcp_client.call_tool('traffic_api', ...)

        # Simple logic based on location for demo
        if isinstance(current_location, dict):
            # Assume urban area if coordinates imply city center (mock)
            pass

        return {
            "hazard_count": len(hazards),
            "hazards": hazards,
            "route_risk_level": "high"
            if any(h["severity"] == "high" for h in hazards)
            else "medium"
            if hazards
            else "low",
        }

    async def get_vehicle_risk_status(self, vehicle_id: str) -> dict:
        """
        Get current risk status for a vehicle.
        Used by Orchestrator.
        """
        historical_avg = self.memory_bank["fleet_risk_patterns"].get(
            f"avg_risk_score_{vehicle_id}", 0
        )

        # In a real system, this would check active alerts and recent telemetry
        # Here we simulate based on stored patterns or mock active state

        current_score = historical_avg  # Simplified: current score is recent average

        return {
            "vehicle_id": vehicle_id,
            "risk_score": round(current_score, 1),
            "risk_level": "high"
            if current_score > 15
            else "medium"
            if current_score > 5
            else "low",
            "last_updated": datetime.now().isoformat(),
        }


class InterventionAgent(LlmAgent):
    """
    Determines and executes safety interventions.
    """

    mcp_client: Any = None

    def __init__(self, mcp_client):
        super().__init__(
            model="gemini-2.5-flash",
            name="intervention_agent",
            description="Safety intervention decision and execution",
            instruction="""When a safety risk is detected, determine appropriate intervention:

            CRITICAL RISKS (immediate action):
            1. Send real-time alert to driver (in-cab display, audio warning)
            2. Notify fleet manager immediately
            3. If risk persists >30 seconds, escalate to emergency protocol

            HIGH RISKS:
            1. Alert driver with specific guidance
            2. Log incident for manager review
            3. If pattern detected (3+ in hour), notify manager

            MEDIUM RISKS:
            1. Log for later analysis
            2. Include in daily driver report

            Consider:
            - Driver's safety record
            - Context (emergency vehicle? medical transport?)
            - False positive rate for this risk type
            """,
            tools=[
                self.alert_driver,
                self.notify_manager,
                self.suggest_route_change,
            ],
        )
        self.mcp_client = mcp_client

    async def alert_driver(
        self,
        vehicle_id: str,
        driver_id: str,
        alert_type: str,
        message: str,
        urgency: str,
    ) -> dict:
        """
        Sends alert to driver through in-vehicle system.
        """
        # TODO: Use MCP tool to send alert via fleet management API
        # Simulated response
        print(f"ALERT SENT to {vehicle_id} ({urgency}): {message}")

        return {
            "alert_sent": True,
            "delivery_time": datetime.now().isoformat(),
            "acknowledged": False,
        }

    async def notify_manager(
        self,
        driver_id: str,
        vehicle_id: str,
        incident_summary: dict,
        priority: str,
    ) -> dict:
        """
        Notifies fleet manager of safety incident.
        """
        # Build notification
        notification = {
            "type": "safety_incident",
            "priority": priority,
            "driver_id": driver_id,
            "vehicle_id": vehicle_id,
            "timestamp": datetime.now().isoformat(),
            "incident": incident_summary,
            "requires_action": priority in ["critical", "high"],
        }

        # Simulated sending
        # TODO: Integrate with fleet management notification system using `notification` object
        print(
            f"MANAGER NOTIFIED ({priority}): {incident_summary.get('type', 'Incident')} - Data: {notification}"
        )

        return {
            "notification_sent": True,
            "channels": {"email": True, "sms": priority == "critical"},
            "timestamp": datetime.now().isoformat(),
        }

    async def suggest_route_change(
        self,
        vehicle_id: str,
        current_route: dict,
        hazard_location: dict,
        reason: str,
    ) -> dict:
        """
        Suggests alternative route to avoid hazard.
        """
        # Simulated route change suggestion
        # Real impl would use RoutePlannerAgent or MCP

        return {
            "alternative_available": True,
            "route": {"summary": "Alternative Route B"},
            "time_impact_minutes": 5,
            "distance_impact_miles": 2.5,
            "safety_improvement": 20,
            "recommendation": "strongly_recommended",
        }
