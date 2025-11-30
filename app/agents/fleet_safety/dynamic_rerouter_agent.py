"""
Dynamic Rerouting Agent - Continuous monitoring and adaptive rerouting
"""

import json
from datetime import datetime
from typing import Any

from google.adk.agents import LlmAgent


class DynamicRerouterAgent(LlmAgent):
    """
    Monitors active trips and triggers rerouting when conditions change.

    Agent that:
    - Monitors traffic conditions
    - Detects significant delays or incidents
    - Calculates reroute benefit
    - Executes rerouting with driver notification
    - Maintains reroute history

    Triggers:
    - Traffic incident (accident, construction)
    - Weather deterioration
    - Significant delay (>30 min vs planned)
    - Road closure
    - Emergency situations
    - EV Range Critical (simulated)
    """

    mcp_client: Any = None
    active_trips: dict = {}
    reroute_history: list = []

    # Thresholds
    min_time_savings_minutes: int = 10
    min_safety_improvement: int = 15
    max_additional_distance_pct: float = 0.10  # 10%

    def __init__(self, mcp_client):
        super().__init__(
            model="gemini-2.5-flash",
            name="dynamic_rerouter",
            description="Real-time route monitoring and adaptive rerouting",
            instruction="""You are a dynamic rerouting specialist for active trips.

            YOUR WORKFLOW:

            1. Get all active trips from system state
            2. For each active trip:
               a. Get current vehicle location
               b. Check traffic conditions on remaining route
               c. Detect any incidents or delays
               d. Check vehicle range status (simulated)
            3. If issues detected:
               a. Calculate reroute benefit
               b. If benefit > threshold, generate alternative route
               c. Notify driver with clear instructions
               d. Log reroute decision
            4. Update trip status

            REROUTE TRIGGERS:
            - Traffic delay > 30 minutes vs planned
            - Traffic incident with severity >= "major"
            - Road closure on planned route
            - Weather deterioration (rain → heavy rain)
            - Safety score drops below 60
            - Emergency directive from command center
            - EV Battery < 10% (force route to charger)

            REROUTE DECISION CRITERIA:
            Only reroute if alternative provides:
            - Time savings ≥ 10 minutes, OR
            - Safety score improvement ≥ 15 points, OR
            - Avoids critical incident (accident, closure)

            Consider:
            - Driver familiarity with new route
            - Additional distance (<10% more acceptable)
            - Delivery window impact
            - Fuel cost difference

            NOTIFICATION FORMAT:
            - Clear: "REROUTE RECOMMENDED"
            - Reason: "Major accident ahead causing 45-min delay"
            - Benefit: "New route saves 35 minutes"
            - Instructions: "Take next exit (#247) and follow new directions"

            Always log your decisions with reasoning.
            """,
            tools=[
                self.monitor_active_trips,
                self.check_route_conditions,
                self.calculate_reroute_benefit,
                self.generate_alternative_route,
                self.notify_driver_reroute,
                self.emergency_reroute,
            ],
        )
        self.mcp_client = mcp_client
        self.active_trips = {}
        self.reroute_history = []

    async def monitor_active_trips(self) -> dict:
        """
        Main function: Check all active trips for rerouting needs.
        Called periodically by orchestrator or runner.
        """
        monitored_trips = []
        reroutes_triggered = 0

        for trip_id, trip in self.active_trips.items():
            try:
                # Check conditions for this trip
                conditions = await self.check_route_conditions(trip)

                monitored_trips.append(
                    {
                        "trip_id": trip_id,
                        "vehicle_id": trip["vehicle_id"],
                        "conditions": conditions,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                # Determine if reroute needed
                if conditions.get("reroute_recommended", False):
                    # Calculate benefit
                    benefit = await self.calculate_reroute_benefit(trip, conditions)

                    if benefit.get("should_reroute", False):
                        # Execute reroute
                        reroute_result = await self.generate_alternative_route(
                            trip, conditions, benefit
                        )

                        if reroute_result.get("success"):
                            reroutes_triggered += 1

            except Exception as e:
                # Log error but continue monitoring other trips
                monitored_trips.append(
                    {
                        "trip_id": trip_id,
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

        return {
            "monitoring_cycle": len(self.reroute_history) + 1,
            "active_trips_count": len(self.active_trips),
            "trips_monitored": len(monitored_trips),
            "reroutes_triggered": reroutes_triggered,
            "timestamp": datetime.now().isoformat(),
            "trip_details": monitored_trips,
        }

    async def check_route_conditions(self, trip: dict) -> dict:
        """
        Check current conditions on remaining route.
        """
        vehicle_location = trip.get("current_location", trip["origin"])
        destination = trip["destination"]
        # Ensure location is formatted correctly for API
        if isinstance(vehicle_location, dict) and "lat" in vehicle_location:
            origin_str = f"{vehicle_location['lat']},{vehicle_location['lng']}"
        else:
            origin_str = str(vehicle_location)

        remaining_route = trip.get(
            "remaining_route_polyline", trip.get("planned_route_polyline", "")
        )

        # Get current traffic conditions
        try:
            # Try with origin/destination as per 0.2.0 update ("delay estimates between locations")
            traffic_result = await self.mcp_client.call_tool(
                "google_maps",
                "get_traffic_conditions",
                {"origin": origin_str, "destination": destination, "mode": "driving"},
            )

            # Parse result
            if isinstance(traffic_result, str):
                traffic_data = json.loads(traffic_result)
            elif hasattr(traffic_result, "content"):
                traffic_data = json.loads(traffic_result.content[0].text)
            else:
                traffic_data = traffic_result  # Assume dict

        except Exception:
            # Fallback: try with path if tool supports it (older version?)
            try:
                traffic_result = await self.mcp_client.call_tool(
                    "google_maps", "get_traffic_conditions", {"path": remaining_route}
                )
                if isinstance(traffic_result, str):
                    traffic_data = json.loads(traffic_result)
                else:
                    traffic_data = traffic_result
            except Exception:
                # Fallback: assume basic traffic check
                traffic_data = {"traffic_level": "unknown"}

        # Get fresh route to compare timing
        current_route = await self.mcp_client.call_tool(
            "google_maps",
            "get_directions",
            {
                "origin": origin_str,
                "destination": destination,
                "departure_time": datetime.now().isoformat(),
            },
        )

        try:
            current_route_data = json.loads(current_route)
            if isinstance(current_route_data, str):
                # Handle potential double-encoding
                current_route_data = json.loads(current_route_data)
        except Exception:
            return {"error": "Failed to parse route data", "reroute_recommended": False}

        if not isinstance(current_route_data, dict):
            return {"error": "Invalid route data format (not a dict)", "reroute_recommended": False}

        # Handle structure variation (data.routes vs routes)
        routes_list = []
        data_field = current_route_data.get("data")
        if isinstance(data_field, dict) and data_field.get("routes"):
            routes_list = data_field["routes"]
        elif isinstance(current_route_data.get("routes"), list):
            routes_list = current_route_data["routes"]

        if not routes_list:
            return {"error": "Could not get current route", "reroute_recommended": False}

        current_eta_minutes = 0
        if routes_list:
            route = routes_list[0]
            if not isinstance(route, dict):
                return {"error": "Invalid route format (not a dict)", "reroute_recommended": False}

            # Extract duration
            dur = route.get("duration_in_traffic_minutes")
            if not dur:
                # Try to parse/convert
                dur_obj = route.get("duration_in_traffic")
                dur_seconds = None
                if isinstance(dur_obj, dict):
                    dur_seconds = dur_obj.get("value")

                if not dur_seconds and route.get("legs"):
                    leg = route["legs"][0]
                    if isinstance(leg, dict):
                        leg_dur = leg.get("duration_in_traffic")
                        if isinstance(leg_dur, dict):
                            dur_seconds = leg_dur.get("value")

                dur = (dur_seconds / 60) if dur_seconds else route.get("duration_minutes", 0)

            current_eta_minutes = dur

        planned_eta_minutes = trip.get("planned_remaining_duration_minutes", current_eta_minutes)

        delay_minutes = current_eta_minutes - planned_eta_minutes

        # Check for incidents
        incidents = []
        if traffic_data.get("traffic_level") == "heavy":
            incidents.append(
                {
                    "type": "traffic_congestion",
                    "severity": "major",
                    "delay_minutes": delay_minutes,
                }
            )

        # Determine if reroute recommended
        reroute_recommended = False
        reasons = []

        if delay_minutes > 30:
            reroute_recommended = True
            reasons.append(f"Significant delay detected: {delay_minutes:.0f} minutes vs planned")

        if traffic_data.get("traffic_level") == "heavy" and delay_minutes > 15:
            reroute_recommended = True
            reasons.append("Heavy traffic causing major delays")

        # Simulated EV Range Check
        # In a real system, we'd check telemetry for battery_level
        if trip.get("vehicle_type", "diesel") == "electric":
            # Mock: 5% chance of low battery warning for demo purposes
            import random

            if random.random() < 0.05:
                reroute_recommended = True
                reasons.append("CRITICAL: Battery level low, reroute to nearest charger required")
                incidents.append({"type": "low_battery", "severity": "critical"})

        return {
            "current_location": vehicle_location,
            "current_eta_minutes": current_eta_minutes,
            "planned_eta_minutes": planned_eta_minutes,
            "delay_minutes": delay_minutes,
            "traffic_level": traffic_data.get("traffic_level", "unknown"),
            "incidents": incidents,
            "reroute_recommended": reroute_recommended,
            "reasons": reasons,
            "timestamp": datetime.now().isoformat(),
        }

    async def calculate_reroute_benefit(self, trip: dict, conditions: dict) -> dict:
        """
        Calculate if rerouting provides sufficient benefit.
        """
        vehicle_location = trip["current_location"]
        destination = trip["destination"]

        if isinstance(vehicle_location, dict) and "lat" in vehicle_location:
            origin_str = f"{vehicle_location['lat']},{vehicle_location['lng']}"
        else:
            origin_str = str(vehicle_location)

        # Get alternative routes
        alt_routes = await self.mcp_client.call_tool(
            "google_maps",
            "get_directions",
            {
                "origin": origin_str,
                "destination": destination,
                "alternatives": True,
                "departure_time": datetime.now().isoformat(),
            },
        )

        alt_routes_data = json.loads(alt_routes)
        if isinstance(alt_routes_data, str):
            try:
                alt_routes_data = json.loads(alt_routes_data)
            except Exception:
                pass

        # Normalize routes list
        routes_list = []
        if isinstance(alt_routes_data, dict):
            data_field = alt_routes_data.get("data")
            if isinstance(data_field, dict) and data_field.get("routes"):
                routes_list = data_field["routes"]
            elif isinstance(alt_routes_data.get("routes"), list):
                routes_list = alt_routes_data["routes"]

        if not routes_list or len(routes_list) < 2:
            return {"should_reroute": False, "reason": "No alternative routes available"}

        # Current route (first result)
        current = routes_list[0]

        # Extract numerical values helper
        def get_minutes(r):
            if not isinstance(r, dict):
                return 0
            m = r.get("duration_in_traffic_minutes")
            if m is not None:
                return m
            # fallback
            dur_obj = r.get("duration_in_traffic")
            s = None
            if isinstance(dur_obj, dict):
                s = dur_obj.get("value")

            if s is None and r.get("legs"):
                leg = r["legs"][0]
                if isinstance(leg, dict):
                    leg_dur = leg.get("duration_in_traffic")
                    if isinstance(leg_dur, dict):
                        s = leg_dur.get("value")
            return (s / 60) if s else r.get("duration_minutes", 0)

        def get_miles(r):
            if not isinstance(r, dict):
                return 0
            m = r.get("distance_miles")
            if m is not None:
                return m
            meters = r.get("distance_meters")
            if meters is None and r.get("legs"):
                leg = r["legs"][0]
                if isinstance(leg, dict):
                    leg_dist = leg.get("distance")
                    if isinstance(leg_dist, dict):
                        meters = leg_dist.get("value")
            return (meters * 0.000621371) if meters else 0

        current_time = get_minutes(current)
        current_distance = get_miles(current)

        # Find best alternative
        alternatives = routes_list[1:]
        best_alt = None
        best_benefit = 0

        for alt in alternatives:
            alt_time = get_minutes(alt)
            alt_distance = get_miles(alt)

            # Time savings
            time_savings = current_time - alt_time

            # Distance penalty (if significantly longer)
            if current_distance > 0:
                distance_increase_pct = (alt_distance - current_distance) / current_distance
            else:
                distance_increase_pct = 0

            if distance_increase_pct > self.max_additional_distance_pct:
                continue  # Too much extra distance

            # Calculate benefit score
            benefit_score = time_savings - (distance_increase_pct * 30)  # Penalize extra distance

            if benefit_score > best_benefit:
                best_benefit = benefit_score
                best_alt = alt
                best_alt["time_savings"] = time_savings
                best_alt["distance_increase_pct"] = distance_increase_pct

        # Decision
        should_reroute = False
        decision_reason = ""

        if best_alt and best_alt["time_savings"] >= self.min_time_savings_minutes:
            should_reroute = True
            decision_reason = f"Alternative route saves {best_alt['time_savings']:.0f} minutes"
        elif conditions.get("incidents"):
            # Critical incidents override time threshold
            critical_incidents = [
                i for i in conditions["incidents"] if i.get("severity") in ["critical", "major"]
            ]
            if critical_incidents and best_alt:
                should_reroute = True
                decision_reason = f"Avoiding {len(critical_incidents)} critical incidents"

        if not should_reroute:
            decision_reason = "Alternative routes do not provide sufficient benefit"

        return {
            "should_reroute": should_reroute,
            "reason": decision_reason,
            "best_alternative": best_alt,
            "time_savings_minutes": best_alt["time_savings"] if best_alt else 0,
            "benefit_score": best_benefit,
            "current_route_time": current_time,
            "alternative_route_time": get_minutes(best_alt) if best_alt else None,
        }

    async def generate_alternative_route(self, trip: dict, conditions: dict, benefit: dict) -> dict:
        """
        Generate and apply new route.
        """
        if not benefit.get("best_alternative"):
            return {"success": False, "reason": "No suitable alternative available"}

        new_route = benefit["best_alternative"]

        # Update trip with new route
        old_route = trip.get("current_route")
        trip["current_route"] = new_route
        trip["remaining_route_polyline"] = new_route.get("polyline") or new_route.get(
            "overview_polyline", {}
        ).get("points", "")

        # Use helper to get duration
        def get_minutes(r):
            if not isinstance(r, dict):
                return 0
            m = r.get("duration_in_traffic_minutes")
            if m is not None:
                return m

            dur_obj = r.get("duration_in_traffic")
            s = None
            if isinstance(dur_obj, dict):
                s = dur_obj.get("value")

            if s is None and r.get("legs"):
                leg = r["legs"][0]
                if isinstance(leg, dict):
                    leg_dur = leg.get("duration_in_traffic")
                    if isinstance(leg_dur, dict):
                        s = leg_dur.get("value")
            return (s / 60) if s else r.get("duration_minutes", 0)

        trip["planned_remaining_duration_minutes"] = get_minutes(new_route)

        # Notify driver
        notification = await self.notify_driver_reroute(trip, conditions, benefit)

        # Log reroute
        reroute_record = {
            "trip_id": trip["trip_id"],
            "vehicle_id": trip["vehicle_id"],
            "timestamp": datetime.now().isoformat(),
            "reason": benefit["reason"],
            "conditions": conditions,
            "old_route": old_route,
            "new_route": new_route,
            "time_savings_minutes": benefit["time_savings_minutes"],
            "notification": notification,
        }

        self.reroute_history.append(reroute_record)

        return {
            "success": True,
            "new_route": new_route,
            "notification_sent": notification.get("sent", False),
            "reroute_record": reroute_record,
        }

    async def notify_driver_reroute(self, trip: dict, conditions: dict, benefit: dict) -> dict:
        """
        Send reroute notification to driver.
        """
        alt_time = benefit.get("alternative_route_time", 0) or 0

        message = f"""
REROUTE RECOMMENDED
Reason: {benefit["reason"]}
Time Savings: {benefit["time_savings_minutes"]:.0f} minutes
Current Delay: {conditions["delay_minutes"]:.0f} minutes
New ETA: {alt_time:.0f} minutes
Instructions: Follow updated navigation on your device.
[ACCEPT REROUTE] [KEEP CURRENT ROUTE]
        """.strip()

        # TODO: Integrate with actual notification system
        notification = {
            "trip_id": trip["trip_id"],
            "vehicle_id": trip["vehicle_id"],
            "driver_id": trip["driver_id"],
            "type": "reroute_recommendation",
            "priority": "high",
            "message": message,
            "sent": True,
            "timestamp": datetime.now().isoformat(),
        }

        return notification

    async def emergency_reroute(self, vehicle_id: str, reason: str) -> dict:
        """
        Execute emergency reroute (bypasses normal decision logic).
        Used for critical situations like road closures, accidents ahead, etc.
        """
        # Find active trip for this vehicle
        trip = next(
            (t for t in self.active_trips.values() if t["vehicle_id"] == vehicle_id),
            None,
        )

        if not trip:
            return {"success": False, "error": "No active trip found for vehicle"}

        # Force reroute with highest priority
        # conditions = {
        #     "emergency": True,
        #     "reason": reason,
        #     "timestamp": datetime.now().isoformat(),
        # }

        # Get alternative route
        vehicle_location = trip["current_location"]
        if isinstance(vehicle_location, dict) and "lat" in vehicle_location:
            origin_str = f"{vehicle_location['lat']},{vehicle_location['lng']}"
        else:
            origin_str = str(vehicle_location)

        alt_routes = await self.mcp_client.call_tool(
            "google_maps",
            "get_directions",
            {
                "origin": origin_str,
                "destination": trip["destination"],
                "alternatives": True,
                "departure_time": datetime.now().isoformat(),
            },
        )

        alt_routes_data = json.loads(alt_routes)

        routes_list = []
        if alt_routes_data.get("data", {}).get("routes"):
            routes_list = alt_routes_data["data"]["routes"]
        elif alt_routes_data.get("routes"):
            routes_list = alt_routes_data["routes"]

        if not routes_list or len(routes_list) < 2:
            # Even in emergency, if no alternative exists, inform command center
            return {
                "success": False,
                "error": "No alternative routes available",
                "recommendation": "Vehicle should stop and await instructions",
            }

        # Take first alternative
        new_route = routes_list[1]

        # Apply immediately
        trip["current_route"] = new_route
        trip["remaining_route_polyline"] = new_route.get("polyline") or new_route.get(
            "overview_polyline", {}
        ).get("points", "")

        # Emergency notification
        emergency_notification = {
            "trip_id": trip["trip_id"],
            "vehicle_id": vehicle_id,
            "type": "emergency_reroute",
            "priority": "critical",
            "message": f"""
EMERGENCY REROUTE REQUIRED
Reason: {reason}
FOLLOW NEW ROUTE IMMEDIATELY
This is a safety-critical directive.
Contact dispatch if unable to comply.
            """.strip(),
            "sent": True,
            "timestamp": datetime.now().isoformat(),
        }

        # Log emergency reroute
        self.reroute_history.append(
            {
                "trip_id": trip["trip_id"],
                "vehicle_id": vehicle_id,
                "type": "emergency",
                "reason": reason,
                "timestamp": datetime.now().isoformat(),
                "new_route": new_route,
                "notification": emergency_notification,
            }
        )

        return {
            "success": True,
            "type": "emergency",
            "new_route": new_route,
            "notification": emergency_notification,
        }

    def add_active_trip(self, trip: dict):
        """Add trip to monitoring"""
        self.active_trips[trip["trip_id"]] = trip

    def remove_active_trip(self, trip_id: str):
        """Remove completed trip from monitoring"""
        if trip_id in self.active_trips:
            del self.active_trips[trip_id]
