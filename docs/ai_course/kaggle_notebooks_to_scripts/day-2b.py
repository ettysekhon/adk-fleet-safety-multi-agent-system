"""
Day 2-B: Agent Tool Patterns and Best Practices

This script demonstrates advanced tool patterns for production-ready agents:

1. Model Context Protocol (MCP): Connect to external MCP servers
2. Long-Running Operations: Tools that pause for human approval
3. Resumable Workflows: Handle pause and resume with state management

Reference: https://www.kaggle.com/code/kaggle5daysofai/day-2b-agent-tools-best-practices
"""

import asyncio
import uuid
import warnings

from adk_fleet_safety_multi_agent_system.helpers.env import load_env_and_verify_api_key
from google.adk.agents import LlmAgent
from google.adk.apps.app import App, ResumabilityConfig
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from mcp import StdioServerParameters


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


def create_mcp_image_toolset():
    """
    Create an MCP toolset connected to the Everything MCP Server.

    This demonstrates how to connect to an external MCP server that provides
    tools. The Everything server is a demo server that provides a `getTinyImage`
    tool for testing MCP integrations.

    In production, you would use MCP servers for services like:
    - Google Maps
    - GitHub
    - Slack
    - Databases
    - File systems

    Returns:
        McpToolset: Configured MCP toolset for image generation
    """
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=[
                    "-y",
                    "@modelcontextprotocol/server-everything",
                ],
                tool_filter=["getTinyImage"],
            ),
            timeout=30,
        )
    )


def create_image_agent(retry_config, mcp_toolset):
    """
    Create an image generation agent using MCP tools.

    This agent demonstrates how to use MCP tools from external servers.
    The agent can generate images using the MCP server's tools.

    Args:
        retry_config: HTTP retry configuration for API calls
        mcp_toolset: The MCP toolset to use

    Returns:
        LlmAgent: Configured image generation agent
    """
    return LlmAgent(
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        name="image_agent",
        instruction="Use the MCP Tool to generate images for user queries",
        tools=[mcp_toolset],
    )


# ============================================================================
# Section 3: Long-Running Operations
# ============================================================================

# Threshold for determining large orders that require approval
LARGE_ORDER_THRESHOLD = 5


def place_shipping_order(num_containers: int, destination: str, tool_context: ToolContext) -> dict:
    """
    Places a shipping order. Requires approval if ordering more than 5 containers.

    This function demonstrates a long-running operation that can pause for
    human approval. It handles three scenarios:
    1. Small orders (≤5 containers): Auto-approve immediately
    2. Large orders - First call: Request approval and pause
    3. Large orders - Resumed call: Process approval decision

    Args:
        num_containers: Number of containers to ship
        destination: Shipping destination
        tool_context: Tool context provided by ADK, used for requesting approval

    Returns:
        Dictionary with order status and details
    """
    # Scenario 1: Small orders (≤5 containers) auto-approve
    if num_containers <= LARGE_ORDER_THRESHOLD:
        return {
            "status": "approved",
            "order_id": f"ORD-{num_containers}-AUTO",
            "num_containers": num_containers,
            "destination": destination,
            "message": f"Order auto-approved: {num_containers} containers to {destination}",
        }

    # Scenario 2: Large order - First call, request approval and pause
    if not tool_context.tool_confirmation:
        tool_context.request_confirmation(
            hint=(
                f"Large order: {num_containers} containers to {destination}. "
                "Do you want to approve?"
            ),
            payload={"num_containers": num_containers, "destination": destination},
        )
        return {
            "status": "pending",
            "message": f"Order for {num_containers} containers requires approval",
        }

    # Scenario 3: Large order - Resumed call, process approval decision
    if tool_context.tool_confirmation.confirmed:
        return {
            "status": "approved",
            "order_id": f"ORD-{num_containers}-HUMAN",
            "num_containers": num_containers,
            "destination": destination,
            "message": f"Order approved: {num_containers} containers to {destination}",
        }
    else:
        return {
            "status": "rejected",
            "message": f"Order rejected: {num_containers} containers to {destination}",
        }


def create_shipping_agent(retry_config):
    """
    Create a shipping coordinator agent with long-running operation support.

    This agent uses a tool that can pause for human approval when processing
    large orders.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        LlmAgent: Configured shipping coordinator agent
    """
    return LlmAgent(
        name="shipping_agent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction="""You are a shipping coordinator assistant.

  When users request to ship containers:
   1. Use the place_shipping_order tool with the number of containers and destination
   2. If the order status is 'pending', inform the user that approval is required
   3. After receiving the final result, provide a clear summary including:
      - Order status (approved/rejected)
      - Order ID (if available)
      - Number of containers and destination
   4. Keep responses concise but informative
  """,
        tools=[FunctionTool(func=place_shipping_order)],
    )


def create_resumable_shipping_app(shipping_agent):
    """
    Create a resumable app wrapper for the shipping agent.

    The App with resumability enabled adds a persistence layer that saves and
    restores state. This is essential for long-running operations that pause
    and resume.

    When a tool pauses:
    - All conversation messages are saved
    - Tool call details are saved
    - Tool parameters are saved
    - Pause location is saved

    When resuming:
    - The app loads the saved state
    - The agent continues exactly where it left off

    Args:
        shipping_agent: The shipping agent to wrap

    Returns:
        App: Configured resumable app
    """
    return App(
        name="shipping_coordinator",
        root_agent=shipping_agent,
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


# ============================================================================
# Section 4: Workflow Helpers
# ============================================================================


def check_for_approval(events):
    """
    Check if events contain an approval request.

    This function detects the special `adk_request_confirmation` event that
    ADK creates when a tool calls `request_confirmation()`. This event
    signals that the agent has paused and is waiting for human input.

    Args:
        events: List of events from the agent execution

    Returns:
        dict with approval details (approval_id, invocation_id) or None
    """
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.function_call and part.function_call.name == "adk_request_confirmation":
                    return {
                        "approval_id": part.function_call.id,
                        "invocation_id": event.invocation_id,
                    }
    return None


def print_agent_response(events):
    """
    Print agent's text responses from events.

    This helper extracts and displays text content from agent events.

    Args:
        events: List of events from the agent execution
    """
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"Agent > {part.text}")


def create_approval_response(approval_info, approved):
    """
    Create approval response message for resuming the agent.

    This function formats the human decision (approve/reject) into a format
    that ADK understands for resuming a paused execution.

    Args:
        approval_info: Dictionary with approval_id and invocation_id
        approved: Boolean indicating whether the request was approved

    Returns:
        Content: Formatted approval response
    """
    confirmation_response = types.FunctionResponse(
        id=approval_info["approval_id"],
        name="adk_request_confirmation",
        response={"confirmed": approved},
    )
    return types.Content(role="user", parts=[types.Part(function_response=confirmation_response)])


async def run_shipping_workflow(runner, session_service, query: str, auto_approve: bool = True):
    """
    Run a shipping workflow with approval handling.

    This function orchestrates the entire long-running operation workflow:
    1. Sends initial request to the agent
    2. Detects if the agent paused for approval
    3. Handles approval decision and resumes if needed

    Args:
        runner: The Runner instance configured with the resumable app
        session_service: The session service for managing sessions
        query: User's shipping request
        auto_approve: Whether to auto-approve large orders (simulates human decision)
    """
    print(f"\n{'=' * 60}")
    print(f"User > {query}\n")

    # Generate unique session ID
    session_id = f"order_{uuid.uuid4().hex[:8]}"

    # Create session
    await session_service.create_session(
        app_name="shipping_coordinator", user_id="test_user", session_id=session_id
    )

    query_content = types.Content(role="user", parts=[types.Part(text=query)])
    events = []

    # Step 1: Send initial request to the agent
    # If num_containers > 5, the agent returns the special `adk_request_confirmation` event
    async for event in runner.run_async(
        user_id="test_user", session_id=session_id, new_message=query_content
    ):
        events.append(event)

    # Step 2: Check if the agent paused for approval
    approval_info = check_for_approval(events)

    # Step 3: Handle approval workflow if needed
    if approval_info:
        print("Pausing for approval...")
        print(f"Human decision: {'APPROVE' if auto_approve else 'REJECT'}\n")

        # Resume the agent by calling run_async() again with the approval decision
        async for event in runner.run_async(
            user_id="test_user",
            session_id=session_id,
            new_message=create_approval_response(approval_info, auto_approve),
            invocation_id=approval_info[
                "invocation_id"
            ],  # Critical: same invocation_id tells ADK to RESUME
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Agent > {part.text}")
    else:
        # No approval needed - order completed immediately
        print_agent_response(events)

    print(f"{'=' * 60}\n")


# ============================================================================
# Main Execution
# ============================================================================


def extract_text_from_response(response):
    """
    Extract and return the text content from an agent response.

    Agent responses can contain various types of content. This function
    extracts just the text parts for display.

    Args:
        response: The response event from the agent

    Returns:
        str or None: The text content, or None if not found
    """
    if response and hasattr(response, "content") and response.content:
        for part in response.content.parts:
            if hasattr(part, "text") and part.text:
                return part.text
    return None


async def main():
    """
    Main function that sets up and runs the advanced tool pattern examples.

    This function demonstrates:
    1. MCP Integration (connecting to external MCP servers)
    2. Long-Running Operations (tools that pause for approval)
    3. Resumable Workflows (handling pause and resume)
    """
    # Load and verify API key from environment
    load_env_and_verify_api_key()
    print("ADK components imported successfully.")

    # Configure retry options for all agents
    retry_config = configure_retry_options()

    # ========================================================================
    # Section 2: MCP Integration Example
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 2: Model Context Protocol (MCP) - Image Generation")
    print("=" * 80)

    # Create MCP toolset
    mcp_image_server = create_mcp_image_toolset()
    print("MCP Toolset created (Everything Server with getTinyImage tool).")

    # Create image agent
    image_agent = create_image_agent(retry_config, mcp_image_server)
    print("Image agent created with MCP integration.")

    # Create runner and test
    from google.adk.runners import InMemoryRunner

    image_runner = InMemoryRunner(agent=image_agent, app_name="agents")
    print("Image runner created.")

    image_query = "Provide a sample tiny image"
    print(f"\nRunning image agent with query: {image_query}\n")

    image_response = await image_runner.run_debug(image_query, verbose=True)

    image_text = extract_text_from_response(image_response)
    if image_text:
        print("\nImage Agent - Response:")
        print("-" * 80)
        print(image_text)
        print("-" * 80)
    else:
        print("No text response found in the image agent output.")

    # Note: To display the actual image, you would decode the base64 data
    # from the function_response. This is shown in the notebook but omitted
    # here for simplicity in a script context.

    # ========================================================================
    # Section 3 & 4: Long-Running Operations Example
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 3 & 4: Long-Running Operations - Shipping Coordinator")
    print("=" * 80)

    # Create shipping agent
    shipping_agent = create_shipping_agent(retry_config)
    print("Shipping agent created with long-running operation support.")

    # Create resumable app
    shipping_app = create_resumable_shipping_app(shipping_agent)
    print("Resumable app created (enables pause/resume functionality).")

    # Create session service and runner
    session_service = InMemorySessionService()
    shipping_runner = Runner(
        app=shipping_app,  # Pass the app instead of the agent
        session_service=session_service,
    )
    print("Shipping runner created with resumability support.")

    # Demo 1: Small order (auto-approves)
    print("\n--- Demo 1: Small Order (Auto-Approved) ---")
    await run_shipping_workflow(shipping_runner, session_service, "Ship 3 containers to Singapore")

    # Demo 2: Large order (approved)
    print("\n--- Demo 2: Large Order (Human Approved) ---")
    await run_shipping_workflow(
        shipping_runner,
        session_service,
        "Ship 10 containers to Rotterdam",
        auto_approve=True,
    )

    # Demo 3: Large order (rejected)
    print("\n--- Demo 3: Large Order (Human Rejected) ---")
    await run_shipping_workflow(
        shipping_runner,
        session_service,
        "Ship 8 containers to Los Angeles",
        auto_approve=False,
    )

    print("\n" + "=" * 80)
    print("All advanced tool pattern examples completed successfully!")
    print("=" * 80)

    # Allow MCP resources to clean up properly
    # This prevents cleanup errors during asyncio shutdown
    await asyncio.sleep(0.5)


def handle_exception(loop, context):
    """
    Custom exception handler for asyncio event loop.

    This catches exceptions that occur in background tasks during shutdown,
    specifically the MCP cleanup error that happens after main() completes.
    """
    exception = context.get("exception")
    if exception is not None:
        # Check if this is the expected MCP cleanup error
        error_msg = str(exception).lower()
        if isinstance(exception, RuntimeError) and (
            "cancel scope" in error_msg or "different task" in error_msg
        ):
            # This is the expected MCP cleanup error during shutdown
            # The script has already completed successfully, so we can ignore it
            return

    # For all other exceptions, use the default handler
    loop.default_exception_handler(context)


def run_main_safely():
    """
    Run main() with proper error handling for MCP cleanup issues.

    The MCP toolset creates background tasks that can cause cleanup errors
    during asyncio shutdown. This function handles those gracefully by
    setting a custom exception handler and suppressing the harmless shutdown
    error that occurs after successful completion.
    """
    # Suppress warnings about experimental features
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")

    # Set custom exception handler to catch MCP cleanup errors
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.set_exception_handler(handle_exception)

    try:
        loop.run_until_complete(main())
    except RuntimeError as e:
        # Catch any RuntimeError that wasn't handled by the exception handler
        error_msg = str(e).lower()
        if "cancel scope" in error_msg or "different task" in error_msg:
            # Expected cleanup error, already handled by exception handler
            pass
        else:
            # Re-raise if it's a different RuntimeError
            raise
    finally:
        # Clean up the event loop
        try:
            # Cancel all remaining tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            # Wait for tasks to complete cancellation
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            # Ignore errors during cleanup
            pass
        finally:
            loop.close()


if __name__ == "__main__":
    run_main_safely()
