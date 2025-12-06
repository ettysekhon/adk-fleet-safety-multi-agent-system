"""
Day 5-A: Agent2Agent (A2A) Communication

This script demonstrates agent-to-agent communication using the A2A protocol:

1. Creating Agents to Expose: Building agents that provide services
2. Exposing Agents via A2A: Using to_a2a() to make agents accessible
3. Consuming Remote Agents: Using RemoteA2aAgent to integrate external agents
4. Testing A2A Communication: Demonstrating cross-agent collaboration

Reference: https://www.kaggle.com/code/kaggle5daysofai/day-5a-agent2agent-communication
"""

import asyncio
import logging
import uuid
import warnings

from adk_fleet_safety_multi_agent_system.helpers.env import load_env_and_verify_api_key
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import (
    AGENT_CARD_WELL_KNOWN_PATH,
    AgentCardResolutionError,
    RemoteA2aAgent,
)
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Suppress experimental warnings for cleaner output
warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")

# Suppress aiohttp unclosed session warnings (these occur when connections fail)
logging.getLogger("aiohttp").setLevel(logging.CRITICAL)

# Suppress ADK's internal error logging for expected connection failures
logging.getLogger("google.adk.agents.remote_a2a_agent").setLevel(logging.CRITICAL)

# ============================================================================
# Configuration
# ============================================================================

MODEL_NAME = "gemini-2.5-flash-lite"
PRODUCT_CATALOG_PORT = 8001


def configure_retry_options():
    """
    Configure retry options for API calls.

    When working with LLMs, you may encounter transient errors like rate limits
    or temporary service unavailability. Retry options automatically handle these
    failures by retrying the request with exponential backoff.

    Returns:
        HttpRetryOptions: Configuration object for retry behaviour
    """
    return types.HttpRetryOptions(
        attempts=5,  # Maximum number of retry attempts
        exp_base=7,  # Exponential delay multiplier
        initial_delay=1,  # Initial delay before first retry (in seconds)
        http_status_codes=[429, 500, 503, 504],  # HTTP status codes to retry on
    )


# ============================================================================
# Section 1: Create the Product Catalog Agent (To Be Exposed)
# ============================================================================


def get_product_info(product_name: str) -> str:
    """
    Get product information for a given product.

    This tool simulates querying a vendor's product database. In production,
    this would query a real database or API.

    Args:
        product_name: Name of the product (e.g., "iPhone 15 Pro", "MacBook Pro")

    Returns:
        Product information as a string
    """
    # Mock product catalog - in production, this would query a real database
    product_catalog = {
        "iphone 15 pro": "iPhone 15 Pro, $999, Low Stock (8 units), 128GB, Titanium finish",
        "samsung galaxy s24": "Samsung Galaxy S24, $799, In Stock (31 units), 256GB, Phantom Black",
        "dell xps 15": 'Dell XPS 15, $1,299, In Stock (45 units), 15.6" display, 16GB RAM, 512GB SSD',
        "macbook pro 14": 'MacBook Pro 14", $1,999, In Stock (22 units), M3 Pro chip, 18GB RAM, 512GB SSD',
        "sony wh-1000xm5": "Sony WH-1000XM5 Headphones, $399, In Stock (67 units), Noise-canceling, 30hr battery",
        "ipad air": 'iPad Air, $599, In Stock (28 units), 10.9" display, 64GB',
        "lg ultrawide 34": 'LG UltraWide 34" Monitor, $499, Out of Stock, Expected: Next week',
    }

    product_lower = product_name.lower().strip()

    if product_lower in product_catalog:
        return f"Product: {product_catalog[product_lower]}"
    else:
        available = ", ".join([p.title() for p in product_catalog])
        return (
            f"Sorry, I don't have information for {product_name}. Available products: {available}"
        )


def create_product_catalog_agent(retry_config):
    """
    Create a Product Catalog Agent that provides product information.

    This agent will be exposed via A2A so other agents can consume it.
    In a real system, this would be maintained by an external vendor.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        LlmAgent: Configured product catalog agent
    """
    return LlmAgent(
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        name="product_catalog_agent",
        description="External vendor's product catalog agent that provides product information and availability.",
        instruction="""
    You are a product catalog specialist from an external vendor.
    When asked about products, use the get_product_info tool to fetch data from the catalog.
    Provide clear, accurate product information including price, availability, and specs.
    If asked about multiple products, look up each one.
    Be professional and helpful.
    """,
        tools=[get_product_info],
    )


# ============================================================================
# Section 2: Expose the Product Catalog Agent via A2A
# ============================================================================


def expose_agent_via_a2a(agent, port=PRODUCT_CATALOG_PORT):
    """
    Expose an agent via A2A protocol.

    The to_a2a() function:
    - Wraps your agent in an A2A-compatible server (FastAPI/Starlette)
    - Auto-generates an agent card that includes agent name, description, skills, etc.
    - Serves the agent card at /.well-known/agent-card.json (standard A2A path)
    - Handles all A2A protocol details (request/response formatting, task endpoints)

    Args:
        agent: The agent to expose
        port: Port where the agent will be served

    Returns:
        FastAPI/Starlette app that can be run with uvicorn
    """
    a2a_app = to_a2a(agent, port=port)
    return a2a_app


# ============================================================================
# Section 4: Create the Customer Support Agent (Consumer)
# ============================================================================


def create_remote_product_catalog_agent(server_url="http://localhost:8001"):
    """
    Create a RemoteA2aAgent that connects to a remote Product Catalog Agent.

    RemoteA2aAgent is a client-side proxy that:
    - Reads the remote agent's card from the well-known path
    - Translates sub-agent calls into A2A protocol requests
    - Handles all protocol details so you can use it like a regular sub-agent

    Args:
        server_url: Base URL of the remote agent server

    Returns:
        RemoteA2aAgent: Configured remote agent proxy
    """
    return RemoteA2aAgent(
        name="product_catalog_agent",
        description="Remote product catalog agent from external vendor that provides product information.",
        agent_card=f"{server_url}{AGENT_CARD_WELL_KNOWN_PATH}",
    )


def create_customer_support_agent(retry_config, remote_product_agent):
    """
    Create a Customer Support Agent that consumes the remote Product Catalog Agent.

    This agent demonstrates how to use RemoteA2aAgent as a sub-agent. The support
    agent can use the remote product catalog agent as if it were local.

    Args:
        retry_config: HTTP retry configuration for API calls
        remote_product_agent: The RemoteA2aAgent proxy for the product catalog

    Returns:
        LlmAgent: Configured customer support agent
    """
    return LlmAgent(
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        name="customer_support_agent",
        description="A customer support assistant that helps customers with product inquiries and information.",
        instruction="""
    You are a friendly and professional customer support agent.

    When customers ask about products:
    1. Use the product_catalog_agent sub-agent to look up product information
    2. Provide clear answers about pricing, availability, and specifications
    3. If a product is out of stock, mention the expected availability
    4. Be helpful and professional!

    Always get product information from the product_catalog_agent before answering customer questions.
    """,
        sub_agents=[remote_product_agent],
    )


# ============================================================================
# Section 5: Test A2A Communication
# ============================================================================


async def test_a2a_communication(runner, session_service, user_query: str):
    """
    Test A2A communication between Customer Support Agent and Product Catalog Agent.

    This function:
    1. Creates a new session for the conversation
    2. Sends the query to the Customer Support Agent
    3. Support Agent communicates with Product Catalog Agent via A2A
    4. Displays the response

    Args:
        runner: The Runner instance for the customer support agent
        session_service: The session service
        user_query: The question to ask the Customer Support Agent
    """
    # Session identifiers - use the same app_name as the runner
    app_name = runner.app_name
    user_id = "demo_user"
    session_id = f"demo_session_{uuid.uuid4().hex[:8]}"

    # Create session - handle case where session might already exist
    try:
        session = await session_service.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
    except Exception:
        # If session already exists, retrieve it
        session = await session_service.get_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )

    # Create the user message
    test_content = types.Content(parts=[types.Part(text=user_query)])

    # Display query
    print(f"\nCustomer: {user_query}")
    print("\nSupport agent response:")
    print("-" * 60)

    try:
        # Run the agent asynchronously
        # Use the session.id to ensure we're using the correct session reference
        async for event in runner.run_async(
            user_id=user_id, session_id=session.id, new_message=test_content
        ):
            # Print final response only
            if event.is_final_response() and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        print(part.text)
    except AgentCardResolutionError:
        # Handle expected error when server is not running
        # Suppress the exception's warning output by catching it early
        print(
            "\nExpected: Product Catalog Agent server is not running.\n"
            "This is normal - the server needs to be started separately.\n"
            "The script demonstrates the A2A setup correctly.\n"
            "\nTo test full A2A communication:\n"
            "  1. Save the A2A app to a Python file\n"
            "  2. Start the server: uvicorn <module>:app --host localhost --port 8001\n"
            "  3. Re-run this script"
        )
    except Exception as e:
        # Handle other connection-related errors
        error_msg = str(e).lower()
        error_type = type(e).__name__
        if (
            "agentcardresolutionerror" in error_type.lower()
            or "connection" in error_msg
            or "503" in error_msg
            or "failed to resolve" in error_msg
        ):
            print(
                "\nExpected: Product Catalog Agent server is not running.\n"
                "This is normal - the server needs to be started separately.\n"
                "The script demonstrates the A2A setup correctly.\n"
                "\nTo test full A2A communication:\n"
                "  1. Save the A2A app to a Python file\n"
                "  2. Start the server: uvicorn <module>:app --host localhost --port 8001\n"
                "  3. Re-run this script"
            )
        else:
            # Re-raise unexpected errors
            raise
    finally:
        # Ensure proper cleanup of async resources
        # This helps prevent "unclosed client session" warnings
        await asyncio.sleep(0.2)

    print("-" * 60)


# ============================================================================
# Main Execution
# ============================================================================


async def main():
    """
    Main function that demonstrates A2A communication features.

    This function demonstrates:
    1. Creating a product catalog agent
    2. Exposing it via A2A (conceptually - server needs to be run separately)
    3. Creating a customer support agent that consumes the remote agent
    4. Testing A2A communication (if server is running)
    """
    # Load and verify API key from environment
    load_env_and_verify_api_key()
    print("ADK components imported successfully.")

    # Configure retry options for all agents
    retry_config = configure_retry_options()

    # ========================================================================
    # Section 1: Create the Product Catalog Agent
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 1: Create the Product Catalog Agent (to be exposed)")
    print("=" * 80)

    product_catalog_agent = create_product_catalog_agent(retry_config)
    print("Product Catalog Agent created successfully.")
    print("   Model: gemini-2.5-flash-lite")
    print("   Tool: get_product_info()")
    print("   Ready to be exposed via A2A.")

    # ========================================================================
    # Section 2: Expose the Product Catalog Agent via A2A
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 2: Expose the Product Catalog Agent via A2A")
    print("=" * 80)

    # Create the A2A app (this would be run with uvicorn in production)
    # Note: The app is created but not started - it would be run separately with uvicorn
    _ = expose_agent_via_a2a(product_catalog_agent, PRODUCT_CATALOG_PORT)
    print("Product Catalog Agent is now A2A-compatible.")
    print(f"   Agent will be served at: http://localhost:{PRODUCT_CATALOG_PORT}")
    print(
        f"   Agent card will be at: http://localhost:{PRODUCT_CATALOG_PORT}{AGENT_CARD_WELL_KNOWN_PATH}"
    )
    print("\nTo start the server, run:")
    print(f"   uvicorn <module>:app --host localhost --port {PRODUCT_CATALOG_PORT}")
    print("   (The A2A app would be saved to a module and run with uvicorn)")

    # ========================================================================
    # Section 4: Create the Customer Support Agent
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 4: Create the Customer Support Agent (consumer)")
    print("=" * 80)

    # Create remote agent proxy
    remote_product_agent = create_remote_product_catalog_agent()
    print("Remote Product Catalog Agent proxy created.")
    print(f"   Connected to: http://localhost:{PRODUCT_CATALOG_PORT}")
    print(f"   Agent card: http://localhost:{PRODUCT_CATALOG_PORT}{AGENT_CARD_WELL_KNOWN_PATH}")

    # Create customer support agent
    customer_support_agent = create_customer_support_agent(retry_config, remote_product_agent)
    print("Customer Support Agent created.")
    print("   Model: gemini-2.5-flash-lite")
    print("   Sub-agents: 1 (remote Product Catalog Agent via A2A)")

    # ========================================================================
    # Section 5: Test A2A Communication
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 5: Test A2A Communication")
    print("=" * 80)

    print("\nNote: For full A2A testing, the Product Catalog Agent server must be running.")
    print("The server can be started using the A2A app created above.")
    print("For demonstration, this script shows the setup but actual")
    print("communication requires the server to be running.\n")

    # Create session service and runner
    # Note: Using app_name="agents" to match ADK's default expectation
    # This prevents the "app name mismatch" warning
    session_service = InMemorySessionService()
    runner = Runner(
        agent=customer_support_agent, app_name="agents", session_service=session_service
    )

    print("Testing A2A communication...")
    print("   (This will only work if the Product Catalog Agent server is running)")
    print()

    # Try to test (will fail if server is not running, but shows the pattern)
    # Error handling is done inside test_a2a_communication
    await test_a2a_communication(
        runner,
        session_service,
        "Can you tell me about the iPhone 15 Pro? Is it in stock?",
    )

    # Clean up async resources to prevent "unclosed client session" warnings
    # Give extra time for HTTP client cleanup
    await asyncio.sleep(0.3)

    # Force cleanup of any remaining async resources
    # This helps prevent aiohttp "unclosed client session" warnings
    import gc

    gc.collect()

    print("\n" + "=" * 80)
    print("A2A communication examples completed.")
    print("=" * 80)
    print("\nKey takeaways:")
    print("  - A2A protocol: standardised protocol for agent-to-agent communication")
    print("  - Exposing agents: use to_a2a() to make agents accessible with agent cards")
    print("  - Consuming agents: use RemoteA2aAgent to integrate remote agents")
    print("  - Cross-organisation: enables agents from different teams or companies to collaborate")
    print("  - Cross-language: agents can be in different languages or frameworks")
    print("  - Microservices: each agent can be an independent service")
    print("\nA2A use cases:")
    print("  • Cross-framework integration: ADK agent communicating with other frameworks")
    print("  • Cross-language communication: Python agent calling Java or Node.js agents")
    print("  • Cross-organisation boundaries: internal agents integrating with vendor services")
    print("\nWhen to use A2A vs local sub-agents:")
    print("  • A2A: external services, different codebases, network communication needed")
    print("  • Local sub-agents: same codebase, internal, low latency required")


if __name__ == "__main__":
    asyncio.run(main())
