"""
Route Planning Agent - Sequential workflow for route generation
"""

import json
from datetime import datetime
from typing import Any

from google.adk.agents import LlmAgent


class RoutePlannerAgent(LlmAgent):
    """
    Generates optimised route options using Google Maps APIs.

    Sequential agent that:
    1. Validates input (addresses, constraints)
    2. Generates multiple route alternatives
    3. Calculates fuel/energy costs (supporting EVs)
    4. Checks delivery windows
    5. Returns ranked options
    """

    mcp_client: Any = None

    def __init__(self, mcp_client):
        super().__init__(
            model="gemini-2.5-flash",
            name="route_planner_agent",
            description="Route planning specialist that generates multiple route options with fuel costs, distance, and duration for fleet vehicles. Call with origin, destination, and vehicle_type.",
            instruction="""You are a route planning specialist for commercial fleets.

            When you receive a route planning request, you MUST:
            1. Use the generate_route_options tool to get route alternatives from Google Maps
            2. For each route returned, use calculate_fuel_cost to estimate costs
            3. Return ALL routes with their details in a structured format

            IMPORTANT: Always call generate_route_options first with the origin and destination.
            Then process the results to provide useful route information.

            Vehicle Types & Fuel Efficiency:
            - light_truck: 4.0 miles/litre diesel, 300-mile range
            - heavy_truck: 2.0 miles/litre diesel, 500-mile range
            - van: 5.5 miles/litre diesel, 400-mile range
            - electric_truck: 1.5 miles/kWh, 250-mile range
            - electric_van: 2.5 miles/kWh, 180-mile range

            Format your response as structured data including:
            - Route summary/name
            - Distance (miles)
            - Duration (minutes)
            - Duration in traffic (minutes)
            - Fuel/energy cost estimate
            - Route polyline (for safety scoring)

            Always explain which routes you found and their key differences.
            """,
            tools=[
                self.generate_route_options,
                self.calculate_fuel_cost,
                self.validate_route_request,
                self.check_delivery_windows,
                self.find_required_stops,
                self.rank_routes,
            ],
        )
        self.mcp_client = mcp_client

    async def validate_route_request(
        self, origin: str, destination: str, vehicle_type: str, departure_time: str
    ) -> dict:
        """
        Validate route request and normalise addresses.
        """
        # Geocode origin to validate
        origin_result = await self.mcp_client.call_tool(
            "google_maps", "geocode_address", {"address": origin}
        )

        origin_data = json.loads(origin_result)
        if origin_data.get("error"):
            return {"valid": False, "error": f"Invalid origin address: {origin}", "field": "origin"}

        # Geocode destination
        dest_result = await self.mcp_client.call_tool(
            "google_maps", "geocode_address", {"address": destination}
        )

        dest_data = json.loads(dest_result)
        if dest_data.get("error"):
            return {
                "valid": False,
                "error": f"Invalid destination address: {destination}",
                "field": "destination",
            }

        # Validate vehicle type
        valid_types = ["light_truck", "heavy_truck", "van", "electric_truck", "electric_van"]
        if vehicle_type not in valid_types:
            return {
                "valid": False,
                "error": f"Invalid vehicle type. Must be one of: {valid_types}",
                "field": "vehicle_type",
            }

        return {
            "valid": True,
            "normalized_origin": origin_data["data"]["formatted_address"],
            "origin_location": origin_data["data"]["location"],
            "normalized_destination": dest_data["data"]["formatted_address"],
            "destination_location": dest_data["data"]["location"],
            "vehicle_type": vehicle_type,
        }

    async def generate_route_options(self, request: dict) -> dict:
        """
        Generate multiple route alternatives using Google Maps.
        """
        origin = request["origin"]
        destination = request["destination"]
        departure_time = request.get("departure_time", datetime.now().isoformat())

        # Get routes from Google Maps MCP server
        routes_result = await self.mcp_client.call_tool(
            "google_maps",
            "get_directions",
            {
                "origin": origin,
                "destination": destination,
                "departure_time": departure_time,
                "alternatives": True,
                "mode": "driving",
            },
        )

        routes_data = json.loads(routes_result)

        if routes_data.get("error") or not routes_data.get("data", {}).get("routes"):
            return {"error": "No routes found", "routes": []}

        # Also get routes avoiding highways (for comparison)
        highway_free_result = await self.mcp_client.call_tool(
            "google_maps",
            "get_directions",
            {
                "origin": origin,
                "destination": destination,
                "departure_time": departure_time,
                "alternatives": False,
                "avoid": ["highways"],
            },
        )

        highway_free_data = json.loads(highway_free_result)
        if highway_free_data.get("data", {}).get("routes"):
            # Add highway-free route if significantly different
            main_route = routes_data["data"]["routes"][0]
            hf_route = highway_free_data["data"]["routes"][0]

            # Calculate distance in miles from meters
            main_dist = main_route.get("distance_meters", 0) * 0.000621371
            hf_dist = hf_route.get("distance_meters", 0) * 0.000621371

            if abs(hf_dist - main_dist) > 10:
                hf_route["route_type"] = "highway_free"
                routes_data["data"]["routes"].append(hf_route)

        # Normalise route data (ensure duration and distance are available)
        for route in routes_data["data"]["routes"]:
            # Duration
            if "estimated_duration_minutes" not in route:
                dur = route.get("duration_in_traffic_minutes")
                if not dur:
                    # Extract from legs if needed or duration object
                    dur_obj = route.get("duration_in_traffic")
                    dur_sec = None
                    if isinstance(dur_obj, dict):
                        dur_sec = dur_obj.get("value")

                    if not dur_sec and route.get("legs"):
                        # Legs might be a list of dicts
                        legs = route["legs"]
                        if legs and isinstance(legs[0], dict):
                            leg_dur = legs[0].get("duration_in_traffic")
                            if isinstance(leg_dur, dict):
                                dur_sec = leg_dur.get("value")

                    if not dur_sec:
                        # Fallback to standard duration
                        dur_obj = route.get("duration")
                        if isinstance(dur_obj, dict):
                            dur_sec = dur_obj.get("value")

                        if not dur_sec and route.get("legs"):
                            legs = route["legs"]
                            if legs and isinstance(legs[0], dict):
                                leg_dur = legs[0].get("duration")
                                if isinstance(leg_dur, dict):
                                    dur_sec = leg_dur.get("value")

                    dur = (dur_sec / 60) if dur_sec else 0
                route["estimated_duration_minutes"] = dur

            # Distance
            if "distance_miles" not in route:
                dist_miles = route.get("distance_miles")
                if not dist_miles:
                    dist_meters = route.get("distance_meters")
                    if not dist_meters and route.get("legs"):
                        legs = route["legs"]
                        if legs and isinstance(legs[0], dict):
                            leg_dist = legs[0].get("distance")
                            if isinstance(leg_dist, dict):
                                dist_meters = leg_dist.get("value")
                    dist_miles = (dist_meters * 0.000621371) if dist_meters else 0
                route["distance_miles"] = dist_miles

        return {
            "route_count": len(routes_data["data"]["routes"]),
            "routes": routes_data["data"]["routes"],
        }

    async def calculate_fuel_cost(
        self, distance_miles: float, vehicle_type: str, route_polyline: str = None
    ) -> dict:
        """
        Calculate fuel or energy cost for route.
        Supports standard and electric vehicles.
        For EVs, accounts for elevation gain which increases battery drain.
        """
        # Ensure distance_miles is a float (handle if it's passed as None or missing)
        distance_miles = float(distance_miles) if distance_miles else 0.0

        is_electric = "electric" in vehicle_type

        if is_electric:
            # Electric Vehicle Logic
            # Efficiency in Miles per kWh
            efficiency_map = {"electric_truck": 1.5, "electric_van": 2.5}

            # Charging cost (£/kWh) - using average public fast charging rate
            energy_price = 0.45

            efficiency = efficiency_map.get(vehicle_type, 2.0)

            # kWh needed for distance
            units_needed = distance_miles / efficiency

            # Elevation adjustment for EVs (if polyline provided)
            elevation_penalty_kwh = 0.0
            if route_polyline:
                try:
                    elevation_result = await self.mcp_client.call_tool(
                        "google_maps",
                        "get_route_elevation_gain",
                        {"polyline": route_polyline},
                    )
                    elevation_data = json.loads(elevation_result)
                    # Handle different response structures
                    if isinstance(elevation_data, dict):
                        elevation_gain_meters = elevation_data.get("total_gain", 0)
                    elif isinstance(elevation_data, str):
                        elevation_data = json.loads(elevation_data)
                        elevation_gain_meters = elevation_data.get("total_gain", 0)
                    else:
                        elevation_gain_meters = 0

                    # Physics-based adjustment:
                    # Potential Energy = m * g * h
                    # Approx: 100m elevation gain ~ 1.5 kWh for a loaded truck
                    if elevation_gain_meters > 0:
                        elevation_penalty_kwh = (elevation_gain_meters / 100) * 1.5
                except (KeyError, AttributeError, RuntimeError, ValueError):
                    # Tool not found, connection error, or parsing error - gracefully degrade
                    # Logging would be ideal but keeping it silent for now to avoid noise
                    elevation_penalty_kwh = 0.0
                except Exception:
                    # Catch-all for any other unexpected errors
                    elevation_penalty_kwh = 0.0

            units_needed += elevation_penalty_kwh
            total_cost = units_needed * energy_price

            result = {
                "distance_miles": distance_miles,
                "vehicle_type": vehicle_type,
                "efficiency_miles_per_kwh": efficiency,
                "kwh_needed": round(units_needed, 2),
                "price_per_kwh": energy_price,
                "total_energy_cost": round(total_cost, 2),
                "cost_per_mile": round(total_cost / distance_miles, 2) if distance_miles > 0 else 0,
                "fuel_type": "electric",
            }

            if elevation_penalty_kwh > 0:
                result["elevation_adjustment_kwh"] = round(elevation_penalty_kwh, 2)
                result["base_kwh"] = round(units_needed - elevation_penalty_kwh, 2)

            return result
        else:
            # Standard Fuel Logic
            # Fuel efficiency by vehicle type (Miles Per Litre)
            mpl_map = {"light_truck": 4.0, "heavy_truck": 2.0, "van": 5.5}

            fuel_price = 1.45  # £/litre
            mpl = mpl_map.get(vehicle_type, 4.0)

            litres_needed = distance_miles / mpl
            total_cost = litres_needed * fuel_price

            return {
                "distance_miles": distance_miles,
                "vehicle_type": vehicle_type,
                "miles_per_litre": mpl,
                "litres_needed": round(litres_needed, 2),
                "fuel_price_per_litre": fuel_price,
                "total_fuel_cost": round(total_cost, 2),
                "cost_per_mile": round(total_cost / distance_miles, 2),
                "fuel_type": "diesel",
            }

    async def check_delivery_windows(
        self, estimated_arrival: str, delivery_windows: list[dict]
    ) -> dict:
        """
        Check if route meets delivery time requirements.
        """
        if not delivery_windows:
            return {"feasible": True, "reason": "No delivery windows specified"}

        from datetime import datetime

        arrival_time = datetime.fromisoformat(estimated_arrival.replace("Z", "+00:00"))

        for window in delivery_windows:
            window_start = datetime.fromisoformat(window["start"].replace("Z", "+00:00"))
            window_end = datetime.fromisoformat(window["end"].replace("Z", "+00:00"))

            if window_start <= arrival_time <= window_end:
                return {
                    "feasible": True,
                    "window": window,
                    "arrival_time": estimated_arrival,
                    "buffer_minutes": (window_end - arrival_time).total_seconds() / 60,
                }

        # No matching window
        earliest_window = min(delivery_windows, key=lambda w: w["start"])
        return {
            "feasible": False,
            "reason": "Arrival time outside all delivery windows",
            "arrival_time": estimated_arrival,
            "earliest_window_start": earliest_window["start"],
        }

    async def find_required_stops(
        self, route_polyline: str, distance_miles: float, duration_hours: float, vehicle_type: str
    ) -> dict:
        """
        Identify required stops (fuel, charging, rest breaks).
        """
        stops = []
        is_electric = "electric" in vehicle_type

        # Range Logic
        if is_electric:
            range_map = {"electric_truck": 250, "electric_van": 180}
            refuel_type = "electric_vehicle_charging_station"
            refuel_keyword = "EV charging"
            refuel_time_min = 45  # 45 mins for fast charge
        else:
            range_map = {"light_truck": 300, "heavy_truck": 500, "van": 400}
            refuel_type = "gas_station"
            refuel_keyword = "truck stop"
            refuel_time_min = 15

        vehicle_range = range_map.get(vehicle_type, 300)

        if distance_miles > vehicle_range * 0.8:  # Need energy if using >80% of range
            # Find station at midpoint
            from polyline import decode

            points = decode(route_polyline)
            midpoint_idx = len(points) // 2
            midpoint = f"{points[midpoint_idx][0]},{points[midpoint_idx][1]}"

            stations = await self.mcp_client.call_tool(
                "google_maps",
                "find_nearby_places",
                {
                    "location": midpoint,
                    "radius": 5000,  # 5km
                    "type": refuel_type,
                    "keyword": refuel_keyword,
                },
            )

            station_data = json.loads(stations)
            if station_data.get("places"):
                place = station_data["places"][0]
                # Use get_place_details to get more info
                try:
                    place_id = place.get("place_id")
                    if place_id:
                        details_result = await self.mcp_client.call_tool(
                            "google_maps", "get_place_details", {"place_id": place_id}
                        )
                        if isinstance(details_result, str):
                            details = json.loads(details_result)
                        elif hasattr(details_result, "content"):
                            details = json.loads(details_result.content[0].text)
                        else:
                            details = details_result

                        if details and not details.get("error"):
                            place["details"] = details
                except Exception:
                    pass

                stops.append(
                    {
                        "type": "charging" if is_electric else "fuel",
                        "reason": f"Energy required (route: {distance_miles:.0f} mi, range: {vehicle_range} mi)",
                        "location": place,
                        "estimated_duration_minutes": refuel_time_min,
                    }
                )

        # Rest breaks (required every 4-5 hours or 8 hours for HOS)
        # If charging stop is long enough (e.g. 45 min), it counts as rest break
        has_long_stop = any(s.get("estimated_duration_minutes", 0) >= 30 for s in stops)

        if duration_hours > 4 and not has_long_stop:
            stops.append(
                {
                    "type": "rest_break",
                    "reason": "Driver rest break required",
                    "recommended_duration_minutes": 30,
                    "hos_requirement": duration_hours > 8,
                }
            )

        return {
            "stops_required": len(stops),
            "stops": stops,
            "total_stop_time_minutes": sum(s.get("estimated_duration_minutes", 30) for s in stops),
        }

    async def rank_routes(self, routes: list[dict]) -> dict:
        """
        Rank routes by different criteria.
        """
        if not routes:
            return {"error": "No routes to rank"}

        # Helper to safely get total cost regardless of fuel type
        def get_cost(r):
            cost_data = r.get("fuel_cost", {})
            return cost_data.get("total_fuel_cost") or cost_data.get("total_energy_cost", 999)

        rankings = {
            "fastest": min(routes, key=lambda r: r.get("estimated_duration_minutes", 999)),
            "shortest": min(routes, key=lambda r: r.get("distance_miles", 999)),
            "cheapest": min(routes, key=get_cost),
            "balanced": None,
        }

        # Calculate balanced score (weighted combination)
        for route in routes:
            time_score = route.get("estimated_duration_minutes", 0) / 60  # hours
            distance_score = route.get("distance_miles", 0) / 100  # normalise
            cost_score = get_cost(route) / 100  # normalise

            # Weighted score (40% time, 30% distance, 30% cost)
            route["balanced_score"] = (
                (time_score * 0.4) + (distance_score * 0.3) + (cost_score * 0.3)
            )

        rankings["balanced"] = min(routes, key=lambda r: r.get("balanced_score", 999))

        return {
            "rankings": rankings,
            "recommendation": rankings["balanced"],
            "recommendation_reason": "Best overall balance of time, distance, and cost",
        }
