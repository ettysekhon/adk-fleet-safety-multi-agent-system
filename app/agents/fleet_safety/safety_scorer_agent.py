"""
Safety Scoring Agent - Parallel evaluation of multiple routes
"""

import asyncio
from datetime import datetime
from typing import Any

from google.adk.agents import LlmAgent


class SafetyScorerAgent(LlmAgent):
    """
    Evaluates route safety using historical data and real-time conditions.

    Parallel agent that scores multiple routes simultaneously:
    - Historical accident data
    - Road characteristics (speed limits, road types)
    - Environmental factors (weather, time of day)
    - Driver-specific adjustments
    - Traffic conditions
    - Vehicle-specific risks (e.g. EV range in cold weather)

    Returns comprehensive safety analysis with 0-100 score.
    """

    mcp_client: Any = None
    accident_database: dict = {}

    def __init__(self, mcp_client):
        super().__init__(
            model="gemini-2.5-flash",
            name="safety_scorer",
            description="Parallel route safety evaluation specialist",
            instruction="""You are a safety analysis expert for fleet operations.

            Your mission: Evaluate routes for safety risks and assign scores (0-100).

            PARALLEL PROCESSING:
            You can evaluate multiple routes simultaneously. Each route evaluation is independent.

            Evaluation Factors:

            1. Road Characteristics (40 points max)
               - Speed limits: High speed = higher risk
                 * 70+ mph: -15 points
                 * 55-69 mph: -5 points
                 * <55 mph: 0 points
               - Road types:
                 * Interstate/highway: +10 (safer, divided)
                 * Arterial roads: 0 (moderate)
                 * Local/urban: -5 (more intersections)
                 * Rural two-lane: -10 (passing, head-on risk)
               - Complexity:
                 * Simple (few turns): +10
                 * Moderate: 0
                 * Complex (many turns/intersections): -10

            2. Historical Safety (30 points max)
               - Accident frequency in corridor
                 * 0-5 incidents/year: +30
                 * 6-10 incidents/year: +15
                 * 11-20 incidents/year: 0
                 * 21+ incidents/year: -20
               - Incident severity score

            3. Environmental Conditions (20 points max)
               - Time of day:
                 * Daylight (8am-6pm): +10
                 * Dusk/Dawn (6-8am, 6-8pm): -5
                 * Night (8pm-6am): -15
               - Weather:
                 * Clear: +10
                 * Rain: -10
                 * Heavy rain/fog: -20
                 * Snow/ice: -30
               - Traffic:
                 * Light: +10
                 * Moderate: 0
                 * Heavy: -10

            4. Driver Fit & Vehicle (10 points max)
               - Experience level:
                 * Expert (5+ years): +10
                 * Experienced (2-5 years): +5
                 * New (<2 years): -5
               - Route familiarity:
                 * Driven 10+ times: +5
                 * Driven 1-10 times: +2
                 * Never driven: -3
               - Safety record:
                 * Excellent (<0.5 incidents/100k mi): +5
                 * Good (0.5-1.0): 0
                 * Poor (>1.0): -10
               - Vehicle Factors:
                 * EV in extreme cold: -5 (battery drain risk)

            SCORING OUTPUT:
            - Overall score: 0-100
            - Risk level: LOW (80-100), MEDIUM (60-79), HIGH (40-59), CRITICAL (<40)
            - Top 3 risk factors with impacts
            - Recommendations for risk mitigation

            Always explain your scoring methodology.
            """,
            tools=[
                self.score_route,
                self.analyze_road_characteristics,
                self.get_historical_safety_data,
                self.evaluate_environmental_conditions,
                self.adjust_for_driver_profile,
                self.generate_risk_mitigation_plan,
            ],
        )
        self.mcp_client = mcp_client

        # TODO: Use a real database in production (rather than simulated data)
        self.accident_database = self._initialise_accident_data()

    def _initialise_accident_data(self) -> dict:
        """
        Initialise simulated historical accident data.
        """
        return {
            "high_risk_corridors": [
                {
                    "name": "M25 London Orbital",
                    "annual_incidents": 45,
                    "severity_score": 7.2,
                    "primary_causes": ["congestion", "weather", "lane_changes"],
                },
                {
                    "name": "M6 Midlands",
                    "annual_incidents": 67,
                    "severity_score": 6.8,
                    "primary_causes": ["congestion", "aggressive_driving"],
                },
                {
                    "name": "A9 Scotland",
                    "annual_incidents": 34,
                    "severity_score": 8.1,
                    "primary_causes": ["curves", "weather", "tourist_traffic"],
                },
            ],
            "time_of_day_multipliers": {
                "night": 2.3,  # 2.3x higher incident rate at night
                "dusk_dawn": 1.6,
                "day": 1.0,
            },
            "weather_multipliers": {
                "clear": 1.0,
                "rain": 2.1,
                "heavy_rain": 3.4,
                "snow": 4.2,
                "ice": 5.8,
            },
        }

    async def score_route(
        self,
        route: dict,
        driver_profile: dict,
        current_conditions: dict,
        vehicle_config: dict = None,
    ) -> dict:
        """
        Main entry point: Comprehensive route safety scoring.

        This orchestrates parallel evaluation of all safety factors.
        """
        # Start all evaluations in parallel
        tasks = [
            self.analyze_road_characteristics(route),
            self.get_historical_safety_data(route),
            self.evaluate_environmental_conditions(route, current_conditions, vehicle_config),
            self.adjust_for_driver_profile(route, driver_profile),
        ]

        # Execute in parallel
        results = await asyncio.gather(*tasks)

        road_analysis = results[0]
        historical_analysis = results[1]
        environmental_analysis = results[2]
        driver_adjustment = results[3]

        # Calculate overall score
        base_score = 100

        # Apply road characteristics impact
        base_score += road_analysis["score_impact"]

        # Apply historical safety impact
        base_score += historical_analysis["score_impact"]

        # Apply environmental conditions impact
        base_score += environmental_analysis["score_impact"]

        # Apply driver-specific adjustment
        base_score += driver_adjustment["score_impact"]

        # Ensure score is between 0-100
        final_score = max(0, min(100, base_score))

        # Determine risk level
        if final_score >= 80:
            risk_level = "LOW"
        elif final_score >= 60:
            risk_level = "MEDIUM"
        elif final_score >= 40:
            risk_level = "HIGH"
        else:
            risk_level = "CRITICAL"

        # Aggregate risk factors (top 3)
        all_risks = []
        all_risks.extend(road_analysis.get("risk_factors", []))
        all_risks.extend(historical_analysis.get("risk_factors", []))
        all_risks.extend(environmental_analysis.get("risk_factors", []))
        all_risks.extend(driver_adjustment.get("risk_factors", []))

        # Sort by impact and take top 3
        all_risks.sort(key=lambda x: abs(x.get("impact", 0)), reverse=True)
        top_risks = all_risks[:3]

        # Generate recommendations
        recommendations = await self.generate_risk_mitigation_plan(
            {"risk_level": risk_level, "top_risks": top_risks, "route": route}
        )

        return {
            "route_id": route.get("route_id", 0),
            "safety_score": round(final_score, 1),
            "risk_level": risk_level,
            "component_scores": {
                "road_characteristics": road_analysis,
                "historical_safety": historical_analysis,
                "environmental_conditions": environmental_analysis,
                "driver_fit": driver_adjustment,
            },
            "top_risk_factors": top_risks,
            "recommendations": recommendations,
            "evaluation_timestamp": datetime.now().isoformat(),
        }

    async def analyze_road_characteristics(self, route: dict) -> dict:
        """
        Analyse road characteristics using Google Maps APIs.
        Maximum impact: ±40 points
        """
        polyline = route.get("polyline", "")
        # Fallback if polyline is in 'overview_polyline.points' structure from Maps API
        if not polyline and isinstance(route.get("overview_polyline"), dict):
            polyline = route["overview_polyline"].get("points", "")

        if not polyline and not route.get("summary"):
            # Return early if no route data
            return {
                "score_impact": 0,
                "risk_factors": [],
                "error": "No route polyline or summary provided",
            }

        # Get road characteristics from Google Maps
        try:
            # Use the custom compound tool
            safety_factors_result = await self.mcp_client.call_tool(
                "google_maps",
                "calculate_route_safety_factors",
                {"route_polyline": polyline},
            )
            # Parse result
            import json

            if isinstance(safety_factors_result, str):
                safety_factors = json.loads(safety_factors_result)
            else:
                safety_factors = safety_factors_result

            if not isinstance(safety_factors, dict):
                try:
                    if hasattr(safety_factors, "content") and safety_factors.content:
                        safety_factors = json.loads(safety_factors.content[0].text)
                    else:
                        raise ValueError("Unexpected format")
                except Exception:
                    if isinstance(safety_factors, str):
                        safety_factors = json.loads(safety_factors)
                    else:
                        raise

            # Map tool output to agent format
            tool_score = safety_factors.get("safety_score", 50)
            score_impact = (tool_score - 50) * 0.8

            risk_factors = safety_factors.get("risk_factors", [])
            # Ensure risk factors have required fields
            for rf in risk_factors:
                if "impact" not in rf:
                    rf["impact"] = -5

            return {
                "score_impact": round(score_impact, 1),
                "risk_factors": risk_factors,
                "analysis_method": "mcp_compound_tool",
                "raw_tool_output": safety_factors,
            }

        except Exception:
            # Fallback analysis based on route summary and data
            summary = route.get("summary", "").lower()
            distance = route.get("distance_miles", 0)
            if distance == 0 and route.get("distance_meters"):
                distance = route["distance_meters"] * 0.000621371

            duration = route.get("duration_minutes", 0)
            if duration == 0 and route.get("duration_seconds"):
                duration = route["duration_seconds"] / 60

            score_impact = 0
            risk_factors = []

            # Analyse based on route characteristics
            if "highway" in summary or "interstate" in summary or "m" in summary or "i-" in summary:
                # Heuristic for highways (M1, I-95, etc)
                score_impact += 10
            elif "local" in summary or "city" in summary:
                score_impact -= 5

            # High average speed = higher risk
            avg_speed = (distance / (duration / 60)) if duration > 0 else 0
            if avg_speed > 65:
                score_impact -= 15
                risk_factors.append(
                    {
                        "factor": "high_speed_route",
                        "impact": -15,
                        "details": f"Average speed {avg_speed:.0f} mph",
                    }
                )

            # Complex routes (low speed despite distance) = more intersections
            if distance > 50 and avg_speed < 35:
                score_impact -= 10
                risk_factors.append(
                    {
                        "factor": "complex_urban_route",
                        "impact": -10,
                        "details": "Many intersections and stops",
                    }
                )

        return {
            "score_impact": round(score_impact, 1),
            "risk_factors": risk_factors,
            "analysis_method": "heuristic_fallback",
        }

    async def get_historical_safety_data(self, route: dict) -> dict:
        """
        Query historical accident data for route corridor.
        Maximum impact: ±30 points
        """
        summary = route.get("summary", "").lower()
        distance = route.get("distance_miles", 0)
        if distance == 0 and route.get("distance_meters"):
            distance = route["distance_meters"] * 0.000621371

        # Check if route matches any high-risk corridors
        matched_corridor = None
        for corridor in self.accident_database["high_risk_corridors"]:
            if any(term in summary for term in corridor["name"].lower().split()):
                matched_corridor = corridor
                break

        if matched_corridor:
            # High-risk corridor
            incidents = matched_corridor["annual_incidents"]
            severity = matched_corridor["severity_score"]

            # Calculate impact based on incident rate
            if incidents <= 5:
                score_impact = 30
            elif incidents <= 10:
                score_impact = 15
            elif incidents <= 20:
                score_impact = 0
            else:
                score_impact = -20

            # Adjust for severity
            if severity > 8.0:
                score_impact -= 10

            risk_factors = [
                {
                    "factor": "high_incident_corridor",
                    "impact": score_impact - 30,  # The negative portion
                    "details": f"{matched_corridor['name']}: {incidents} incidents/year, severity {severity}/10",
                    "primary_causes": matched_corridor["primary_causes"],
                }
            ]
        else:
            # Default/average safety corridor
            # Estimate based on distance (longer routes = more exposure)
            exposure_factor = min(distance / 100, 3)  # Cap at 3x
            base_incidents = 8 * exposure_factor

            score_impact = 15 if base_incidents <= 10 else 0

            risk_factors = []

        return {
            "score_impact": round(score_impact, 1),
            "risk_factors": risk_factors,
            "matched_corridor": matched_corridor["name"] if matched_corridor else "standard",
            "estimated_annual_incidents": matched_corridor["annual_incidents"]
            if matched_corridor
            else int(base_incidents),
        }

    async def evaluate_environmental_conditions(
        self, route: dict, current_conditions: dict, vehicle_config: dict = None
    ) -> dict:
        """
        Evaluate time of day, weather, and traffic conditions.
        Maximum impact: ±20 points
        """
        score_impact = 0
        risk_factors = []

        # Time of day analysis
        # Use is_day boolean from live weather if available, otherwise infer from hour
        is_day = current_conditions.get("is_day")
        if is_day is None:
            # Fallback: infer from time_of_day
            time_of_day = current_conditions.get("time_of_day", 12)
            is_day = 6 <= time_of_day < 20

        if not is_day:
            # Night
            time_category = "night"
            time_impact = -15
            risk_factors.append(
                {
                    "factor": "night_driving",
                    "impact": -15,
                    "details": "Night driving significantly increases risk",
                }
            )
        else:
            # Check if it's dusk/dawn period
            time_of_day = current_conditions.get("time_of_day", 12)
            if 6 <= time_of_day < 8 or 18 <= time_of_day < 20:
                time_category = "dusk_dawn"
                time_impact = -5
                risk_factors.append(
                    {
                        "factor": "low_visibility_time",
                        "impact": -5,
                        "details": "Dusk/dawn period with reduced visibility",
                    }
                )
            else:
                # Daytime
                time_category = "day"
                time_impact = 10

        score_impact += time_impact

        # Weather analysis
        # Use 'condition' from live weather API (clear, cloudy, rain, snow)
        weather = current_conditions.get("condition", current_conditions.get("weather", "clear"))
        weather_multiplier = self.accident_database["weather_multipliers"].get(weather, 1.0)

        if weather != "clear":
            weather_impact = -10 * (weather_multiplier - 1.0)
            score_impact += weather_impact
            risk_factors.append(
                {
                    "factor": f"adverse_weather_{weather}",
                    "impact": round(weather_impact, 1),
                    "details": f"Weather conditions: {weather} ({weather_multiplier}x risk multiplier)",
                }
            )
        else:
            score_impact += 10  # Bonus for clear weather

        # Wind risk (new feature from live weather)
        wind_speed = current_conditions.get("wind_speed_kmh", 0)
        if wind_speed > 50:
            score_impact -= 10
            risk_factors.append(
                {
                    "factor": "high_winds",
                    "impact": -10,
                    "details": f"Wind speeds of {wind_speed:.0f} km/h detected",
                }
            )

        # EV Specific Risks (Extreme cold affects battery)
        if (
            vehicle_config
            and "electric" in vehicle_config.get("type", "")
            and (weather in ["snow", "ice"] or current_conditions.get("temperature_c", 10) < 0)
        ):
            score_impact -= 5
            risk_factors.append(
                {
                    "factor": "ev_range_risk_cold",
                    "impact": -5,
                    "details": "Cold weather significantly reduces EV range",
                }
            )

        # Traffic analysis (from route data)
        duration_in_traffic = route.get("duration_in_traffic_minutes")
        duration_normal = route.get("duration_minutes")

        if duration_in_traffic and duration_normal:
            traffic_delay_pct = ((duration_in_traffic - duration_normal) / duration_normal) * 100

            if traffic_delay_pct > 50:
                # Heavy traffic
                traffic_impact = -10
                risk_factors.append(
                    {
                        "factor": "heavy_traffic",
                        "impact": -10,
                        "details": f"{traffic_delay_pct:.0f}% traffic delay",
                    }
                )
            elif traffic_delay_pct > 20:
                # Moderate traffic
                traffic_impact = -5
                risk_factors.append(
                    {
                        "factor": "moderate_traffic",
                        "impact": -5,
                        "details": f"{traffic_delay_pct:.0f}% traffic delay",
                    }
                )
            else:
                # Light traffic
                traffic_impact = 0

            score_impact += traffic_impact

        return {
            "score_impact": round(score_impact, 1),
            "risk_factors": risk_factors,
            "conditions": {
                "time_category": time_category,
                "weather": weather,
                "weather_multiplier": weather_multiplier,
            },
        }

    async def adjust_for_driver_profile(self, route: dict, driver_profile: dict) -> dict:
        """
        Adjust score based on driver experience and route familiarity.
        Maximum impact: ±10 points
        """
        score_impact = 0
        risk_factors = []

        # Experience level
        years_experience = driver_profile.get("years_experience", 2)
        if years_experience >= 5:
            score_impact += 10
        elif years_experience >= 2:
            score_impact += 5
        else:
            score_impact -= 5
            risk_factors.append(
                {
                    "factor": "inexperienced_driver",
                    "impact": -5,
                    "details": f"Driver has only {years_experience} years experience",
                }
            )

        # Route familiarity
        times_driven = driver_profile.get("times_driven_route", 0)
        if times_driven >= 10:
            score_impact += 5
        elif times_driven >= 1:
            score_impact += 2
        else:
            score_impact -= 3
            risk_factors.append(
                {
                    "factor": "unfamiliar_route",
                    "impact": -3,
                    "details": "Driver has never driven this route",
                }
            )

        # Safety record
        incidents_per_100k = driver_profile.get("incidents_per_100k_miles", 1.0)
        if incidents_per_100k < 0.5:
            # Excellent record
            score_impact += 5
        elif incidents_per_100k > 1.0:
            # Poor record
            score_impact -= 10
            risk_factors.append(
                {
                    "factor": "poor_safety_record",
                    "impact": -10,
                    "details": f"Driver incident rate: {incidents_per_100k:.2f} per 100k miles",
                }
            )

        return {
            "score_impact": round(score_impact, 1),
            "risk_factors": risk_factors,
            "driver_assessment": {
                "experience_level": "expert"
                if years_experience >= 5
                else "experienced"
                if years_experience >= 2
                else "new",
                "route_familiarity": "high"
                if times_driven >= 10
                else "moderate"
                if times_driven >= 1
                else "none",
                "safety_rating": "excellent"
                if incidents_per_100k < 0.5
                else "good"
                if incidents_per_100k <= 1.0
                else "poor",
            },
        }

    async def generate_risk_mitigation_plan(self, analysis: dict) -> list[dict]:
        """
        Generate specific recommendations to mitigate identified risks.
        """
        risk_level = analysis["risk_level"]
        top_risks = analysis["top_risks"]
        route = analysis["route"]

        recommendations = []

        # Critical/High risk - strong interventions
        if risk_level in ["CRITICAL", "HIGH"]:
            recommendations.append(
                {
                    "priority": "critical",
                    "action": "Consider alternative route",
                    "reason": f"Route scored {risk_level} risk level",
                    "estimated_impact": "Could reduce incident probability by 40-60%",
                }
            )

        # Address specific risk factors
        for risk in top_risks:
            factor = risk.get("factor", "")

            if "night" in factor:
                recommendations.append(
                    {
                        "priority": "high",
                        "action": "Delay departure to daylight hours",
                        "reason": "Night driving significantly increases risk",
                        "estimated_impact": "Reduces risk by 25-35%",
                    }
                )

            elif "weather" in factor:
                recommendations.append(
                    {
                        "priority": "high",
                        "action": "Monitor weather and consider delay",
                        "reason": risk["details"],
                        "estimated_impact": "Wait for improved conditions",
                    }
                )

            elif "inexperienced" in factor or "unfamiliar" in factor:
                recommendations.append(
                    {
                        "priority": "medium",
                        "action": "Pair with experienced driver or provide route briefing",
                        "reason": risk["details"],
                        "estimated_impact": "Reduces risk by 15-20%",
                    }
                )

            elif "traffic" in factor:
                recommendations.append(
                    {
                        "priority": "medium",
                        "action": "Adjust departure time to avoid peak traffic",
                        "reason": risk["details"],
                        "estimated_impact": "Reduces congestion-related incidents",
                    }
                )

            elif "high_speed" in factor:
                recommendations.append(
                    {
                        "priority": "medium",
                        "action": "Enable speed monitoring alerts",
                        "reason": "High-speed corridor requires extra vigilance",
                        "estimated_impact": "Prevents speeding violations",
                    }
                )

            elif "ev_range" in factor:
                recommendations.append(
                    {
                        "priority": "high",
                        "action": "Ensure 100% charge before departure",
                        "reason": "Cold weather reduces EV range significantly",
                        "estimated_impact": "Prevents stranded vehicle",
                    }
                )

        # General recommendations
        distance = route.get("distance_miles", 0)
        if distance == 0 and route.get("distance_meters"):
            distance = route["distance_meters"] * 0.000621371

        if distance > 400:
            recommendations.append(
                {
                    "priority": "medium",
                    "action": "Plan mandatory rest stops",
                    "reason": "Long-distance route requires fatigue management",
                    "estimated_impact": "Prevents fatigue-related incidents",
                }
            )

        return recommendations
