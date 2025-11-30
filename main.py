import asyncio
import sys

from app.agent import orchestrator


async def run_demo_scenario():
    """
    Runs the demo scenarios:
    1. Standard Route Planning (London to Manchester, Diesel Truck)
    2. Electric Fleet Planning (Cambridge to Edinburgh, Electric Van)
    """
    print("\nFLEET SAFETY INTELLIGENCE PLATFORM - CLI DEMO")
    print("============================================================")
    print("Initializing system...\n")

    # SCENARIO 1: Standard Diesel
    origin_1 = "London, UK"
    destination_1 = "Manchester, UK"
    driver_id_1 = "d001"
    vehicle_id_1 = "v001"  # Diesel Truck

    print(f"SCENARIO 1: Diesel Fleet Route ({origin_1} -> {destination_1})")
    print(f"   Driver: {driver_id_1}, Vehicle: {vehicle_id_1} (Diesel)")
    print("-" * 60)

    print("\nOrchestrator: Received request. Coordinating agents...")

    try:
        result = await orchestrator.request_route_plan(
            origin=origin_1,
            destination=destination_1,
            driver_id=driver_id_1,
            vehicle_id=vehicle_id_1,
            priority="safety",
        )
        display_result(result)

    except Exception as e:
        print(f"\nError running Scenario 1: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "-" * 60 + "\n")

    # SCENARIO 2: Electric Vehicle
    # First, let's ensure the system knows about an electric vehicle
    # Mocking adding an EV to the state if not present (Orchestrator stores this in memory)
    orchestrator.fleet_state["vehicles"]["v002"] = {
        "id": "v002",
        "type": "electric_van",
        "status": "active",
        "battery_level_pct": 85,
    }

    origin_2 = "Cambridge, UK"
    destination_2 = "Edinburgh, UK"  # Long distance to trigger charging stop logic
    driver_id_2 = "d002"
    vehicle_id_2 = "v002"  # Electric Van

    print(f"SCENARIO 2: Electric Fleet Route ({origin_2} -> {destination_2})")
    print(f"   Driver: {driver_id_2}, Vehicle: {vehicle_id_2} (Electric Van)")
    print("   Note: This is a long route likely requiring charging stops.")
    print("-" * 60)

    print("\nOrchestrator: Received request. Coordinating agents...")

    try:
        result = await orchestrator.request_route_plan(
            origin=origin_2,
            destination=destination_2,
            driver_id=driver_id_2,
            vehicle_id=vehicle_id_2,
            priority="balanced",  # Balance time/safety for EV
        )
        display_result(result)

    except Exception as e:
        print(f"\nError running Scenario 2: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 60)
    print("Demo Complete.")


def display_result(result):
    """Helper to print results nicely"""
    print("\nPLAN GENERATED")
    print("=" * 60)

    if result.get("status") == "success":
        rec = result["recommended_route"]
        print(f"Recommended Route: {rec.get('summary', 'Unknown')}")
        print(f" • Distance: {rec.get('distance_miles', 0):.1f} miles")
        print(f" • Duration: {rec.get('estimated_duration_minutes', 0):.0f} mins")

        # Fuel/Energy display
        cost_data = rec.get("fuel_cost", {})
        if cost_data.get("fuel_type") == "electric":
            print(f" • Energy: {cost_data.get('kwh_needed', 0)} kWh")
            print(f" • Cost: £{cost_data.get('total_energy_cost', 0):.2f}")
        else:
            print(f" • Fuel: {cost_data.get('litres_needed', 0)} Litres")
            print(f" • Cost: £{cost_data.get('total_fuel_cost', 0):.2f}")

        safety = rec.get("safety_analysis", {})
        print(f" • Safety Score: {safety.get('safety_score', 'N/A')}/100")
        print(f" • Risk Level: {safety.get('risk_level', 'Unknown')}")

        print(f"\nDecision Rationale: {result.get('selection_criteria')}")

        # Show stops (especially for EV)
        # stops_data = rec.get("stops", {})

    else:
        print("Planning Failed")
        print(result)


def main():
    """Entry point for CLI demo"""
    try:
        asyncio.run(run_demo_scenario())
    except KeyboardInterrupt:
        print("\nDemo interrupted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
