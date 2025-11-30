"""
Day 3-A: Agent Sessions

This script demonstrates session management for stateful AI agents:

1. Session Management: Understanding sessions, events, and state
2. Persistent Sessions: Using DatabaseSessionService for persistence
3. Context Compaction: Automatically summarising conversation history
4. Session State: Managing structured data across conversation turns

Reference: https://www.kaggle.com/code/kaggle5daysofai/day-3a-agent-sessions
"""

import asyncio
import os
from typing import Any

from google.adk.agents import Agent, LlmAgent
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService, InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from adk_fleet_safety_multi_agent_system.helpers.env import load_env_and_verify_api_key

# ============================================================================
# Configuration
# ============================================================================

APP_NAME = "default"
USER_ID = "default"
MODEL_NAME = "gemini-2.5-flash-lite"


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
# Helper Functions
# ============================================================================


async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str = None,
    session_name: str = "default",
    session_service=None,
):
    """
    Helper function that manages a complete conversation session.

    This function handles session creation/retrieval, query processing, and
    response streaming. It supports both single queries and multiple queries
    in sequence.

    Args:
        runner_instance: The Runner instance to use
        user_queries: Single query string or list of query strings
        session_name: Unique identifier for the session
        session_service: The session service (if None, uses runner's service)
    """
    print(f"\n### Session: {session_name}")

    # Get app name and session service from the Runner
    app_name = runner_instance.app_name
    if session_service is None:
        session_service = runner_instance.session_service

    # Attempt to create a new session or retrieve an existing one
    try:
        session = await session_service.create_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )
    except Exception:
        session = await session_service.get_session(
            app_name=app_name, user_id=USER_ID, session_id=session_name
        )

    # Process queries if provided
    if user_queries:
        # Convert single query to list for uniform processing
        if isinstance(user_queries, str):
            user_queries = [user_queries]

        # Process each query in the list sequentially
        for query in user_queries:
            print(f"\nUser > {query}")

            # Convert the query string to the ADK Content format
            query_content = types.Content(role="user", parts=[types.Part(text=query)])

            # Stream the agent's response asynchronously
            async for event in runner_instance.run_async(
                user_id=USER_ID, session_id=session.id, new_message=query_content
            ):
                # Check if the event contains valid content
                if event.content and event.content.parts:
                    # Filter out empty or "None" responses before printing
                    part = event.content.parts[0]
                    if hasattr(part, "text") and part.text and part.text != "None":
                        print(f"{MODEL_NAME} > {part.text}")
    else:
        print("No queries!")


# ============================================================================
# Section 2: Session Management
# ============================================================================


def create_stateful_agent(retry_config):
    """
    Create a basic stateful agent using InMemorySessionService.

    This agent can maintain conversation context within a session, but the
    session data is lost when the application stops (stored in RAM only).

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        tuple: (agent, session_service, runner)
    """
    # Step 1: Create the LLM Agent
    root_agent = Agent(
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        name="text_chat_bot",
        description="A text chatbot",
    )

    # Step 2: Set up Session Management
    # InMemorySessionService stores conversations in RAM (temporary)
    session_service = InMemorySessionService()

    # Step 3: Create the Runner
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

    return root_agent, session_service, runner


# ============================================================================
# Section 3: Persistent Sessions
# ============================================================================


def create_persistent_agent(retry_config, db_url="sqlite:///data/my_agent_data.db"):
    """
    Create a persistent agent using DatabaseSessionService.

    This agent stores conversation history in a database, so sessions survive
    application restarts, crashes, and deployments.

    Args:
        retry_config: HTTP retry configuration for API calls
        db_url: Database URL (defaults to SQLite file)

    Returns:
        tuple: (agent, session_service, runner)
    """
    # Step 1: Create the agent
    chatbot_agent = LlmAgent(
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        name="text_chat_bot",
        description="A text chatbot with persistent memory",
    )

    # Step 2: Switch to DatabaseSessionService
    # SQLite database will be created automatically
    session_service = DatabaseSessionService(db_url=db_url)

    # Step 3: Create a new runner with persistent storage
    runner = Runner(agent=chatbot_agent, app_name=APP_NAME, session_service=session_service)

    return chatbot_agent, session_service, runner


# ============================================================================
# Section 4: Context Compaction
# ============================================================================


def create_compacting_app(chatbot_agent, retry_config, db_url="sqlite:///data/my_agent_data.db"):
    """
    Create an app with context compaction enabled.

    Context compaction automatically summarises conversation history to reduce
    context size, improve performance, and lower costs. It triggers after a
    specified number of turns and keeps a configurable overlap for context.

    Args:
        chatbot_agent: The agent to use
        retry_config: HTTP retry configuration for API calls
        db_url: Database URL for persistent storage

    Returns:
        tuple: (app, session_service, runner)
    """
    # Create an app with Events Compaction enabled
    research_app_compacting = App(
        name="research_app_compacting",
        root_agent=chatbot_agent,
        events_compaction_config=EventsCompactionConfig(
            compaction_interval=3,  # Trigger compaction every 3 invocations
            overlap_size=1,  # Keep 1 previous turn for context
        ),
    )

    # Set up persistent session service
    session_service = DatabaseSessionService(db_url=db_url)

    # Create a new runner for our upgraded app
    research_runner_compacting = Runner(
        app=research_app_compacting, session_service=session_service
    )

    return research_app_compacting, session_service, research_runner_compacting


async def verify_compaction(session_service, runner, session_id):
    """
    Verify that compaction occurred by inspecting session events.

    Args:
        session_service: The session service
        runner: The runner instance
        session_id: The session ID to inspect
    """
    # Get the final session state
    final_session = await session_service.get_session(
        app_name=runner.app_name, user_id=USER_ID, session_id=session_id
    )

    print("\n--- Searching for compaction summary event ---")
    found_summary = False
    for event in final_session.events:
        # Compaction events have a 'compaction' attribute in actions
        if event.actions and hasattr(event.actions, "compaction") and event.actions.compaction:
            print("\nSUCCESS: Found the compaction event:")
            print(f"  Author: {event.author}")
            print(f"\n Compacted information: {event}")
            found_summary = True
            break

    if not found_summary:
        print("\nNo compaction event found. Try increasing the number of turns.")


# ============================================================================
# Section 5: Session State Management
# ============================================================================


def save_userinfo(tool_context: ToolContext, user_name: str, country: str) -> dict[str, Any]:
    """
    Tool to record and save user name and country in session state.

    This demonstrates how tools can write to session state using tool_context.
    The 'user:' prefix indicates this is user-specific data.

    Args:
        tool_context: Tool context provided by ADK
        user_name: The username to store in session state
        country: The name of the user's country

    Returns:
        Dictionary with status
    """
    # Write to session state using the 'user:' prefix for user data
    tool_context.state["user:name"] = user_name
    tool_context.state["user:country"] = country

    return {"status": "success"}


def retrieve_userinfo(tool_context: ToolContext) -> dict[str, Any]:
    """
    Tool to retrieve user name and country from session state.

    This demonstrates how tools can read from session state.

    Args:
        tool_context: Tool context provided by ADK

    Returns:
        Dictionary with status and user information
    """
    # Read from session state
    user_name = tool_context.state.get("user:name", "Username not found")
    country = tool_context.state.get("user:country", "Country not found")

    return {"status": "success", "user_name": user_name, "country": country}


def create_state_management_agent(retry_config):
    """
    Create an agent with session state management tools.

    This agent can save and retrieve user information from session state,
    demonstrating how to manage structured data across conversation turns.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        tuple: (agent, session_service, runner)
    """
    # Create an agent with session state tools
    root_agent = LlmAgent(
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        name="text_chat_bot",
        description="""A text chatbot.
    Tools for managing user context:
    * To record username and country when provided use `save_userinfo` tool.
    * To fetch username and country when required use `retrieve_userinfo` tool.
    """,
        tools=[save_userinfo, retrieve_userinfo],
    )

    # Set up session service and runner
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, session_service=session_service, app_name=APP_NAME)

    return root_agent, session_service, runner


async def inspect_session_state(session_service, app_name, session_id):
    """
    Inspect the state of a session to see what data is stored.

    Args:
        session_service: The session service
        app_name: The application name
        session_id: The session ID to inspect
    """
    # Retrieve the session and inspect its state
    session = await session_service.get_session(
        app_name=app_name, user_id=USER_ID, session_id=session_id
    )

    print("\nSession state contents:")
    print(session.state)
    print("\nNotice the 'user:name' and 'user:country' keys storing our data.")


# ============================================================================
# Main Execution
# ============================================================================


async def main():
    """
    Main function that demonstrates all session management features.

    This function demonstrates:
    1. Basic session management with InMemorySessionService
    2. Persistent sessions with DatabaseSessionService
    3. Context compaction for efficient context management
    4. Session state management with custom tools
    """
    # Load and verify API key from environment
    load_env_and_verify_api_key()
    print("ADK components imported successfully.")

    # Configure retry options for all agents
    retry_config = configure_retry_options()

    # ========================================================================
    # Section 2: Basic Session Management
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 2: Session Management - InMemorySessionService")
    print("=" * 80)

    stateful_agent, stateful_session_service, stateful_runner = create_stateful_agent(retry_config)
    print("Stateful agent initialised!")
    print(f"   - Application: {APP_NAME}")
    print(f"   - User: {USER_ID}")
    print(f"   - Using: {stateful_session_service.__class__.__name__}")

    # Test stateful conversation
    print("\n--- Testing Stateful Conversation ---")
    await run_session(
        stateful_runner,
        [
            "Hi, I am Sam! What is the capital of United States?",
            "Hello! What is my name?",  # Agent should remember!
        ],
        "stateful-agentic-session",
        stateful_session_service,
    )

    # ========================================================================
    # Section 3: Persistent Sessions
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 3: Persistent Sessions - DatabaseSessionService")
    print("=" * 80)

    # Clean up any existing database
    db_file = "data/my_agent_data.db"
    os.makedirs("data", exist_ok=True)  # Ensure data directory exists
    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"Cleaned up existing database: {db_file}")

    persistent_agent, persistent_session_service, persistent_runner = create_persistent_agent(
        retry_config
    )
    print("Upgraded to persistent sessions!")
    print(f"   - Database: {db_file}")
    print("   - Sessions will survive restarts!")

    # Test persistent conversation
    print("\n--- Test Run 1: Initial Conversation ---")
    await run_session(
        persistent_runner,
        [
            "Hi, I am Sam! What is the capital of the United States?",
            "Hello! What is my name?",
        ],
        "test-db-session-01",
        persistent_session_service,
    )

    # Test session isolation
    print("\n--- Testing Session Isolation ---")
    await run_session(
        persistent_runner,
        ["Hello! What is my name?"],
        "test-db-session-02",  # Different session
        persistent_session_service,
    )

    # ========================================================================
    # Section 4: Context Compaction
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 4: Context Compaction")
    print("=" * 80)

    compacting_app, compacting_session_service, compacting_runner = create_compacting_app(
        persistent_agent, retry_config
    )
    print("Research App upgraded with Events Compaction!")
    print("   - Compaction interval: 3 turns")
    print("   - Overlap size: 1 turn")

    # Run a conversation long enough to trigger compaction
    print("\n--- Running Conversation to Trigger Compaction ---")
    await run_session(
        compacting_runner,
        "What is the latest news about AI in healthcare?",
        "compaction_demo",
        compacting_session_service,
    )
    await run_session(
        compacting_runner,
        "Are there any new developments in drug discovery?",
        "compaction_demo",
        compacting_session_service,
    )
    await run_session(
        compacting_runner,
        "Tell me more about the second development you found.",
        "compaction_demo",
        compacting_session_service,
    )
    # Compaction should trigger after this turn!
    await run_session(
        compacting_runner,
        "Who are the main companies involved in that?",
        "compaction_demo",
        compacting_session_service,
    )

    # Verify compaction occurred
    await verify_compaction(compacting_session_service, compacting_runner, "compaction_demo")

    # ========================================================================
    # Section 5: Session State Management
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 5: Session State Management")
    print("=" * 80)

    state_agent, state_session_service, state_runner = create_state_management_agent(retry_config)
    print("Agent with session state tools initialised!")

    # Test session state
    print("\n--- Testing Session State ---")
    await run_session(
        state_runner,
        [
            "Hi there, how are you doing today? What is my name?",  # Agent shouldn't know
            "My name is Sam. I'm from Poland.",  # Provide name - agent should save it
            "What is my name? Which country am I from?",  # Agent should recall
        ],
        "state-demo-session",
        state_session_service,
    )

    # Inspect session state
    await inspect_session_state(state_session_service, APP_NAME, "state-demo-session")

    # Test session isolation
    print("\n--- Testing Session State Isolation ---")
    await run_session(
        state_runner,
        ["Hi there, how are you doing today? What is my name?"],
        "new-isolated-session",
        state_session_service,
    )

    print("\n" + "=" * 80)
    print("All session management examples completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
