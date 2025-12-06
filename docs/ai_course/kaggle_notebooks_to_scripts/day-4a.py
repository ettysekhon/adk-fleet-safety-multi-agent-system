"""
Day 4-A: Agent Observability

This script demonstrates observability for AI agents:

1. Logging Configuration: Setting up DEBUG logs for debugging
2. Debugging with ADK Web UI: Using traces and events to find issues
3. Production Logging: Using LoggingPlugin for production observability
4. Custom Plugins: Building custom plugins with callbacks

Reference: https://www.kaggle.com/code/kaggle5daysofai/day-4a-agent-observability
"""

import asyncio
import logging
import os

from adk_fleet_safety_multi_agent_system.helpers.env import load_env_and_verify_api_key
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.adk.runners import InMemoryRunner
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.google_search_tool import google_search
from google.genai import types

# ============================================================================
# Configuration
# ============================================================================

MODEL_NAME = "gemini-2.5-flash-lite"
LOG_FILE = "logs/logger.log"


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


def setup_logging(log_file=LOG_FILE, log_level=logging.DEBUG):
    """
    Configure logging for debugging and observability.

    This sets up file-based logging with DEBUG level to capture detailed
    information about agent execution, LLM requests, and tool calls.

    Args:
        log_file: Path to the log file
        log_level: Logging level (default: DEBUG)
    """
    # Ensure logs directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # Clean up any previous logs
    if os.path.exists(log_file):
        os.remove(log_file)
        print(f"Cleaned up {log_file}")

    # Configure logging with DEBUG log level
    logging.basicConfig(
        filename=log_file,
        level=log_level,
        format="%(filename)s:%(lineno)s %(levelname)s:%(message)s",
    )

    print(f"Logging configured (level: {logging.getLevelName(log_level)})")
    print(f"Log file: {log_file}")


# ============================================================================
# Section 2: Debugging with Observability
# ============================================================================


def create_broken_research_agent(retry_config):
    """
    Create a research paper finder agent with an intentional bug.

    This agent has a bug: the count_papers function expects a List[str] but
    the agent's instruction might cause it to pass a string instead. This
    demonstrates how observability helps identify and fix issues.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        tuple: (google_search_agent, root_agent)
    """

    # Intentionally incorrect: function expects List[str] but agent might pass str
    def count_papers(papers: str):  # Bug: should be List[str]
        """
        This function counts the number of papers in a list of strings.

        Args:
            papers: A list of strings, where each string is a research paper.
                  (Note: This has a bug - the type hint says str but should be List[str])

        Returns:
            The number of papers in the list.
        """
        return len(papers)

    # Google Search agent
    google_search_agent = LlmAgent(
        name="google_search_agent",
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        description="Searches for information using Google search",
        instruction="""Use the google_search tool to find information on the given topic. Return the raw search results.
    If the user asks for a list of papers, then give them the list of research papers you found and not the summary.""",
        tools=[google_search],
    )

    # Root agent
    root_agent = LlmAgent(
        name="research_paper_finder_agent",
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        instruction="""Your task is to find research papers and count them.

    You MUST ALWAYS follow these steps:
    1) Find research papers on the user provided topic using the 'google_search_agent'.
    2) Then, pass the papers to 'count_papers' tool to count the number of papers returned.
    3) Return both the list of research papers and the total number of papers.
    """,
        tools=[AgentTool(agent=google_search_agent), count_papers],
    )

    return google_search_agent, root_agent


def create_fixed_research_agent(retry_config):
    """
    Create a fixed version of the research paper finder agent.

    This version fixes the bug by using the correct type hint for count_papers.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        tuple: (google_search_agent, root_agent)
    """

    # Fixed: function correctly expects List[str]
    def count_papers(papers: list[str]):
        """
        This function counts the number of papers in a list of strings.

        Args:
            papers: A list of strings, where each string is a research paper.

        Returns:
            The number of papers in the list.
        """
        return len(papers)

    # Google Search agent
    google_search_agent = LlmAgent(
        name="google_search_agent",
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        description="Searches for information using Google search",
        instruction="Use the google_search tool to find information on the given topic. Return the raw search results.",
        tools=[google_search],
    )

    # Root agent
    root_agent = LlmAgent(
        name="research_paper_finder_agent",
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        instruction="""Your task is to find research papers and count them.

    You must follow these steps:
    1) Find research papers on the user provided topic using the 'google_search_agent'.
    2) Then, pass the papers to 'count_papers' tool to count the number of papers returned.
    3) Return both the list of research papers and the total number of papers.
    """,
        tools=[AgentTool(agent=google_search_agent), count_papers],
    )

    return google_search_agent, root_agent


def extract_text_from_response(response):
    """
    Extract and return the text content from an agent response.

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


# ============================================================================
# Section 3: Production Logging with LoggingPlugin
# ============================================================================


def create_runner_with_logging(agent):
    """
    Create a runner with LoggingPlugin for production observability.

    The LoggingPlugin automatically captures:
    - User messages and agent responses
    - Timing data for performance analysis
    - LLM requests and responses for debugging
    - Tool calls and results
    - Complete execution traces

    Args:
        agent: The agent to use

    Returns:
        InMemoryRunner: Configured runner with logging plugin
    """
    return InMemoryRunner(
        agent=agent,
        plugins=[LoggingPlugin()],  # Handles standard observability logging
        app_name="agents",
    )


def print_log_file_contents(log_file=LOG_FILE):
    """
    Print the contents of the log file for debugging.

    This is useful for examining detailed logs after agent execution.

    Args:
        log_file: Path to the log file
    """
    if os.path.exists(log_file):
        print(f"\nExamining logs from {log_file}...\n")
        with open(log_file) as f:
            print(f.read())
    else:
        print(f"Log file {log_file} not found.")


# ============================================================================
# Main Execution
# ============================================================================


async def main():
    """
    Main function that demonstrates observability features.

    This function demonstrates:
    1. Setting up logging configuration
    2. Debugging a broken agent
    3. Using LoggingPlugin for production observability
    4. Testing the fixed agent
    """
    # Load and verify API key from environment
    load_env_and_verify_api_key()
    print("ADK components imported successfully.")

    # Configure retry options for all agents
    retry_config = configure_retry_options()

    # Set up logging
    setup_logging()

    # ========================================================================
    # Section 2: Debugging with Observability
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 2: Debugging with Observability")
    print("=" * 80)

    print("\n--- Creating Broken Agent (Intentional Bug) ---")
    print("The count_papers function has incorrect type hint (str instead of List[str])")
    _, broken_agent = create_broken_research_agent(retry_config)
    print("Broken agent created.")

    # Create runner for broken agent
    broken_runner = InMemoryRunner(agent=broken_agent, app_name="agents")
    print("Runner created for broken agent.")

    # Test the broken agent
    print("\n--- Testing Broken Agent ---")
    print("Query: 'Find latest quantum computing papers'")
    print("(Note: The count might be incorrect due to the bug)\n")

    try:
        broken_response = await broken_runner.run_debug(
            "Find latest quantum computing papers", verbose=True
        )
        broken_text = extract_text_from_response(broken_response)
        if broken_text:
            print("\nBroken Agent - Response:")
            print("-" * 80)
            print(broken_text)
            print("-" * 80)
        else:
            print("No text response found.")
    except Exception as e:
        print(f"\nError occurred (expected with broken agent): {e}")

    print("\n💡 Debugging Tip:")
    print("   - Check the logs above for detailed execution traces")
    print("   - Look for function_call arguments in the logs")
    print("   - The bug: count_papers receives a string instead of List[str]")
    print("   - Fix: Change the type hint in count_papers function")

    # ========================================================================
    # Section 3: Production Logging with LoggingPlugin
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 3: Production Logging with LoggingPlugin")
    print("=" * 80)

    print("\n--- Creating Fixed Agent ---")
    _, fixed_agent = create_fixed_research_agent(retry_config)
    print("Fixed agent created (correct type hint: List[str]).")

    # Create runner with LoggingPlugin
    print("\n--- Creating Runner with LoggingPlugin ---")
    logging_runner = create_runner_with_logging(fixed_agent)
    print("Runner created with LoggingPlugin.")
    print("   - Automatically captures all agent activity")
    print("   - Logs user messages, agent responses, tool calls, and traces")

    # Test the fixed agent with logging
    print("\n--- Testing Fixed Agent with LoggingPlugin ---")
    print("Query: 'Find recent papers on quantum computing'\n")

    logging_response = await logging_runner.run_debug(
        "Find recent papers on quantum computing", verbose=True
    )

    logging_text = extract_text_from_response(logging_response)
    if logging_text:
        print("\nFixed Agent - Response:")
        print("-" * 80)
        print(logging_text)
        print("-" * 80)
    else:
        print("No text response found.")

    # Print log file contents
    print("\n--- Log File Contents ---")
    print_log_file_contents()

    print("\n" + "=" * 80)
    print("Observability examples completed successfully.")
    print("=" * 80)
    print("\nKey takeaways:")
    print("  - Logs: record of single events (what happened)")
    print("  - Traces: connected logs showing the full sequence (why it happened)")
    print("  - Metrics: summary numbers (how well it is performing)")
    print("  - DEBUG logs: essential for development debugging")
    print("  - LoggingPlugin: production-ready observability solution")
    print("  - Custom plugins: build custom observability for specific needs")
    print("\nWhen to use which:")
    print("  • Development debugging → Use 'adk web --log_level DEBUG'")
    print("  • Common production observability → Use LoggingPlugin()")
    print("  • Custom requirements → Build custom plugins with callbacks")


if __name__ == "__main__":
    asyncio.run(main())
