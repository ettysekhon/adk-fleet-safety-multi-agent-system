"""
Day 4-B: Agent Evaluation

This script demonstrates agent evaluation for testing and measuring performance:

1. Creating Evaluation Test Cases: Defining test scenarios
2. Evaluation Configuration: Setting pass/fail thresholds
3. Running Evaluations: Using CLI and programmatic evaluation
4. Analyzing Results: Understanding evaluation metrics

Reference: https://www.kaggle.com/code/kaggle5daysofai/day-4b-agent-evaluation
"""

import asyncio
import json
import os

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types

from adk_fleet_safety_multi_agent_system.helpers.env import load_env_and_verify_api_key

# ============================================================================
# Configuration
# ============================================================================

MODEL_NAME = "gemini-2.5-flash-lite"
AGENT_DIR = "agents/home_automation_agent"
TEST_CONFIG_FILE = f"{AGENT_DIR}/test_config.json"
EVALSET_FILE = f"{AGENT_DIR}/integration.evalset.json"


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
# Section 2: Create Home Automation Agent
# ============================================================================


def set_device_status(location: str, device_id: str, status: str) -> dict:
    """
    Sets the status of a smart home device.

    This tool simulates controlling smart home devices. A device's status can
    only be ON or OFF.

    Args:
        location: The room where the device is located
        device_id: The unique identifier for the device
        status: The desired status, either 'ON' or 'OFF'

    Returns:
        A dictionary confirming the action
    """
    print(f"Tool Call: Setting {device_id} in {location} to {status}")
    return {
        "success": True,
        "message": f"Successfully set the {device_id} in {location} to {status.lower()}.",
    }


def create_home_automation_agent(retry_config):
    """
    Create a home automation agent with deliberate flaws for evaluation.

    This agent is designed to demonstrate evaluation concepts. It has an
    overconfident instruction that claims to control "ALL smart devices"
    which will be tested through evaluation.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        LlmAgent: Configured home automation agent
    """
    return LlmAgent(
        model=Gemini(model=MODEL_NAME, retry_options=retry_config),
        name="home_automation_agent",
        description="An agent to control smart devices in a home.",
        instruction="""You are a home automation assistant. You control ALL smart devices in the house.

    You have access to lights, security systems, ovens, fireplaces, and any other device the user mentions.
    Always try to be helpful and control whatever device the user asks for.

    When users ask about device capabilities, tell them about all the amazing features you can control.""",
        tools=[set_device_status],
    )


# ============================================================================
# Section 4: Systematic Evaluation
# ============================================================================


def create_evaluation_config(output_file=TEST_CONFIG_FILE):
    """
    Create an evaluation configuration file.

    This file defines the pass/fail thresholds for evaluation metrics.
    It specifies criteria like tool trajectory scores and response match scores.

    Args:
        output_file: Path to the output configuration file
    """
    eval_config = {
        "criteria": {
            "tool_trajectory_avg_score": 1.0,  # Perfect tool usage required
            "response_match_score": 0.8,  # 80% text similarity threshold
        }
    }

    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(eval_config, f, indent=2)

    print(f"Evaluation configuration created: {output_file}")
    print("\nEvaluation criteria:")
    print("  • tool_trajectory_avg_score: 1.0 - requires exact tool usage match")
    print("  • response_match_score: 0.8 - requires 80% text similarity")
    print("\nWhat this evaluation will catch:")
    print("  - Incorrect tool usage (wrong device, location, or status)")
    print("  - Poor response quality and communication")
    print("  - Deviations from expected behaviour patterns")


def create_evaluation_test_cases(output_file=EVALSET_FILE):
    """
    Create evaluation test cases file.

    This file contains multiple test cases (sessions) that define expected
    behaviour for the agent. Each test case includes:
    - User input
    - Expected final response
    - Expected tool usage (intermediate data)

    Args:
        output_file: Path to the output evalset file
    """
    test_cases = {
        "eval_set_id": "home_automation_integration_suite",
        "eval_cases": [
            {
                "eval_id": "living_room_light_on",
                "conversation": [
                    {
                        "user_content": {
                            "parts": [{"text": "Please turn on the floor lamp in the living room"}]
                        },
                        "final_response": {
                            "parts": [
                                {
                                    "text": "Successfully set the floor lamp in the living room to on."
                                }
                            ]
                        },
                        "intermediate_data": {
                            "tool_uses": [
                                {
                                    "name": "set_device_status",
                                    "args": {
                                        "location": "living room",
                                        "device_id": "floor lamp",
                                        "status": "ON",
                                    },
                                }
                            ]
                        },
                    }
                ],
            },
            {
                "eval_id": "kitchen_on_off_sequence",
                "conversation": [
                    {
                        "user_content": {
                            "parts": [{"text": "Switch on the main light in the kitchen."}]
                        },
                        "final_response": {
                            "parts": [
                                {"text": "Successfully set the main light in the kitchen to on."}
                            ]
                        },
                        "intermediate_data": {
                            "tool_uses": [
                                {
                                    "name": "set_device_status",
                                    "args": {
                                        "location": "kitchen",
                                        "device_id": "main light",
                                        "status": "ON",
                                    },
                                }
                            ]
                        },
                    }
                ],
            },
        ],
    }

    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w") as f:
        json.dump(test_cases, f, indent=2)

    print(f"Evaluation test cases created: {output_file}")
    print("\nTest scenarios:")
    for case in test_cases["eval_cases"]:
        user_msg = case["conversation"][0]["user_content"]["parts"][0]["text"]
        print(f"  • {case['eval_id']}: {user_msg}")

    print("\nExpected results:")
    print("  • living_room_light_on: should pass both criteria")
    print("  • kitchen_on_off_sequence: should pass both criteria")


def print_evaluation_analysis():
    """
    Print example analysis of evaluation results.

    This demonstrates how to interpret evaluation metrics and use them
    to improve agent performance.
    """
    print("\nUnderstanding evaluation results:")
    print()
    print("Example analysis:")
    print()
    print("Test case: living_room_light_on")
    print("  response_match_score: 0.45/0.80")
    print("  tool_trajectory_avg_score: 1.0/1.0")
    print()
    print("What this tells us:")
    print("  • Tool usage: agent used the correct tool with correct parameters")
    print("  • Response quality: response text too different from expected")
    print("  • Root cause: agent's communication style, not functionality")
    print()
    print("Actionable insights:")
    print("  1. Technical capability works (tool usage is correct)")
    print("  2. Communication needs improvement (response quality failed)")
    print("  3. Fix: update agent instructions for clearer language or constrained response.")


# ============================================================================
# Main Execution
# ============================================================================


async def test_agent_manually(agent, query: str):
    """
    Test the agent manually with a query to verify it works.

    Args:
        agent: The agent to test
        query: The test query
    """
    runner = InMemoryRunner(agent=agent, app_name="agents")
    print(f"\nTesting query: {query}")
    response = await runner.run_debug(query, verbose=True)

    # Extract text response
    if response and hasattr(response, "content") and response.content:
        for part in response.content.parts:
            if hasattr(part, "text") and part.text:
                print(f"\nAgent Response: {part.text}")
                return

    print("No text response found.")


async def main():
    """
    Main function that demonstrates agent evaluation features.

    This function demonstrates:
    1. Creating a home automation agent
    2. Creating evaluation configuration
    3. Creating test cases
    4. Manual testing of the agent
    5. Understanding evaluation metrics
    """
    # Load and verify API key from environment
    load_env_and_verify_api_key()
    print("ADK components imported successfully.")

    # Configure retry options for all agents
    retry_config = configure_retry_options()

    # ========================================================================
    # Section 2: Create Home Automation Agent
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 2: Create Home Automation Agent")
    print("=" * 80)

    home_agent = create_home_automation_agent(retry_config)
    print("Home automation agent created.")
    print("  Note: Agent has overconfident instructions for evaluation purposes")

    # Test the agent manually
    print("\n--- Manual Test ---")
    await test_agent_manually(home_agent, "Please turn on the floor lamp in the living room")

    # ========================================================================
    # Section 4: Systematic Evaluation
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 4: Systematic Evaluation")
    print("=" * 80)

    # Create evaluation configuration
    print("\n--- Step 1: Create Evaluation Configuration ---")
    create_evaluation_config()

    # Create test cases
    print("\n--- Step 2: Create Test Cases ---")
    create_evaluation_test_cases()

    # Print evaluation command
    print("\n--- Step 3: Run Evaluation (CLI Command) ---")
    print("🚀 To run evaluation, use the following command:")
    print(
        f"   adk eval {AGENT_DIR} {EVALSET_FILE} --config_file_path={TEST_CONFIG_FILE} --print_detailed_results"
    )
    print()
    print("💡 Note: This requires the agent to be in the expected directory structure.")
    print("   For this script, we've created the configuration files for reference.")

    # Print evaluation analysis
    print("\n--- Step 4: Understanding evaluation results ---")
    print_evaluation_analysis()

    print("\n" + "=" * 80)
    print("Agent evaluation examples completed successfully.")
    print("=" * 80)
    print("\nKey takeaways:")
    print("  - Evaluation = systematic testing and measuring agent performance")
    print("  - Response match score: measures text similarity (0.0-1.0)")
    print("  - Tool trajectory score: measures correct tool usage (0.0-1.0)")
    print("  - Interactive evaluation: use ADK web UI for test creation")
    print("  - Automated evaluation: use 'adk eval' CLI for regression testing")
    print("  - Evaluation helps catch regressions before production")
    print("\nEvaluation metrics explained:")
    print("  • response_match_score: how similar the response text is to expected")
    print("  • tool_trajectory_avg_score: whether correct tools were used correctly")
    print("  • both scores range from 0.0 (fail) to 1.0 (perfect match)")
    print("\nNext steps:")
    print("  • Create more test cases covering edge cases")
    print("  • Run evaluations regularly to catch regressions")
    print("  • Use evaluation results to improve agent instructions")


if __name__ == "__main__":
    asyncio.run(main())
