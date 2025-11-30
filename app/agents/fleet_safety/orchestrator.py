"""
Fleet Safety Command Center - Orchestrator Agent
Coordinates all other agents and maintains system state
"""

import asyncio
from datetime import datetime
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools import load_memory

from app.helpers.weather import get_live_weather


class FleetSafetyOrchestrator(LlmAgent):
    """
    Central command agent that coordinates all fleet safety operations.

    Responsibilities:
    - Maintain fleet state (vehicle locations, driver assignments)
    - Route requests to appropriate specialist agents
    - Aggregate insights from multiple agents
    - Make final safety decisions
    - Generate executive dashboards
    """

    fleet_state: dict = {}
    risk_monitor: Any = None
    route_planner: Any = None
    safety_scorer: Any = None
    rerouter: Any = None
    analytics: Any = None

    def __init__(self):
        super().__init__(
            model="gemini-2.5-flash",
            name="fleet_safety_orchestrator",
            description="Central coordinator for fleet safety operations",
            instruction="""You are the Fleet Safety Command Center orchestrator.

            Your role:
            1. Maintain awareness of entire fleet status (including EV/Hybrid vehicles)
            2. Coordinate specialist agents (Risk Monitor, Route Planner, etc.)
            3. Make final safety decisions when agents provide conflicting recommendations
            4. Generate executive summaries and dashboards
            5. Prioritize actions based on urgency and impact

            Memory & Context:
            - Use the `load_memory` tool to recall past fleet decisions or context if needed.

            Agent Coordination:
            - Risk Monitor: Real-time safety monitoring (loop agent, always running)
            - Route Planner: Creates optimized routes (sequential, on-demand)
            - Safety Scorer: Evaluates route safety (parallel, batch processing)
            - Dynamic Rerouter: Adjusts active trips (loop agent, event-driven)
            - Analytics: Historical analysis and predictions (batch, scheduled)

            Decision Framework:
            CRITICAL PRIORITY: Immediate safety threats (active trip hazards)
            HIGH PRIORITY: Near-term risks (route planning with safety concerns)
            MEDIUM PRIORITY: Optimization opportunities (better routes available)
            LOW PRIORITY: Analytics and reporting

            Always explain your reasoning and which agents you're consulting.
            """,
            tools=[
                self.get_fleet_status,
                self.request_route_plan,
                self.check_vehicle_safety,
                self.generate_executive_dashboard,
                self.coordinate_emergency_response,
                load_memory,
            ],
        )

        # Maintain fleet state
        self.fleet_state = {"vehicles": {}, "drivers": {}, "active_trips": {}, "alerts": []}

        # References to specialist agents
        self.risk_monitor = None
        self.route_planner = None
        self.safety_scorer = None
        self.rerouter = None
        self.analytics = None

    def register_agents(self, agents: dict[str, LlmAgent]):
        """Register specialist agents for coordination"""
        self.risk_monitor = agents.get("risk_monitor")
        self.route_planner = agents.get("route_planner")
        self.safety_scorer = agents.get("safety_scorer")
        self.rerouter = agents.get("rerouter")
        self.analytics = agents.get("analytics")

    async def get_fleet_status(self, include_details: bool = False) -> dict:
        """
        Get current status of entire fleet.

        Returns:
        - Vehicle count and locations
        - Active trip count
        - Active alert count
        - System health
        """
        active_vehicles = len(
            [v for v in self.fleet_state["vehicles"].values() if v.get("status") == "active"]
        )

        active_trips = len(self.fleet_state["active_trips"])

        active_alerts = len([a for a in self.fleet_state["alerts"] if a.get("status") == "active"])

        critical_alerts = len(
            [
                a
                for a in self.fleet_state["alerts"]
                if a.get("priority") == "critical" and a.get("status") == "active"
            ]
        )

        status = {
            "timestamp": datetime.now().isoformat(),
            "fleet_size": len(self.fleet_state["vehicles"]),
            "active_vehicles": active_vehicles,
            "active_trips": active_trips,
            "total_alerts": active_alerts,
            "critical_alerts": critical_alerts,
            "system_health": "critical"
            if critical_alerts > 0
            else "warning"
            if active_alerts > 5
            else "good",
        }

        if include_details:
            status["vehicles"] = list(self.fleet_state["vehicles"].values())
            status["active_trips_details"] = list(self.fleet_state["active_trips"].values())
            status["alerts"] = [
                a for a in self.fleet_state["alerts"] if a.get("status") == "active"
            ]

        return status

    async def request_route_plan(
        self,
        origin: str,
        destination: str,
        driver_id: str,
        vehicle_id: str,
        departure_time: str | None = None,
        priority: str = "safety",
    ) -> dict:
        """
        Request comprehensive route plan from Route Planner and Safety Scorer agents.

        Workflow:
        1. Route Planner generates 3-5 route options
        2. Safety Scorer evaluates each route in parallel
        3. Orchestrator selects best route based on priority
        4. Return recommendation with rationale
        """
        if not self.route_planner or not self.safety_scorer:
            return {"error": "Required agents not registered", "status": "failed"}

        # Get vehicle details
        vehicle = self.fleet_state["vehicles"].get(vehicle_id, {})
        vehicle_type = vehicle.get("type", "truck")

        # Step 1: Get route options from Route Planner
        # Ensure departure_time is a valid ISO string
        if not departure_time or departure_time.lower() == "now":
            departure_time = datetime.now().isoformat()

        route_request = {
            "origin": origin,
            "destination": destination,
            "vehicle_type": vehicle_type,
            "driver_profile": self.fleet_state["drivers"].get(driver_id, {}),
            "departure_time": departure_time,
        }

        route_options = await self.route_planner.generate_route_options(route_request)

        if not route_options or not route_options.get("routes"):
            return {"error": "No routes found", "status": "failed"}

        # Fetch live weather once for the origin location
        # Use route_planner's mcp_client for geocoding if needed
        mcp_client = getattr(self.route_planner, "mcp_client", None)
        live_weather = await get_live_weather(origin, mcp_client=mcp_client)

        # Step 2: Score each route in parallel (using Safety Scorer)
        scoring_tasks = []
        for route in route_options["routes"]:
            # Combine live weather with time-based conditions
            current_conditions = {
                "time_of_day": datetime.now().hour,
                "day_of_week": datetime.now().weekday(),
                "condition": live_weather["condition"],
                "temperature_c": live_weather["temperature_c"],
                "wind_speed_kmh": live_weather["wind_speed_kmh"],
                "is_day": live_weather["is_day"],
            }
            task = self.safety_scorer.score_route(
                route=route,
                driver_profile=route_request["driver_profile"],
                current_conditions=current_conditions,
                vehicle_config=vehicle,  # Pass full vehicle config including type
            )
            scoring_tasks.append(task)

        # Execute scoring in parallel
        scored_routes = await asyncio.gather(*scoring_tasks)

        # Step 3: Combine route data with safety scores
        for i, route in enumerate(route_options["routes"]):
            route["safety_analysis"] = scored_routes[i]

        # Step 4: Select best route based on priority
        if priority == "safety":
            # Prioritize safety score
            best_route = max(
                route_options["routes"], key=lambda r: r["safety_analysis"]["safety_score"]
            )
            selection_criteria = "highest safety score"
        elif priority == "speed":
            # Prioritize travel time, but require minimum safety threshold
            eligible_routes = [
                r
                for r in route_options["routes"]
                if r["safety_analysis"]["safety_score"] >= 70  # Minimum safety threshold
            ]
            if eligible_routes:
                best_route = min(eligible_routes, key=lambda r: r["estimated_duration_minutes"])
                selection_criteria = "fastest time with acceptable safety (score ≥70)"
            else:
                # All routes below safety threshold, pick safest
                best_route = max(
                    route_options["routes"], key=lambda r: r["safety_analysis"]["safety_score"]
                )
                selection_criteria = "safest available (all routes below minimum threshold)"
        else:  # balanced
            # Balance safety and time
            best_route = min(
                route_options["routes"],
                key=lambda r: (100 - r["safety_analysis"]["safety_score"])
                + (r["estimated_duration_minutes"] / 10),
            )
            selection_criteria = "best balance of safety and efficiency"

        return {
            "status": "success",
            "recommended_route": best_route,
            "selection_criteria": selection_criteria,
            "alternative_routes": [r for r in route_options["routes"] if r != best_route],
            "route_comparison": self._generate_route_comparison(route_options["routes"]),
            "timestamp": datetime.now().isoformat(),
        }

    async def check_vehicle_safety(self, vehicle_id: str) -> dict:
        """
        Get comprehensive safety status for a vehicle.

        Queries:
        - Risk Monitor for current risk level
        - Analytics for historical safety record
        - Active alerts for this vehicle
        """
        if not self.risk_monitor:
            return {"error": "Risk Monitor not available"}

        # Get current risk assessment
        current_risk = await self.risk_monitor.get_vehicle_risk_status(vehicle_id)

        # Get active alerts
        vehicle_alerts = [
            a
            for a in self.fleet_state["alerts"]
            if a.get("vehicle_id") == vehicle_id and a.get("status") == "active"
        ]

        # Get historical data from analytics if available
        historical_data = {}
        if self.analytics:
            historical_data = await self.analytics.get_vehicle_safety_history(vehicle_id, days=30)

        return {
            "vehicle_id": vehicle_id,
            "current_risk_level": current_risk.get("risk_level", "unknown"),
            "current_risk_score": current_risk.get("risk_score", 0),
            "active_alerts": vehicle_alerts,
            "alert_count": len(vehicle_alerts),
            "historical_incidents": historical_data.get("incident_count", 0),
            "safety_rating": historical_data.get("safety_rating", "N/A"),
            "timestamp": datetime.now().isoformat(),
        }

    async def generate_executive_dashboard(self, time_period: str = "today") -> dict:
        """
        Generate executive dashboard aggregating all system insights.

        Includes:
        - Fleet status overview
        - Key safety metrics
        - Active incidents
        - Trends and predictions
        - Recommended actions
        """
        # Get fleet status
        fleet_status = await self.get_fleet_status(include_details=True)

        # Get analytics summary
        analytics_summary = {}
        if self.analytics:
            analytics_summary = await self.analytics.generate_summary(time_period)

        # Calculate key metrics
        total_trips = fleet_status.get("active_trips", 0)
        incident_rate = (
            analytics_summary.get("incident_count", 0) / total_trips if total_trips > 0 else 0
        )

        # Identify trends
        trends = []
        if analytics_summary.get("incident_count", 0) > analytics_summary.get(
            "previous_period_incidents", 0
        ):
            trends.append(
                {
                    "trend": "increasing_incidents",
                    "severity": "warning",
                    "description": f"Incidents up {analytics_summary['incident_count'] - analytics_summary.get('previous_period_incidents', 0)} vs previous period",
                }
            )

        # Generate recommendations
        recommendations = []
        if fleet_status["critical_alerts"] > 0:
            recommendations.append(
                {
                    "priority": "critical",
                    "action": "Review critical alerts immediately",
                    "details": f"{fleet_status['critical_alerts']} critical alerts require attention",
                }
            )

        if incident_rate > 0.05:  # More than 5% of trips had incidents
            recommendations.append(
                {
                    "priority": "high",
                    "action": "Investigate incident spike",
                    "details": f"Incident rate at {incident_rate * 100:.1f}% (target: <5%)",
                }
            )

        return {
            "generated_at": datetime.now().isoformat(),
            "time_period": time_period,
            "fleet_overview": fleet_status,
            "key_metrics": {
                "total_trips": total_trips,
                "incident_count": analytics_summary.get("incident_count", 0),
                "incident_rate": f"{incident_rate * 100:.2f}%",
                "average_safety_score": analytics_summary.get("avg_safety_score", 0),
                "on_time_delivery_rate": analytics_summary.get("on_time_rate", 0),
            },
            "trends": trends,
            "recommendations": recommendations,
            "system_health": fleet_status["system_health"],
        }

    async def coordinate_emergency_response(self, alert_id: str, response_type: str) -> dict:
        """
        Coordinate emergency response to critical alerts.

        Actions:
        - Alert driver
        - Notify manager
        - Trigger re-routing if needed
        - Dispatch assistance
        """
        # Find alert
        alert = next((a for a in self.fleet_state["alerts"] if a.get("id") == alert_id), None)

        if not alert:
            return {"error": "Alert not found", "alert_id": alert_id}

        actions_taken = []

        if response_type == "immediate_stop":
            # Contact driver immediately
            actions_taken.append(
                {
                    "action": "driver_alert",
                    "status": "sent",
                    "message": "CRITICAL: Pull over safely and contact dispatch immediately",
                }
            )

            # Notify manager
            actions_taken.append(
                {"action": "manager_notification", "status": "sent", "priority": "critical"}
            )

        elif response_type == "reroute":
            # Trigger dynamic re-routing
            if self.rerouter and alert.get("vehicle_id"):
                reroute_result = await self.rerouter.emergency_reroute(
                    vehicle_id=alert["vehicle_id"],
                    reason=alert.get("description", "Emergency reroute"),
                )
                actions_taken.append(
                    {
                        "action": "emergency_reroute",
                        "status": "completed" if reroute_result.get("success") else "failed",
                        "new_route": reroute_result.get("new_route"),
                    }
                )

        elif response_type == "dispatch_assistance":
            # Dispatch roadside assistance or emergency services
            actions_taken.append(
                {"action": "dispatch_assistance", "status": "requested", "eta": "15-30 minutes"}
            )

        # Update alert status
        alert["status"] = "responding"
        alert["response_initiated"] = datetime.now().isoformat()

        return {
            "alert_id": alert_id,
            "response_type": response_type,
            "actions_taken": actions_taken,
            "timestamp": datetime.now().isoformat(),
        }

    def _generate_route_comparison(self, routes: list[dict]) -> dict:
        """Generate comparison matrix of route options"""
        if not routes:
            return {}

        comparison = {
            "safest_route": max(routes, key=lambda r: r["safety_analysis"]["safety_score"]),
            "fastest_route": min(routes, key=lambda r: r["estimated_duration_minutes"]),
            "shortest_route": min(routes, key=lambda r: r["distance_miles"]),
            "tradeoffs": [],
        }

        safest = comparison["safest_route"]
        fastest = comparison["fastest_route"]

        if safest != fastest:
            time_diff = safest["estimated_duration_minutes"] - fastest["estimated_duration_minutes"]
            safety_diff = (
                safest["safety_analysis"]["safety_score"]
                - fastest["safety_analysis"]["safety_score"]
            )

            comparison["tradeoffs"].append(
                {
                    "decision": "safety_vs_speed",
                    "safest_route_time_penalty_minutes": time_diff,
                    "safest_route_safety_advantage_points": safety_diff,
                    "recommendation": "Choose safest" if safety_diff > 20 else "Either acceptable",
                }
            )

        return comparison
