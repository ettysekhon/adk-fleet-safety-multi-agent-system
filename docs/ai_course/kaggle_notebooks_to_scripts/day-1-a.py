"""
Day 1-A: From Prompt to Action

This script introduces the basics of the Google Agent Development Kit (ADK) by
building a single agent that can use the Google Search tool to answer a user
question.

Reference: https://www.kaggle.com/code/kaggle5daysofai/day-1a-from-prompt-to-action
"""

import asyncio

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.genai import types

from adk_fleet_safety_multi_agent_system.helpers.env import load_env_and_verify_api_key


def configure_retry_options() -> types.HttpRetryOptions:
    """
    Configure retry behaviour for model calls.

    LLM APIs can occasionally return transient errors (for example, rate limits
    or temporary outages). This helper returns a retry configuration that uses
    exponential backoff to make calls more resilient.
    """
    return types.HttpRetryOptions(
        attempts=5,
        exp_base=7,
        initial_delay=1,
        http_status_codes=[429, 500, 503, 504],
    )


def create_search_agent(retry_config: types.HttpRetryOptions) -> Agent:
    """
    Create a single agent that can use Google Search to answer questions.

    Args:
        retry_config: Retry configuration shared across model calls.

    Returns:
        Agent: Configured ADK agent.
    """
    return Agent(
        name="helpful_assistant",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        description="Answers general questions by consulting Google Search when needed.",
        instruction="You are a helpful assistant. Use Google Search for current information or when unsure.",
        tools=[google_search],
    )


async def run_agent_query(runner: InMemoryRunner, question: str):
    """
    Run the agent via the ADK debug runner, which prints intermediary steps.

    Args:
        runner: In-memory runner initialised with the agent.
        question: User question to submit to the agent.

    Returns:
        Event: The final response event produced by the agent.
    """
    return await runner.run_debug(question)


def extract_text_response(response):
    """
    Extract the text portion of the agent response, if present.
    """
    if response and hasattr(response, "content") and response.content:
        for part in response.content.parts:
            if hasattr(part, "text") and part.text:
                return part.text
    return None


async def main():
    """
    Entry point for running the Day 1-A example.
    """
    load_env_and_verify_api_key()
    print("ADK components imported successfully.")

    retry_config = configure_retry_options()
    search_agent = create_search_agent(retry_config)
    runner = InMemoryRunner(agent=search_agent, app_name="agents")
    print("Search agent and runner initialised.")

    question = "What is Agent Development Kit from Google? What languages is the SDK available in?"
    print(f"\nSubmitting question: {question}\n")
    response = await run_agent_query(runner, question)

    text = extract_text_response(response)
    if text:
        print("Final response:\n")
        print(text)
    else:
        print("No text response returned by the agent.")


if __name__ == "__main__":
    asyncio.run(main())
