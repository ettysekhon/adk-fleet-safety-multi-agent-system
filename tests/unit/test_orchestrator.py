"""
Unit tests for FleetSafetyOrchestrator.
Tests the orchestrator's tools and agent registration (not LLM behaviour).
"""

import pytest

from app.agents.fleet_safety.analytics_agent import AnalyticsAgent
from app.agents.fleet_safety.dynamic_rerouter_agent import DynamicRerouterAgent
from app.agents.fleet_safety.orchestrator import FleetSafetyOrchestrator
from app.agents.fleet_safety.risk_monitor_agent import RiskMonitorAgent
from app.agents.fleet_safety.route_planner_agent import RoutePlannerAgent
from app.agents.fleet_safety.safety_scorer_agent import SafetyScorerAgent


class MockMCPClient:
    """Mock MCP client for unit testing without real Google Maps calls."""

    async def call_tool(self, server_name, tool_name, arguments):
        return "{}"


@pytest.mark.asyncio
async def test_orchestrator_init():
    """Test orchestrator initializes correctly."""
    orchestrator = FleetSafetyOrchestrator()

    assert orchestrator.name == "fleet_safety_orchestrator"
    assert orchestrator.model == "gemini-2.5-flash"
    assert "vehicles" in orchestrator.fleet_state
    assert "drivers" in orchestrator.fleet_state
    assert "active_trips" in orchestrator.fleet_state
    assert "alerts" in orchestrator.fleet_state


@pytest.mark.asyncio
async def test_register_agents():
    """Test that specialist agents can be registered."""
    orchestrator = FleetSafetyOrchestrator()
    mock_client = MockMCPClient()

    # Create specialist agents
    route_planner = RoutePlannerAgent(mcp_client=mock_client)
    safety_scorer = SafetyScorerAgent(mcp_client=mock_client)
    risk_monitor = RiskMonitorAgent(mcp_client=mock_client)
    analytics = AnalyticsAgent(mcp_client=mock_client)
    rerouter = DynamicRerouterAgent(mcp_client=mock_client)

    initial_tool_count = len(orchestrator.tools)

    # Register agents
    orchestrator.register_agents(
        {
            "route_planner": route_planner,
            "safety_scorer": safety_scorer,
            "risk_monitor": risk_monitor,
            "analytics": analytics,
            "rerouter": rerouter,
        }
    )

    # Verify agents are stored
    assert orchestrator.route_planner is route_planner
    assert orchestrator.safety_scorer is safety_scorer
    assert orchestrator.risk_monitor is risk_monitor
    assert orchestrator.analytics is analytics
    assert orchestrator.rerouter is rerouter

    # Verify AgentTools were added (5 new tools)
    assert len(orchestrator.tools) == initial_tool_count + 5


@pytest.mark.asyncio
async def test_get_fleet_status():
    """Test fleet status retrieval."""
    orchestrator = FleetSafetyOrchestrator()

    # Add test data
    orchestrator.fleet_state["vehicles"]["v001"] = {
        "id": "v001",
        "type": "Heavy Truck",
        "status": "active",
    }
    orchestrator.fleet_state["vehicles"]["v002"] = {
        "id": "v002",
        "type": "Van",
        "status": "inactive",
    }

    status = await orchestrator.get_fleet_status()

    assert status["fleet_size"] == 2
    assert status["active_vehicles"] == 1
    assert "timestamp" in status
    assert "system_health" in status


@pytest.mark.asyncio
async def test_get_fleet_status_with_details():
    """Test fleet status with detailed info."""
    orchestrator = FleetSafetyOrchestrator()

    orchestrator.fleet_state["vehicles"]["v001"] = {
        "id": "v001",
        "type": "Heavy Truck",
        "status": "active",
    }

    status = await orchestrator.get_fleet_status(include_details=True)

    assert "vehicles" in status
    assert len(status["vehicles"]) == 1


@pytest.mark.asyncio
async def test_get_vehicle_info():
    """Test vehicle info retrieval."""
    orchestrator = FleetSafetyOrchestrator()

    orchestrator.fleet_state["vehicles"]["v001"] = {
        "id": "v001",
        "type": "Heavy Truck",
        "status": "active",
        "fuel_type": "diesel",
    }

    # Existing vehicle
    info = await orchestrator.get_vehicle_info("v001")
    assert info["id"] == "v001"
    assert info["type"] == "Heavy Truck"

    # Non-existent vehicle
    info = await orchestrator.get_vehicle_info("v999")
    assert "error" in info


@pytest.mark.asyncio
async def test_get_driver_info():
    """Test driver info retrieval."""
    orchestrator = FleetSafetyOrchestrator()

    orchestrator.fleet_state["drivers"]["d001"] = {
        "id": "d001",
        "name": "John Smith",
        "experience_years": 5,
    }

    # Existing driver
    info = await orchestrator.get_driver_info("d001")
    assert info["id"] == "d001"
    assert info["name"] == "John Smith"

    # Non-existent driver
    info = await orchestrator.get_driver_info("d999")
    assert "error" in info


@pytest.mark.asyncio
async def test_generate_executive_dashboard():
    """Test executive dashboard generation."""
    orchestrator = FleetSafetyOrchestrator()

    # Add some test data
    orchestrator.fleet_state["vehicles"]["v001"] = {"id": "v001", "status": "active"}
    orchestrator.fleet_state["alerts"].append(
        {"id": "a001", "status": "active", "priority": "high"}
    )

    dashboard = await orchestrator.generate_executive_dashboard()

    assert "generated_at" in dashboard
    assert "fleet_overview" in dashboard
    assert "key_metrics" in dashboard
    assert "recommendations" in dashboard
    assert "system_health" in dashboard


@pytest.mark.asyncio
async def test_coordinate_emergency_response():
    """Test emergency response coordination."""
    orchestrator = FleetSafetyOrchestrator()

    # Add alert
    orchestrator.fleet_state["alerts"].append(
        {
            "id": "alert_001",
            "status": "active",
            "priority": "critical",
            "vehicle_id": "v001",
            "description": "Test emergency",
        }
    )

    # Test immediate stop response
    response = await orchestrator.coordinate_emergency_response(
        alert_id="alert_001", response_type="immediate_stop"
    )

    assert response["alert_id"] == "alert_001"
    assert response["response_type"] == "immediate_stop"
    assert len(response["actions_taken"]) > 0

    # Test non-existent alert
    response = await orchestrator.coordinate_emergency_response(
        alert_id="fake_alert", response_type="immediate_stop"
    )
    assert "error" in response
