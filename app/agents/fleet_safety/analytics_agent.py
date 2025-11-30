"""
Analytics Agent - Historical analysis and predictive insights
"""

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from google.adk.agents import LlmAgent


class AnalyticsAgent(LlmAgent):
    """
    Performs batch analytics on historical fleet data.

    Analyses:
    - Driver safety patterns (30-day, 90-day trends)
    - Route corridor risk scoring
    - Incident prediction models
    - Cost optimisation opportunities (including EV efficiency)
    - Performance benchmarking
    - Trend identification

    Runs as scheduled batch job or on-demand for reports.
    """

    mcp_client: Any = None
    historical_data: dict = {}

    def __init__(self, mcp_client):
        super().__init__(
            model="gemini-2.5-flash",
            name="analytics_agent",
            description="Fleet analytics and predictive insights specialist",
            instruction="""You are a fleet analytics expert specialising in safety and operational insights.

            YOUR CAPABILITIES:

            1. Driver Analytics
               - Safety score trends (30-day, 90-day)
               - Incident frequency and severity
               - Performance benchmarking vs fleet average
               - Improvement recommendations

            2. Route Analytics
               - Corridor risk scoring
               - Historical incident mapping
               - Time-of-day risk patterns
               - Seasonal trends

            3. Predictive Models
               - Incident probability scoring
               - High-risk driver identification
               - Route safety predictions
               - Maintenance-related safety correlation

            4. Cost Analysis
               - Fuel/Energy efficiency trends
               - EV vs Diesel cost comparison
               - Route optimisation savings
               - Incident cost impact
               - ROI calculations

            5. Performance Reporting
               - Executive dashboards
               - Safety KPIs
               - Trend identification
               - Benchmarking reports

            ANALYSIS METHODOLOGY:
            - Use statistical methods (moving averages, percentiles, correlations)
            - Identify outliers and anomalies
            - Provide actionable insights
            - Quantify business impact (£, % improvement)
            - Compare against industry benchmarks

            REPORT STRUCTURE:
            - Executive Summary (key findings, 2-3 sentences)
            - Key Metrics (numbers, trends)
            - Detailed Analysis (breakdown by dimension)
            - Recommendations (prioritised by impact)
            - Supporting Data (tables, calculations)

            Always cite your data sources and methodology.
            """,
            tools=[
                self.analyze_driver_patterns,
                self.identify_risk_corridors,
                self.predict_incident_probability,
                self.generate_summary,
                self.get_vehicle_safety_history,
                self.calculate_roi_metrics,
                self.benchmark_performance,
            ],
        )
        self.mcp_client = mcp_client
        self.historical_data = self._initialise_historical_data()

    def _initialise_historical_data(self) -> dict:
        """
        Initialise simulated historical data.
        """
        # Generate synthetic historical trip data
        trips = []
        now = datetime.now()
        for i in range(500):  # 500 historical trips
            # Simulate mixed fleet: 20% electric
            is_electric = (i % 5) == 0

            trip = {
                "trip_id": f"TRIP_{i:04d}",
                "date": (now - timedelta(days=(i % 90))).isoformat(),
                "driver_id": f"DRV_{(i % 25):03d}",  # 25 drivers
                "vehicle_id": f"VEH_{(i % 50):03d}",  # 50 vehicles
                "distance_miles": 100 + (i % 500),
                "duration_minutes": 120 + (i % 300),
                "safety_score": 70 + (i % 30),
                "incident_occurred": (i % 20) == 0,  # 5% incident rate
                "route_type": ["highway", "urban", "mixed"][(i % 3)],
                "fuel_type": "electric" if is_electric else "diesel",
            }

            if is_electric:
                # kWh consumed (approx 1.5 miles/kWh)
                trip["energy_kwh"] = trip["distance_miles"] / 1.5
            else:
                # Litres consumed
                trip["fuel_litres"] = 45 + (i % 150)  # Approx 45-195 litres

            trips.append(trip)

        # Generate incident records
        incidents = []
        incident_id = 0
        for trip in trips:
            if trip["incident_occurred"]:
                incidents.append(
                    {
                        "incident_id": f"INC_{incident_id:04d}",
                        "trip_id": trip["trip_id"],
                        "driver_id": trip["driver_id"],
                        "vehicle_id": trip["vehicle_id"],
                        "date": trip["date"],
                        "type": [
                            "speeding",
                            "harsh_braking",
                            "lane_departure",
                            "following_distance",
                        ][incident_id % 4],
                        "severity": ["low", "medium", "high"][incident_id % 3],
                        "cost": [500, 2000, 5000][incident_id % 3],
                    }
                )
                incident_id += 1

        return {
            "trips": trips,
            "incidents": incidents,
            "fleet_averages": {
                "avg_safety_score": 82.5,
                "avg_incident_rate": 0.05,
                "avg_fuel_efficiency": 3.0,  # miles per litre (diesel)
                "avg_energy_efficiency": 1.5,  # miles per kWh (electric)
                "avg_on_time_rate": 0.94,
            },
        }

    async def analyze_driver_patterns(self, driver_id: str, days_lookback: int = 30) -> dict:
        """
        Comprehensive driver safety analysis.
        """
        cutoff_date = datetime.now() - timedelta(days=days_lookback)

        # Get driver's trips
        driver_trips = [
            t
            for t in self.historical_data["trips"]
            if t["driver_id"] == driver_id and datetime.fromisoformat(t["date"]) >= cutoff_date
        ]

        if not driver_trips:
            return {"error": f"No trips found for driver {driver_id} in last {days_lookback} days"}

        # Get driver's incidents
        driver_incidents = [
            i
            for i in self.historical_data["incidents"]
            if i["driver_id"] == driver_id and datetime.fromisoformat(i["date"]) >= cutoff_date
        ]

        # Calculate metrics
        total_trips = len(driver_trips)
        total_miles = sum(t["distance_miles"] for t in driver_trips)
        incident_count = len(driver_incidents)
        incident_rate = incident_count / total_trips if total_trips > 0 else 0

        safety_scores = [t["safety_score"] for t in driver_trips]
        avg_safety_score = statistics.mean(safety_scores)
        safety_score_trend = self._calculate_trend(safety_scores)

        # Compare to fleet average
        fleet_avg = self.historical_data["fleet_averages"]
        safety_score_vs_fleet = avg_safety_score - fleet_avg["avg_safety_score"]
        incident_rate_vs_fleet = incident_rate - fleet_avg["avg_incident_rate"]

        # Identify patterns
        patterns = []

        # Incident type analysis
        if driver_incidents:
            incident_types = defaultdict(int)
            for inc in driver_incidents:
                incident_types[inc["type"]] += 1

            most_common_incident = max(incident_types.items(), key=lambda x: x[1])
            patterns.append(
                {
                    "pattern": "frequent_incident_type",
                    "details": f"Most common: {most_common_incident[0]} ({most_common_incident[1]} occurrences)",
                    "recommendation": f"Targeted training on {most_common_incident[0]}",
                }
            )

        # Safety score trend
        if safety_score_trend < -5:
            patterns.append(
                {
                    "pattern": "declining_safety",
                    "details": f"Safety score declining by {abs(safety_score_trend):.1f} points",
                    "recommendation": "Schedule coaching session",
                }
            )
        elif safety_score_trend > 5:
            patterns.append(
                {
                    "pattern": "improving_safety",
                    "details": f"Safety score improving by {safety_score_trend:.1f} points",
                    "recommendation": "Recognize and reward improvement",
                }
            )

        # Performance classification
        if avg_safety_score >= 90:
            performance_tier = "excellent"
        elif avg_safety_score >= 80:
            performance_tier = "good"
        elif avg_safety_score >= 70:
            performance_tier = "fair"
        else:
            performance_tier = "needs_improvement"

        return {
            "driver_id": driver_id,
            "analysis_period_days": days_lookback,
            "total_trips": total_trips,
            "total_miles": round(total_miles, 1),
            "incident_count": incident_count,
            "incident_rate": round(incident_rate, 4),
            "avg_safety_score": round(avg_safety_score, 1),
            "safety_score_trend": round(safety_score_trend, 1),
            "fleet_comparison": {
                "safety_score_vs_fleet": round(safety_score_vs_fleet, 1),
                "incident_rate_vs_fleet": round(incident_rate_vs_fleet, 4),
                "percentile_rank": self._calculate_percentile_rank(
                    avg_safety_score,
                    [t["safety_score"] for t in self.historical_data["trips"]],
                ),
            },
            "performance_tier": performance_tier,
            "patterns_identified": patterns,
            "timestamp": datetime.now().isoformat(),
        }

    async def identify_risk_corridors(
        self, min_incidents: int = 5, days_lookback: int = 90
    ) -> dict:
        """
        Identify high-risk route corridors from historical data.
        """
        cutoff_date = datetime.now() - timedelta(days=days_lookback)

        # Get recent incidents
        recent_incidents = [
            i
            for i in self.historical_data["incidents"]
            if datetime.fromisoformat(i["date"]) >= cutoff_date
        ]

        # In production, I would analyse actual route corridors
        # For demo, I analyse by route type
        corridors = defaultdict(
            lambda: {
                "incident_count": 0,
                "total_trips": 0,
                "incidents": [],
                "severity_scores": [],
            }
        )

        # Aggregate by route type
        recent_trips = [
            t
            for t in self.historical_data["trips"]
            if datetime.fromisoformat(t["date"]) >= cutoff_date
        ]

        for trip in recent_trips:
            corridor_key = trip["route_type"]
            corridors[corridor_key]["total_trips"] += 1

            # Check if incident occurred
            trip_incidents = [i for i in recent_incidents if i["trip_id"] == trip["trip_id"]]
            if trip_incidents:
                corridors[corridor_key]["incident_count"] += len(trip_incidents)
                corridors[corridor_key]["incidents"].extend(trip_incidents)

                for inc in trip_incidents:
                    severity_map = {"low": 1, "medium": 5, "high": 10}
                    corridors[corridor_key]["severity_scores"].append(
                        severity_map.get(inc["severity"], 5)
                    )

        # Calculate risk scores for each corridor
        risk_corridors = []
        for corridor_name, data in corridors.items():
            if data["incident_count"] >= min_incidents:
                incident_rate = (
                    data["incident_count"] / data["total_trips"] if data["total_trips"] > 0 else 0
                )
                avg_severity = (
                    statistics.mean(data["severity_scores"]) if data["severity_scores"] else 0
                )

                # Risk score (0-100, higher = more risk)
                risk_score = (incident_rate * 1000) + (avg_severity * 5)
                risk_score = min(100, risk_score)

                risk_corridors.append(
                    {
                        "corridor_name": corridor_name,
                        "incident_count": data["incident_count"],
                        "total_trips": data["total_trips"],
                        "incident_rate": round(incident_rate, 4),
                        "avg_severity": round(avg_severity, 2),
                        "risk_score": round(risk_score, 1),
                        "risk_level": "high"
                        if risk_score > 70
                        else "medium"
                        if risk_score > 40
                        else "low",
                    }
                )

        # Sort by risk score
        risk_corridors.sort(key=lambda x: x["risk_score"], reverse=True)

        return {
            "analysis_period_days": days_lookback,
            "corridors_analysed": len(corridors),
            "high_risk_corridors": [c for c in risk_corridors if c["risk_level"] == "high"],
            "all_risk_corridors": risk_corridors,
            "recommendations": self._generate_corridor_recommendations(risk_corridors),
            "timestamp": datetime.now().isoformat(),
        }

    async def predict_incident_probability(
        self,
        driver_id: str,
        route_type: str,
        time_of_day: int,
        weather: str = "clear",
    ) -> dict:
        """
        Predict incident probability using ML-style scoring.
        """
        # Get driver history
        driver_analysis = await self.analyze_driver_patterns(driver_id, days_lookback=90)

        if driver_analysis.get("error"):
            return driver_analysis

        # Base probability (fleet average)
        base_probability = self.historical_data["fleet_averages"]["avg_incident_rate"]

        # Driver factor
        driver_incident_rate = driver_analysis["incident_rate"]
        driver_factor = driver_incident_rate / base_probability if base_probability > 0 else 1.0

        # Route type factor (from historical data)
        route_incidents = [
            i
            for i in self.historical_data["incidents"]
            if any(
                t["trip_id"] == i["trip_id"] and t["route_type"] == route_type
                for t in self.historical_data["trips"]
            )
        ]
        route_trips = [t for t in self.historical_data["trips"] if t["route_type"] == route_type]
        route_incident_rate = (
            len(route_incidents) / len(route_trips) if route_trips else base_probability
        )
        route_factor = route_incident_rate / base_probability if base_probability > 0 else 1.0

        # Time of day factor
        if 6 <= time_of_day < 9 or 16 <= time_of_day < 19:
            time_factor = 1.3  # Rush hour
        elif time_of_day >= 22 or time_of_day < 6:
            time_factor = 2.2  # Night driving
        else:
            time_factor = 1.0  # Normal daytime

        # Weather factor
        weather_factors = {
            "clear": 1.0,
            "rain": 2.1,
            "heavy_rain": 3.4,
            "snow": 4.2,
            "ice": 5.8,
        }
        weather_factor = weather_factors.get(weather, 1.0)

        # Combined probability
        predicted_probability = (
            base_probability * driver_factor * route_factor * time_factor * weather_factor
        )

        # Cap at reasonable maximum
        predicted_probability = min(0.50, predicted_probability)  # Max 50%

        # Risk classification
        if predicted_probability > 0.10:
            risk_classification = "high"
        elif predicted_probability > 0.05:
            risk_classification = "elevated"
        elif predicted_probability > 0.02:
            risk_classification = "moderate"
        else:
            risk_classification = "low"

        # Contributing factors
        factors = [
            {"factor": "driver_history", "multiplier": round(driver_factor, 2)},
            {"factor": "route_type", "multiplier": round(route_factor, 2)},
            {"factor": "time_of_day", "multiplier": round(time_factor, 2)},
            {"factor": "weather", "multiplier": round(weather_factor, 2)},
        ]
        factors.sort(key=lambda x: x["multiplier"], reverse=True)

        return {
            "driver_id": driver_id,
            "predicted_probability": round(predicted_probability, 4),
            "predicted_probability_pct": round(predicted_probability * 100, 2),
            "risk_classification": risk_classification,
            "baseline_probability": round(base_probability, 4),
            "contributing_factors": factors,
            "recommendations": self._generate_prediction_recommendations(
                predicted_probability, factors
            ),
            "confidence_level": "medium",  # Would be calculated from model validation
            "timestamp": datetime.now().isoformat(),
        }

    async def generate_summary(self, time_period: str = "today") -> dict:
        """
        Generate analytics summary for specified time period.
        """
        # Parse time period
        if time_period == "today":
            days = 1
        elif time_period == "week":
            days = 7
        elif time_period == "month":
            days = 30
        else:
            days = 30  # Default

        cutoff_date = datetime.now() - timedelta(days=days)

        # Filter data
        period_trips = [
            t
            for t in self.historical_data["trips"]
            if datetime.fromisoformat(t["date"]) >= cutoff_date
        ]

        period_incidents = [
            i
            for i in self.historical_data["incidents"]
            if datetime.fromisoformat(i["date"]) >= cutoff_date
        ]

        # Calculate metrics
        total_trips = len(period_trips)
        total_miles = sum(t["distance_miles"] for t in period_trips)
        incident_count = len(period_incidents)
        incident_rate = incident_count / total_trips if total_trips > 0 else 0

        avg_safety_score = (
            statistics.mean([t["safety_score"] for t in period_trips]) if period_trips else 0
        )

        # Fuel/Energy stats
        diesel_trips = [t for t in period_trips if t["fuel_type"] == "diesel"]
        electric_trips = [t for t in period_trips if t["fuel_type"] == "electric"]

        total_fuel = sum(t.get("fuel_litres", 0) for t in diesel_trips)
        total_energy = sum(t.get("energy_kwh", 0) for t in electric_trips)

        diesel_miles = sum(t["distance_miles"] for t in diesel_trips)
        electric_miles = sum(t["distance_miles"] for t in electric_trips)

        avg_efficiency_mpl = diesel_miles / total_fuel if total_fuel > 0 else 0
        avg_efficiency_mpkwh = electric_miles / total_energy if total_energy > 0 else 0

        # Cost analysis
        total_incident_cost = sum(i.get("cost", 0) for i in period_incidents)

        return {
            "time_period": time_period,
            "days": days,
            "total_trips": total_trips,
            "total_miles": round(total_miles, 1),
            "incident_count": incident_count,
            "incident_rate": round(incident_rate, 4),
            "avg_safety_score": round(avg_safety_score, 1),
            "avg_efficiency_mpl": round(avg_efficiency_mpl, 1),
            "avg_efficiency_mpkwh": round(avg_efficiency_mpkwh, 1),
            "total_incident_cost": round(total_incident_cost, 2),
            "previous_period_incidents": len(
                [
                    i
                    for i in self.historical_data["incidents"]
                    if datetime.fromisoformat(i["date"]) < cutoff_date
                    and datetime.fromisoformat(i["date"]) >= (cutoff_date - timedelta(days=days))
                ]
            ),
            "on_time_rate": self.historical_data["fleet_averages"]["avg_on_time_rate"],
            "timestamp": datetime.now().isoformat(),
        }

    async def get_vehicle_safety_history(self, vehicle_id: str, days: int = 30) -> dict:
        """
        Get safety history for specific vehicle.
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        vehicle_trips = [
            t
            for t in self.historical_data["trips"]
            if t["vehicle_id"] == vehicle_id and datetime.fromisoformat(t["date"]) >= cutoff_date
        ]

        vehicle_incidents = [
            i
            for i in self.historical_data["incidents"]
            if i["vehicle_id"] == vehicle_id and datetime.fromisoformat(i["date"]) >= cutoff_date
        ]

        if not vehicle_trips:
            return {
                "incident_count": 0,
                "safety_rating": "N/A",
                "note": f"No trips for vehicle {vehicle_id} in last {days} days",
            }

        incident_count = len(vehicle_incidents)
        avg_safety_score = statistics.mean([t["safety_score"] for t in vehicle_trips])

        if avg_safety_score >= 85:
            safety_rating = "excellent"
        elif avg_safety_score >= 75:
            safety_rating = "good"
        elif avg_safety_score >= 65:
            safety_rating = "fair"
        else:
            safety_rating = "poor"

        return {
            "vehicle_id": vehicle_id,
            "days_analyzed": days,
            "trip_count": len(vehicle_trips),
            "incident_count": incident_count,
            "avg_safety_score": round(avg_safety_score, 1),
            "safety_rating": safety_rating,
        }

    async def calculate_roi_metrics(self, intervention_cost: float) -> dict:
        """
        Calculate ROI for safety interventions.
        """
        # Current state
        annual_incidents = len(self.historical_data["incidents"]) * (
            365 / 90
        )  # Extrapolate to annual
        avg_incident_cost = statistics.mean(
            [i.get("cost", 0) for i in self.historical_data["incidents"]]
        )
        current_annual_cost = annual_incidents * avg_incident_cost

        # Projected improvement (industry benchmarks: 30-40% reduction)
        expected_reduction_pct = 0.35  # 35%
        projected_incidents = annual_incidents * (1 - expected_reduction_pct)
        projected_annual_cost = projected_incidents * avg_incident_cost

        annual_savings = current_annual_cost - projected_annual_cost

        # ROI calculation
        roi = (
            ((annual_savings - intervention_cost) / intervention_cost) * 100
            if intervention_cost > 0
            else 0
        )
        payback_months = (intervention_cost / (annual_savings / 12)) if annual_savings > 0 else 999

        return {
            "intervention_cost": round(intervention_cost, 2),
            "current_annual_incident_cost": round(current_annual_cost, 2),
            "projected_annual_incident_cost": round(projected_annual_cost, 2),
            "expected_annual_savings": round(annual_savings, 2),
            "roi_percentage": round(roi, 1),
            "payback_period_months": round(payback_months, 1),
            "five_year_net_benefit": round((annual_savings * 5) - intervention_cost, 2),
            "recommendation": "Highly recommended"
            if roi > 100
            else "Recommended"
            if roi > 50
            else "Consider alternatives",
        }

    async def benchmark_performance(self, metric: str = "safety_score") -> dict:
        """
        Benchmark fleet performance against industry standards.
        """
        # Industry benchmarks (from FMCSA/industry data)
        industry_benchmarks = {
            "safety_score": {"top_quartile": 90, "median": 82, "bottom_quartile": 70},
            "incident_rate": {
                "top_quartile": 0.02,
                "median": 0.05,
                "bottom_quartile": 0.10,
            },
            "fuel_efficiency": {
                "top_quartile": 3.5,  # approx 16 mpg
                "median": 2.8,  # approx 12.7 mpg
                "bottom_quartile": 2.3,  # approx 10.5 mpg
            },
        }

        # Fleet performance
        if metric == "safety_score":
            fleet_value = self.historical_data["fleet_averages"]["avg_safety_score"]
        elif metric == "incident_rate":
            fleet_value = self.historical_data["fleet_averages"]["avg_incident_rate"]
        elif metric == "fuel_efficiency":
            fleet_value = self.historical_data["fleet_averages"]["avg_fuel_efficiency"]
        else:
            return {"error": f"Unknown metric: {metric}"}

        benchmark = industry_benchmarks.get(metric, {})

        # Determine quartile
        if fleet_value >= benchmark["top_quartile"]:
            quartile = "top"
            performance = "excellent"
        elif fleet_value >= benchmark["median"]:
            quartile = "above_median"
            performance = "good"
        elif fleet_value >= benchmark["bottom_quartile"]:
            quartile = "below_median"
            performance = "fair"
        else:
            quartile = "bottom"
            performance = "needs_improvement"

        return {
            "metric": metric,
            "fleet_value": round(fleet_value, 2),
            "industry_benchmarks": benchmark,
            "quartile": quartile,
            "performance_rating": performance,
            "gap_to_top_quartile": round(benchmark["top_quartile"] - fleet_value, 2),
            "percentile_estimate": self._estimate_percentile(fleet_value, benchmark),
        }

    def _calculate_trend(self, values: list[float]) -> float:
        """Calculate trend (simple linear regression slope)"""
        if len(values) < 2:
            return 0.0

        n = len(values)
        x = list(range(n))

        x_mean = statistics.mean(x)
        y_mean = statistics.mean(values)

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0

        return slope * n  # Scale to total change over period

    def _calculate_percentile_rank(self, value: float, population: list[float]) -> int:
        """Calculate percentile rank"""
        if not population:
            return 50

        below = sum(1 for v in population if v < value)
        percentile = (below / len(population)) * 100

        return int(percentile)

    def _estimate_percentile(self, value: float, benchmark: dict) -> int:
        """Estimate percentile from benchmark quartiles"""
        if value >= benchmark["top_quartile"]:
            return 85
        elif value >= benchmark["median"]:
            return 65
        elif value >= benchmark["bottom_quartile"]:
            return 35
        else:
            return 15

    def _generate_corridor_recommendations(self, corridors: list[dict]) -> list[str]:
        """Generate recommendations based on corridor analysis"""
        recommendations = []

        high_risk = [c for c in corridors if c["risk_level"] == "high"]
        if high_risk:
            recommendations.append(
                f"Prioritise alternative routes for {len(high_risk)} high-risk corridors"
            )
            recommendations.append("Implement pre-trip safety briefings for high-risk routes")

        if corridors:
            top_corridor = corridors[0]
            recommendations.append(
                f"Focus training on incidents common in {top_corridor['corridor_name']} corridor"
            )

        return recommendations

    def _generate_prediction_recommendations(
        self, probability: float, factors: list[dict]
    ) -> list[str]:
        """Generate recommendations based on incident prediction"""
        recommendations = []

        if probability > 0.10:
            recommendations.append(
                "HIGH RISK: Consider delaying trip or assigning different driver"
            )
        elif probability > 0.05:
            recommendations.append(
                "ELEVATED RISK: Brief driver on specific hazards before departure"
            )

        # Address top contributing factor
        top_factor = factors[0]
        if top_factor["factor"] == "driver_history" and top_factor["multiplier"] > 1.5:
            recommendations.append("Schedule coaching session with driver to address patterns")
        elif top_factor["factor"] == "weather" and top_factor["multiplier"] > 2.0:
            recommendations.append("Delay trip until weather improves if possible")
        elif top_factor["factor"] == "time_of_day" and top_factor["multiplier"] > 1.5:
            recommendations.append("Adjust schedule to avoid high-risk time period")

        return recommendations
