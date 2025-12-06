"""
Fleet Safety Command Center - Orchestrator Agent
Coordinates all other agents using ADK's multi-agent patterns
"""

from datetime import datetime
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools import load_memory
from google.adk.tools.agent_tool import AgentTool

from app.helpers.weather import get_live_weather


class FleetSafetyOrchestrator(LlmAgent):
    """
    Central command agent that coordinates all fleet safety operations.

    Uses ADK's AgentTool pattern to delegate to specialist agents,
    ensuring proper tracing and multi-agent visibility.
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
            2. Coordinate specialist agents using the available tools
            3. Make final safety decisions when agents provide conflicting recommendations
            4. Generate executive summaries and dashboards
            5. Prioritize actions based on urgency and impact

            SPECIALIST AGENTS (use these tools to delegate tasks):
            - route_planner_agent: For route planning - generates multiple route options
            - safety_scorer_agent: For safety scoring - evaluates route safety (0-100 score)
            - risk_monitor_agent: For real-time safety monitoring and risk assessment
            - analytics_agent: For historical analysis and predictions
            - rerouter_agent: For dynamic re-routing of active trips

            WORKFLOW FOR ROUTE PLANNING REQUESTS:
            1. First, use get_fleet_status to check vehicle and driver info
            2. Call route_planner_agent with origin, destination, vehicle type
            3. For EACH route returned, call safety_scorer_agent to get safety scores
            4. Compare scores and recommend the safest route with rationale
            5. Include risk factors and mitigation recommendations in your response

            Decision Framework:
            CRITICAL PRIORITY: Immediate safety threats (active trip hazards)
            HIGH PRIORITY: Near-term risks (route planning with safety concerns)
            MEDIUM PRIORITY: Optimization opportunities (better routes available)
            LOW PRIORITY: Analytics and reporting

            Always explain your reasoning and which agents you consulted.
            Format your responses clearly with sections for:
            - Recommended Route
            - Safety Score and Risk Level
            - Top Risk Factors
            - Recommendations
            """,
            tools=[
                self.get_fleet_status,
                self.get_vehicle_info,
                self.get_driver_info,
                self.get_weather_conditions,
                self.generate_executive_dashboard,
                self.coordinate_emergency_response,
                load_memory,
            ],
        )

        self.fleet_state = {"vehicles": {}, "drivers": {}, "active_trips": {}, "alerts": []}

        # Sub-agent references (set via register_agents)
        self.risk_monitor = None
        self.route_planner = None
        self.safety_scorer = None
        self.rerouter = None
        self.analytics = None

    def register_agents(self, agents: dict[str, LlmAgent]):
        """
        Register specialist agents and add them as AgentTools.
        This enables proper ADK multi-agent tracing.
        """
        self.risk_monitor = agents.get("risk_monitor")
        self.route_planner = agents.get("route_planner")
        self.safety_scorer = agents.get("safety_scorer")
        self.rerouter = agents.get("rerouter")
        self.analytics = agents.get("analytics")

        # Add specialist agents as tools using AgentTool
        agent_tools = []

        if self.route_planner:
            agent_tools.append(
                AgentTool(
                    agent=self.route_planner,
                    skip_summarization=True,  # Return raw output for processing
                )
            )

        if self.safety_scorer:
            agent_tools.append(
                AgentTool(
                    agent=self.safety_scorer,
                    skip_summarization=True,
                )
            )

        if self.risk_monitor:
            agent_tools.append(
                AgentTool(
                    agent=self.risk_monitor,
                    skip_summarization=True,
                )
            )

        if self.analytics:
            agent_tools.append(
                AgentTool(
                    agent=self.analytics,
                    skip_summarization=True,
                )
            )

        if self.rerouter:
            agent_tools.append(
                AgentTool(
                    agent=self.rerouter,
                    skip_summarization=True,
                )
            )

        # Extend the existing tools with agent tools
        self.tools = list(self.tools) + agent_tools

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

    async def get_vehicle_info(self, vehicle_id: str) -> dict:
        """
        Get detailed information about a specific vehicle.

        Args:
            vehicle_id: The ID of the vehicle (e.g., 'v001')

        Returns vehicle details including type, status, and capabilities.
        """
        vehicle = self.fleet_state["vehicles"].get(vehicle_id)
        if not vehicle:
            return {"error": f"Vehicle {vehicle_id} not found in fleet"}
        return vehicle

    async def get_driver_info(self, driver_id: str) -> dict:
        """
        Get detailed information about a specific driver.

        Args:
            driver_id: The ID of the driver (e.g., 'd001')

        Returns driver profile including experience and safety record.
        """
        driver = self.fleet_state["drivers"].get(driver_id)
        if not driver:
            return {"error": f"Driver {driver_id} not found"}
        return driver

    async def get_weather_conditions(self, location: str) -> dict:
        """
        Get current weather conditions for a location.

        Args:
            location: Address or coordinates for weather lookup

        Returns current weather including temperature, conditions, and wind.
        """
        mcp_client = getattr(self.route_planner, "mcp_client", None)
        return await get_live_weather(location, mcp_client=mcp_client)

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
        fleet_status = await self.get_fleet_status(include_details=True)

        analytics_summary = {}
        if self.analytics:
            analytics_summary = await self.analytics.generate_summary(time_period)

        total_trips = fleet_status.get("active_trips", 0)
        incident_rate = (
            analytics_summary.get("incident_count", 0) / total_trips if total_trips > 0 else 0
        )

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

        recommendations = []
        if fleet_status["critical_alerts"] > 0:
            recommendations.append(
                {
                    "priority": "critical",
                    "action": "Review critical alerts immediately",
                    "details": f"{fleet_status['critical_alerts']} critical alerts require attention",
                }
            )

        if incident_rate > 0.05:
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

        Args:
            alert_id: ID of the alert to respond to
            response_type: Type of response ('immediate_stop', 'reroute', 'dispatch_assistance')

        Actions:
        - Alert driver
        - Notify manager
        - Trigger re-routing if needed
        - Dispatch assistance
        """
        alert = next((a for a in self.fleet_state["alerts"] if a.get("id") == alert_id), None)

        if not alert:
            return {"error": "Alert not found", "alert_id": alert_id}

        actions_taken = []

        if response_type == "immediate_stop":
            actions_taken.append(
                {
                    "action": "driver_alert",
                    "status": "sent",
                    "message": "CRITICAL: Pull over safely and contact dispatch immediately",
                }
            )
            actions_taken.append(
                {"action": "manager_notification", "status": "sent", "priority": "critical"}
            )

        elif response_type == "reroute":
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
            actions_taken.append(
                {"action": "dispatch_assistance", "status": "requested", "eta": "15-30 minutes"}
            )

        alert["status"] = "responding"
        alert["response_initiated"] = datetime.now().isoformat()

        return {
            "alert_id": alert_id,
            "response_type": response_type,
            "actions_taken": actions_taken,
            "timestamp": datetime.now().isoformat(),
        }
