"""
Day 3-B: Agent Memory

This script demonstrates long-term memory management for AI agents:

1. Memory Workflow: Initialize, ingest, and retrieve memories
2. Memory Initialization: Setting up MemoryService
3. Manual Memory Storage: Transferring session data to memory
4. Memory Retrieval: Using load_memory and preload_memory tools
5. Automatic Memory Storage: Using callbacks for automation
6. Memory Consolidation: Understanding intelligent memory extraction

Reference: https://www.kaggle.com/code/kaggle5daysofai/day-3b-agent-memory
"""

import asyncio

from google.adk.agents import LlmAgent
from google.adk.memory import InMemoryMemoryService
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import load_memory, preload_memory
from google.genai import types

from adk_fleet_safety_multi_agent_system.helpers.env import load_env_and_verify_api_key

APP_NAME = "MemoryDemoApp"
USER_ID = "demo_user"
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


async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str,
    session_id: str = "default",
    session_service=None,
):
    """
    Helper function to run queries in a session and display responses.

    This function manages session creation/retrieval, query processing, and
    response streaming. It supports both single queries and multiple queries
    in sequence.

    Args:
        runner_instance: The Runner instance to use
        user_queries: Single query string or list of query strings
        session_id: Unique identifier for the session
        session_service: The session service (if None, uses runner's service)
    """
    print(f"\n### Session: {session_id}")

    # Get app name and session service from the Runner
    app_name = runner_instance.app_name
    if session_service is None:
        session_service = runner_instance.session_service

    # Create or retrieve session
    try:
        session = await session_service.create_session(
            app_name=app_name, user_id=USER_ID, session_id=session_id
        )
    except Exception:
        session = await session_service.get_session(
            app_name=app_name, user_id=USER_ID, session_id=session_id
        )

    # Convert single query to list
    if isinstance(user_queries, str):
        user_queries = [user_queries]

    # Process each query
    for query in user_queries:
        print(f"\nUser > {query}")
        query_content = types.Content(role="user", parts=[types.Part(text=query)])

        # Stream agent response
        async for event in runner_instance.run_async(
            user_id=USER_ID, session_id=session.id, new_message=query_content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                text = event.content.parts[0].text
                if text and text != "None":
                    print(f"Model > {text}")


# ============================================================================
# Section 3: Initialize MemoryService
# ============================================================================


def create_memory_service():
    """
    Create an InMemoryMemoryService for development and testing.

    This service provides keyword-based search and in-memory storage.
    For production, use VertexAiMemoryBankService which provides LLM-powered
    consolidation and semantic search with persistent cloud storage.

    Returns:
        InMemoryMemoryService: Configured memory service
    """
    return InMemoryMemoryService()


def create_agent_with_memory(retry_config, memory_tool=None):
    """
    Create an agent with memory support.

    Args:
        retry_config: HTTP retry configuration for API calls
        memory_tool: Memory tool to add (load_memory or preload_memory, or None)

    Returns:
        LlmAgent: Configured agent
    """
    tools = []
    instruction = "Answer user questions in simple words."

    if memory_tool == "load_memory":
        tools = [load_memory]
        instruction += " Use load_memory tool if you need to recall past conversations."
    elif memory_tool == "preload_memory":
        tools = [preload_memory]
        instruction += " Past conversations are automatically loaded for context."

    return LlmAgent(
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        name="MemoryDemoAgent",
        instruction=instruction,
        tools=tools,
    )


def create_runner_with_memory(agent, session_service, memory_service):
    """
    Create a Runner with both Session and Memory services.

    The Runner requires both services to enable memory functionality:
    - session_service: Manages conversation threads and events
    - memory_service: Provides long-term knowledge storage

    Args:
        agent: The agent to use
        session_service: Session service for conversation management
        memory_service: Memory service for long-term storage

    Returns:
        Runner: Configured runner with memory support
    """
    return Runner(
        agent=agent,
        app_name=APP_NAME,
        session_service=session_service,
        memory_service=memory_service,
    )


# ============================================================================
# Section 4: Ingest Session Data into Memory
# ============================================================================


async def add_session_to_memory(memory_service, session_service, app_name, user_id, session_id):
    """
    Transfer session data to memory storage.

    This function takes a session and ingests it into the memory store,
    making the conversation available for future searches across sessions.

    Args:
        memory_service: The memory service to use
        session_service: The session service containing the session
        app_name: Application name
        user_id: User ID
        session_id: Session ID to transfer
    """
    # Get the session
    session = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    # Transfer to memory
    await memory_service.add_session_to_memory(session)
    print(f"Session '{session_id}' added to memory.")


async def inspect_session_events(session_service, app_name, user_id, session_id):
    """
    Inspect the events stored in a session.

    Args:
        session_service: The session service
        app_name: Application name
        user_id: User ID
        session_id: Session ID to inspect
    """
    session = await session_service.get_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

    print("\nSession contains:")
    for event in session.events:
        if event.content and event.content.parts:
            text = event.content.parts[0].text[:60] if event.content.parts[0].text else "(empty)"
            print(f"  {event.content.role}: {text}...")


# ============================================================================
# Section 5: Memory Retrieval
# ============================================================================


async def search_memory_directly(memory_service, app_name, user_id, query):
    """
    Search memories directly using the memory service.

    This is useful for debugging, analytics, or custom memory management UIs.
    The search_memory() method takes a text query and returns matching memories.

    Args:
        memory_service: The memory service to search
        app_name: Application name
        user_id: User ID
        query: Search query text
    """
    search_response = await memory_service.search_memory(
        app_name=app_name, user_id=user_id, query=query
    )

    print(f"\nSearch results for: '{query}'")
    print(f"  Found {len(search_response.memories)} relevant memories")
    print()

    for memory in search_response.memories:
        if memory.content and memory.content.parts:
            text = memory.content.parts[0].text[:80] if memory.content.parts[0].text else "(empty)"
            print(f"  [{memory.author}]: {text}...")


# ============================================================================
# Section 6: Automating Memory Storage
# ============================================================================


async def auto_save_to_memory(callback_context):
    """
    Callback function to automatically save session to memory after each agent turn.

    This callback is triggered after every agent response. It accesses the memory
    service and current session from the callback context and transfers the
    conversation to long-term storage automatically.

    Args:
        callback_context: Context provided by ADK with access to services
    """
    await callback_context._invocation_context.memory_service.add_session_to_memory(
        callback_context._invocation_context.session
    )


def create_auto_memory_agent(retry_config):
    """
    Create an agent with automatic memory saving and retrieval.

    This agent combines:
    - Automatic storage: after_agent_callback saves conversations
    - Automatic retrieval: preload_memory loads memories

    This creates a fully automated memory system with zero manual intervention.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        LlmAgent: Configured agent with automatic memory management
    """
    return LlmAgent(
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        name="AutoMemoryAgent",
        instruction="Answer user questions.",
        tools=[preload_memory],
        after_agent_callback=auto_save_to_memory,  # Saves after each turn!
    )


# ============================================================================
# Main Execution
# ============================================================================


async def main():
    """
    Main function that demonstrates all memory management features.

    This function demonstrates:
    1. Memory initialization and setup
    2. Manual memory storage (ingesting session data)
    3. Memory retrieval with load_memory tool
    4. Direct memory search
    5. Automatic memory storage with callbacks
    """
    # Load and verify API key from environment
    load_env_and_verify_api_key()
    print("ADK components imported successfully.")

    # Configure retry options for all agents
    retry_config = configure_retry_options()

    # ========================================================================
    # Section 3: Initialize MemoryService
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 3: Initialize MemoryService")
    print("=" * 80)

    # Create memory service
    memory_service = create_memory_service()
    print("MemoryService initialised (InMemoryMemoryService for development).")

    # Create session service
    session_service = InMemorySessionService()
    print("SessionService initialised.")

    # Create basic agent
    user_agent = create_agent_with_memory(retry_config)
    print("Agent created.")

    # Create runner with both services
    runner = create_runner_with_memory(user_agent, session_service, memory_service)
    print("Runner created with memory support!")
    print("   - Both SessionService and MemoryService are configured")
    print("   - Memory is available but not yet used (no memory tools added)")

    # ========================================================================
    # Section 4: Ingest Session Data into Memory
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 4: Ingest Session Data into Memory")
    print("=" * 80)

    # Have a conversation to populate the session
    print("\n--- Step 1: Having a conversation ---")
    await run_session(
        runner,
        "My favorite color is blue-green. Can you write a Haiku about it?",
        "conversation-01",
        session_service,
    )

    # Inspect session events
    await inspect_session_events(session_service, APP_NAME, USER_ID, "conversation-01")

    # Transfer session to memory
    print("\n--- Step 2: Transferring session to memory ---")
    await add_session_to_memory(
        memory_service, session_service, APP_NAME, USER_ID, "conversation-01"
    )

    # ========================================================================
    # Section 5: Enable Memory Retrieval
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 5: Enable Memory Retrieval")
    print("=" * 80)

    # Create agent with load_memory tool
    print("\n--- Creating agent with load_memory tool (reactive) ---")
    memory_agent = create_agent_with_memory(retry_config, memory_tool="load_memory")
    print("Agent created with load_memory tool.")
    print("   - Agent decides when to search memory")
    print("   - More efficient (saves tokens)")

    # Create runner with memory agent
    memory_runner = create_runner_with_memory(memory_agent, session_service, memory_service)

    # Test memory retrieval in a new session
    print("\n--- Testing memory retrieval in new session ---")
    print("(Agent should use load_memory to recall favorite color)")
    await run_session(memory_runner, "What is my favorite color?", "color-test", session_service)

    # Complete manual workflow test
    print("\n--- Complete Manual Workflow Test ---")
    await run_session(
        memory_runner, "My birthday is on March 15th.", "birthday-session-01", session_service
    )

    # Manually save birthday session to memory
    await add_session_to_memory(
        memory_service, session_service, APP_NAME, USER_ID, "birthday-session-01"
    )

    # Test retrieval in a completely new session
    print("\n--- Testing cross-session memory retrieval ---")
    await run_session(
        memory_runner,
        "When is my birthday?",
        "birthday-session-02",  # Different session ID
        session_service,
    )

    # Direct memory search
    print("\n--- Direct Memory Search ---")
    await search_memory_directly(
        memory_service, APP_NAME, USER_ID, "What is the user's favorite color?"
    )

    # ========================================================================
    # Section 6: Automating Memory Storage
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 6: Automating Memory Storage")
    print("=" * 80)

    # Create agent with automatic memory saving
    print("\n--- Creating agent with automatic memory management ---")
    auto_memory_agent = create_auto_memory_agent(retry_config)
    print("Agent created with:")
    print("   - after_agent_callback: Automatically saves after each turn")
    print("   - preload_memory: Automatically loads memory before each turn")

    # Create runner for auto-memory agent
    auto_runner = create_runner_with_memory(auto_memory_agent, session_service, memory_service)

    # Test automatic memory system
    print("\n--- Test 1: First conversation (auto-saved) ---")
    await run_session(
        auto_runner,
        "I gifted a new toy to my nephew on his 1st birthday!",
        "auto-save-test",
        session_service,
    )

    print("\n--- Test 2: Second conversation (auto-retrieved) ---")
    await run_session(
        auto_runner,
        "What did I gift my nephew?",
        "auto-save-test-2",  # Different session - proves memory works!
        session_service,
    )

    print("\n" + "=" * 80)
    print("All memory management examples completed successfully.")
    print("=" * 80)
    print("\nKey takeaways:")
    print("  - Memory provides long-term knowledge across multiple conversations")
    print("  - Sessions = short-term memory (single conversation)")
    print("  - Memory = long-term knowledge (across conversations)")
    print("  - load_memory: reactive (agent decides when to search)")
    print("  - preload_memory: proactive (always loads memory)")
    print("  - Callbacks enable automatic memory storage")
    print("  - Production: use VertexAiMemoryBankService for semantic search")


if __name__ == "__main__":
    asyncio.run(main())
