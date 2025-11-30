"""
Weather service for fetching live weather data from Open-Meteo API.

This module provides a maintainable way to fetch weather conditions
for fleet safety route planning and scoring.
"""

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def get_live_weather(location_str: str, mcp_client: Any = None) -> dict:
    """
    Fetch live weather for a location (lat/lng string or city name).

    Args:
        location_str: Either "lat,lng" format or a city name
        mcp_client: Optional MCP client for geocoding city names

    Returns:
        dict: Weather data with keys:
            - condition: str (clear, cloudy, rain, snow)
            - temperature_c: float
            - wind_speed_kmh: float
            - is_day: bool
    """
    try:
        # Try to parse as lat,lng
        lat, lng = location_str.split(",")
        lat = float(lat.strip())
        lng = float(lng.strip())
    except ValueError:
        # If it's a city name, geocode it first
        if mcp_client:
            try:
                geo_result = await mcp_client.call_tool(
                    "google_maps", "geocode_address", {"address": location_str}
                )
                geo_data = json.loads(geo_result)
                if geo_data.get("error"):
                    logger.warning(f"Geocoding failed for {location_str}, using default")
                    return _get_default_weather()
                loc = geo_data["data"]["location"]
                lat, lng = loc["lat"], loc["lng"]
            except Exception as e:
                logger.warning(f"Error geocoding {location_str}: {e}, using default")
                return _get_default_weather()
        else:
            logger.warning(f"No MCP client provided, cannot geocode {location_str}")
            return _get_default_weather()

    # Call Open-Meteo (Free, No Key Required)
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "current_weather": "true",
        "hourly": "visibility",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"Error fetching weather from Open-Meteo: {e}")
        return _get_default_weather()

    return {
        "condition": _map_weather_code(data["current_weather"]["weathercode"]),
        "temperature_c": data["current_weather"]["temperature"],
        "wind_speed_kmh": data["current_weather"]["windspeed"],
        "is_day": data["current_weather"]["is_day"] == 1,
    }


def _map_weather_code(code: int) -> str:
    """
    Map WMO weather code to simplified condition string.

    Args:
        code: WMO weather code (0-99)

    Returns:
        str: One of: clear, cloudy, rain, snow
    """
    if code == 0:
        return "clear"
    if code in [1, 2, 3]:
        return "cloudy"
    if code in [51, 53, 55, 61, 63, 65, 66, 67, 80, 81, 82]:
        return "rain"
    if code in [71, 73, 75, 77, 85, 86]:
        return "snow"
    return "cloudy"  # Default fallback


def _get_default_weather() -> dict:
    """Return default weather data when API calls fail."""
    return {
        "condition": "clear",
        "temperature_c": 10.0,
        "wind_speed_kmh": 0.0,
        "is_day": True,
    }
