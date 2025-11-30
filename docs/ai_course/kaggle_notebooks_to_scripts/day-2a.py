"""
Day 2-A: Agent Tools

This script demonstrates how to build agents with custom tools:

1. Custom Function Tools: Convert Python functions into agent tools
2. Agent Tools: Use other agents as tools for delegation
3. Built-in Code Executor: Improve reliability by executing Python code

Reference: https://www.kaggle.com/code/kaggle5daysofai/day-2a-agent-tools
"""

import asyncio

from google.adk.agents import LlmAgent
from google.adk.code_executors import BuiltInCodeExecutor
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import AgentTool
from google.genai import types

from adk_fleet_safety_multi_agent_system.helpers.env import load_env_and_verify_api_key


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


def show_python_code_and_result(response):
    """
    Extract and display Python code and results from code execution tool responses.

    This helper function inspects agent responses to find code execution results
    and displays them in a readable format.

    Args:
        response: The response event from the agent (list of events)
    """
    for i in range(len(response)):
        # Check if the response contains a valid function call result from the code executor
        if (
            (response[i].content.parts)
            and (response[i].content.parts[0])
            and (response[i].content.parts[0].function_response)
            and (response[i].content.parts[0].function_response.response)
        ):
            response_code = response[i].content.parts[0].function_response.response
            if "result" in response_code and response_code["result"] != "```":
                if "tool_code" in response_code["result"]:
                    print(
                        "Generated Python Code >> ",
                        response_code["result"].replace("tool_code", ""),
                    )
                else:
                    print("Generated Python Response >> ", response_code["result"])


def get_fee_for_payment_method(method: str) -> dict:
    """
    Looks up the transaction fee percentage for a given payment method.

    This tool simulates looking up a company's internal fee structure based on
    the name of the payment method provided by the user.

    Args:
        method: The name of the payment method. It should be descriptive,
                e.g., "platinum credit card" or "bank transfer".

    Returns:
        Dictionary with status and fee information.
        Success: {"status": "success", "fee_percentage": 0.02}
        Error: {"status": "error", "error_message": "Payment method not found"}
    """
    fee_database = {
        "platinum credit card": 0.02,  # 2%
        "gold debit card": 0.035,  # 3.5%
        "bank transfer": 0.01,  # 1%
    }

    fee = fee_database.get(method.lower())
    if fee is not None:
        return {"status": "success", "fee_percentage": fee}
    else:
        return {
            "status": "error",
            "error_message": f"Payment method '{method}' not found",
        }


def get_exchange_rate(base_currency: str, target_currency: str) -> dict:
    """
    Looks up and returns the exchange rate between two currencies.

    Args:
        base_currency: The ISO 4217 currency code of the currency you
                       are converting from (e.g., "USD").
        target_currency: The ISO 4217 currency code of the currency you
                         are converting to (e.g., "EUR").

    Returns:
        Dictionary with status and rate information.
        Success: {"status": "success", "rate": 0.93}
        Error: {"status": "error", "error_message": "Unsupported currency pair"}
    """
    rate_database = {
        "usd": {
            "eur": 0.93,  # Euro
            "jpy": 157.50,  # Japanese Yen
            "inr": 83.58,  # Indian Rupee
        }
    }

    base = base_currency.lower()
    target = target_currency.lower()

    rate = rate_database.get(base, {}).get(target)
    if rate is not None:
        return {"status": "success", "rate": rate}
    else:
        return {
            "status": "error",
            "error_message": f"Unsupported currency pair: {base_currency}/{target_currency}",
        }


def create_currency_agent(retry_config):
    """
    Create a currency conversion agent with custom function tools.

    This agent demonstrates how to use custom Python functions as tools.
    The agent can look up fees and exchange rates, then calculate conversions.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        LlmAgent: Configured currency conversion agent
    """
    return LlmAgent(
        name="currency_agent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction="""You are a smart currency conversion assistant.

    For currency conversion requests:
    1. Use `get_fee_for_payment_method()` to find transaction fees
    2. Use `get_exchange_rate()` to get currency conversion rates
    3. Check the "status" field in each tool's response for errors
    4. Calculate the final amount after fees based on the output from `get_fee_for_payment_method` and `get_exchange_rate` methods and provide a clear breakdown.
    5. First, state the final converted amount.
        Then, explain how you got that result by showing the intermediate amounts. Your explanation must include: the fee percentage and its
        value in the original currency, the amount remaining after the fee, and the exchange rate used for the final conversion.

    If any tool returns status "error", explain the issue to the user clearly.
    """,
        tools=[get_fee_for_payment_method, get_exchange_rate],
    )


def create_calculation_agent(retry_config):
    """
    Create a specialised calculation agent that generates and executes Python code.

    This agent uses the BuiltInCodeExecutor to run Python code in a sandbox,
    providing reliable mathematical calculations instead of relying on LLM math.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        LlmAgent: Configured calculation agent with code execution capability
    """
    return LlmAgent(
        name="CalculationAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction="""You are a specialised calculator that ONLY responds with Python code. You are forbidden from providing any text, explanations, or conversational responses.

     Your task is to take a request for a calculation and translate it into a single block of Python code that calculates the answer.

     **RULES:**
    1.  Your output MUST be ONLY a Python code block.
    2.  Do NOT write any text before or after the code block.
    3.  The Python code MUST calculate the result.
    4.  The Python code MUST print the final result to stdout.
    5.  You are PROHIBITED from performing the calculation yourself. Your only job is to generate the code that will perform the calculation.

    Failure to follow these rules will result in an error.
       """,
        code_executor=BuiltInCodeExecutor(),
    )


def create_enhanced_currency_agent(retry_config, calculation_agent):
    """
    Create an enhanced currency agent that uses code execution for calculations.

    This agent improves on the basic currency agent by delegating calculations
    to a specialist calculation agent, ensuring accurate mathematical results.

    Args:
        retry_config: HTTP retry configuration for API calls
        calculation_agent: The calculation agent to use as a tool

    Returns:
        LlmAgent: Configured enhanced currency agent with calculation delegation
    """
    return LlmAgent(
        name="enhanced_currency_agent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction="""You are a smart currency conversion assistant. You must strictly follow these steps and use the available tools.

  For any currency conversion request:

   1. Get Transaction Fee: Use the get_fee_for_payment_method() tool to determine the transaction fee.
   2. Get Exchange Rate: Use the get_exchange_rate() tool to get the currency conversion rate.
   3. Error Check: After each tool call, you must check the "status" field in the response. If the status is "error", you must stop and clearly explain the issue to the user.
   4. Calculate Final Amount (CRITICAL): You are strictly prohibited from performing any arithmetic calculations yourself. You must use the calculation_agent tool to generate Python code that calculates the final converted amount. This 
      code will use the fee information from step 1 and the exchange rate from step 2.
   5. Provide Detailed Breakdown: In your summary, you must:
       * State the final converted amount.
       * Explain how the result was calculated, including:
           * The fee percentage and the fee amount in the original currency.
           * The amount remaining after deducting the fee.
           * The exchange rate applied.
    """,
        tools=[
            get_fee_for_payment_method,
            get_exchange_rate,
            AgentTool(agent=calculation_agent),  # Using another agent as a tool!
        ],
    )


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


def print_detailed_logs(response_list):
    """
    Iterates through the response history to print tool calls, code, and outputs.
    """
    print("\n" + "=" * 30 + " EXECUTION LOGS " + "=" * 30)

    # Ensure we are iterating over a list. If it's a single response, wrap it.
    if not isinstance(response_list, list):
        response_list = [response_list]

    for i, step in enumerate(response_list):
        if not hasattr(step, "content") or not step.content:
            continue

        for part in step.content.parts:
            if part.text:
                snippet = part.text.strip().split("\n")[0]
                if snippet:
                    print(f"\n[Step {i}] Agent thought: {snippet}...")

            if part.function_call:
                func_name = part.function_call.name
                args = part.function_call.args
                print(f"\n[Step {i}] Tool call: {func_name}")
                print(f"          Arguments: {args}")

            if part.function_response:
                func_name = part.function_response.name
                resp_content = part.function_response.response
                print(f"\n[Step {i}] Tool output ({func_name}): {resp_content}")

            if part.executable_code:
                lang = part.executable_code.language
                code = part.executable_code.code
                print(f"\n[Step {i}] Generated code ({lang}):")
                print(f"          {code}")

            if part.code_execution_result:
                outcome = part.code_execution_result.outcome
                output = part.code_execution_result.output
                print(f"\n[Step {i}] Code execution result ({outcome}):")
                print(f"          {output.strip()}")

    print("=" * 76 + "\n")


async def main():
    """
    Main function that sets up and runs the agent tool examples.

    This function demonstrates:
    1. Custom Function Tools (currency conversion with fees and rates)
    2. Agent Tools (using calculation agent as a tool)
    3. Code Execution (reliable mathematical calculations)
    """
    # Load and verify API key from environment
    load_env_and_verify_api_key()
    print("ADK components imported successfully.")

    # Configure retry options for all agents
    retry_config = configure_retry_options()

    # ========================================================================
    # Section 2: Custom Function Tools Example
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 2: Custom Function Tools - Currency Converter")
    print("=" * 80)

    # Test the custom functions
    print("\nTesting custom functions:")
    fee_result = get_fee_for_payment_method("platinum credit card")
    print(f"Fee lookup test: {fee_result}")

    rate_result = get_exchange_rate("USD", "EUR")
    print(f"Exchange rate test: {rate_result}")

    # Create the currency agent
    currency_agent = create_currency_agent(retry_config)
    print("\nCurrency agent created with custom function tools.")
    print("Available tools:")
    print("  • get_fee_for_payment_method - Looks up company fee structure")
    print("  • get_exchange_rate - Gets current exchange rates")

    # Create runner and test
    currency_runner = InMemoryRunner(agent=currency_agent, app_name="agents")
    print("\nCurrency runner created.")

    currency_query = (
        "I want to convert 500 US Dollars to Euros using my Platinum Credit Card. "
        "How much will I receive?"
    )
    print(f"\nRunning currency agent with query: {currency_query}\n")

    currency_response = await currency_runner.run_debug(currency_query)

    currency_text = extract_text_from_response(currency_response)
    if currency_text:
        print("\nCurrency Agent - Final Response:")
        print("-" * 80)
        print(currency_text)
        print("-" * 80)
    else:
        print("No text response found in the currency agent output.")

    # ========================================================================
    # Section 3: Code Execution Example
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 3: Code Execution - Enhanced Currency Converter")
    print("=" * 80)

    # Create the calculation agent
    calculation_agent = create_calculation_agent(retry_config)
    print("Calculation agent created with BuiltInCodeExecutor.")

    # Create the enhanced currency agent
    enhanced_currency_agent = create_enhanced_currency_agent(retry_config, calculation_agent)
    print("Enhanced currency agent created.")
    print("New capability: Delegates calculations to specialist agent")
    print("Tool types used:")
    print("  • Function Tools (fees, rates)")
    print("  • Agent Tool (calculation specialist)")

    # Create runner and test
    enhanced_runner = InMemoryRunner(agent=enhanced_currency_agent, app_name="agents")
    print("Enhanced currency runner created.")

    enhanced_query = (
        "Convert 1,250 USD to INR using a Bank Transfer. Show me the precise calculation."
    )
    print(f"\nRunning enhanced currency agent with query: {enhanced_query}\n")

    enhanced_response = await enhanced_runner.run_debug(enhanced_query)

    print_detailed_logs(enhanced_response)

    enhanced_text = extract_text_from_response(enhanced_response)
    if enhanced_text:
        print("\nEnhanced Currency Agent - Final Response:")
        print("-" * 80)
        print(enhanced_text)
        print("-" * 80)
    else:
        print("No text response found in the enhanced currency agent output.")

    # Display the generated Python code
    print("\nGenerated Python Code from Code Executor:")
    print("-" * 80)
    show_python_code_and_result(enhanced_response)
    print("-" * 80)

    print("\n" + "=" * 80)
    print("All tool examples completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
