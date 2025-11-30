"""
Environment and API key management utilities.

This module handles loading API keys from different sources:
- .env files (for local development)
- Environment variables (for deployed environments)
"""

import logging
import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

logger = logging.getLogger(__name__)


def is_running_in_agent_engine() -> bool:
    """Check if we're running inside Vertex AI Agent Engine."""
    # Agent Engine sets these environment variables automatically
    return (
        os.getenv("GOOGLE_CLOUD_PROJECT") is not None
        and os.getenv("K_SERVICE") is not None  # Cloud Run indicator
    )


def load_env_and_verify_api_key(require_maps_key: bool = False):
    """
    Load environment variables and verify API keys are set.

    This function tries multiple sources in order:
    1. .env file (if python-dotenv is available)
    2. Environment variables (already set in the environment)

    Note: When running in Agent Engine, GOOGLE_API_KEY is not required
    as the service uses Vertex AI authentication (service account).

    Args:
        require_maps_key (bool): If True, also verifies GOOGLE_MAPS_API_KEY is set.

    Returns:
        str: The GOOGLE_API_KEY if found, or None if running in Agent Engine

    Raises:
        ValueError: If required API keys are not set in any source (local dev only)
    """
    # Try loading from .env file (for local development)
    if load_dotenv is not None:
        load_dotenv()

    # Check if running in Agent Engine - uses Vertex AI auth, not API key
    if is_running_in_agent_engine():
        logger.info("Running in Agent Engine - using Vertex AI authentication")
        # Still check for Maps API key if required
        if require_maps_key:
            google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
            if not google_maps_api_key:
                raise ValueError(
                    "GOOGLE_MAPS_API_KEY is not set but required. Please set it in deployment env vars."
                )
        return None  # No API key needed in Agent Engine

    # Local development - require GOOGLE_API_KEY
    google_api_key = os.getenv("GOOGLE_API_KEY")

    if not google_api_key:
        raise ValueError(
            "GOOGLE_API_KEY is not set. Please set it in:\n"
            "- A .env file (for local development)\n"
            "- Environment variables (for deployed environments)"
        )

    if require_maps_key:
        google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        if not google_maps_api_key:
            raise ValueError(
                "GOOGLE_MAPS_API_KEY is not set but required for this script. Please set it in:\n"
                "- A .env file (for local development)\n"
                "- Environment variables (for deployed environments)"
            )

    return google_api_key


def setup_api_key():
    """
    Setup and verify Google API key, printing success or error message.

    This is a convenience function that calls load_env_and_verify_api_key()
    and handles errors gracefully with user-friendly messages.

    Returns:
        str: The GOOGLE_API_KEY if successful, None otherwise
    """
    try:
        api_key = load_env_and_verify_api_key()
        print("Gemini API key setup complete.")
        return api_key
    except Exception as e:
        print(
            f"Authentication Error: Please make sure you have added 'GOOGLE_API_KEY'. Details: {e}"
        )
        return None
