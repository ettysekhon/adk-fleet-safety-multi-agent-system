"""
Day 1-B: Multi-Agent System Architectures

This script demonstrates four different approaches to building multi-agent systems:

1. Orchestrated Agents: A coordinator agent that decides when to call sub-agents
2. Sequential Agents: A fixed pipeline where agents run in a guaranteed order
3. Parallel Agents: Independent agents that run concurrently for speed
4. Loop Agents: Agents that iterate and refine their output until a condition is met

Reference: https://www.kaggle.com/code/kaggle5daysofai/day-1b-agent-architectures
"""

import asyncio

from adk_fleet_safety_multi_agent_system.helpers.env import load_env_and_verify_api_key
from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import AgentTool, FunctionTool, google_search
from google.genai import types

# ============================================================================
# Configuration
# ============================================================================


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
# Section 2: Orchestrated Multi-Agent System (Research & Summarization)
# ============================================================================


def create_research_agent(retry_config):
    """
    Create a research agent that uses Google Search to find information.

    This agent's job is to search for information on a given topic and present
    the findings with citations.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured research agent
    """
    return Agent(
        name="ResearchAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "You are a specialised research agent. Your only job is to use the "
            "google_search tool to find 2-3 pieces of relevant information on "
            "the given topic and present the findings with citations."
        ),
        tools=[google_search],
        output_key="research_findings",  # Stores result in session state with this key
    )


def create_summariser_agent(retry_config):
    """
    Create a summariser agent that condenses research findings.

    This agent reads research findings and creates a concise summary as a
    bulleted list.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured summariser agent
    """
    return Agent(
        name="SummariserAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "Read the provided research findings: {research_findings}\n"
            "Create a concise summary as a bulleted list with 3-5 key points."
        ),
        output_key="final_summary",
    )


def create_research_coordinator(research_agent, summariser_agent, retry_config):
    """
    Create a coordinator agent that orchestrates the research workflow.

    This agent doesn't do the work itself. Instead, it decides when to call
    the research agent and summariser agent, acting as an orchestrator.

    The sub-agents are wrapped in AgentTool to make them callable as tools
    by the coordinator.

    Args:
        research_agent: The research agent to orchestrate
        summariser_agent: The summariser agent to orchestrate
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured coordinator agent
    """
    return Agent(
        name="ResearchCoordinator",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "You are a research coordinator. Your goal is to answer the user's "
            "query by orchestrating a workflow.\n"
            "1. First, you MUST call the `ResearchAgent` tool to find relevant "
            "information on the topic provided by the user.\n"
            "2. Next, after receiving the research findings, you MUST call the "
            "`SummariserAgent` tool to create a concise summary.\n"
            "3. Finally, present the final summary clearly to the user as your response."
        ),
        tools=[AgentTool(research_agent), AgentTool(summariser_agent)],
    )


# ============================================================================
# Section 3: Sequential Multi-Agent System
# ============================================================================


def create_outline_agent(retry_config):
    """
    Create an agent that generates blog post outlines.

    This is the first step in a sequential pipeline. It creates a structured
    outline for a blog post on a given topic.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured outline agent
    """
    return Agent(
        name="OutlineAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "Create a blog outline for the given topic with:\n"
            "1. A catchy headline\n"
            "2. An introduction hook\n"
            "3. 3-5 main sections with 2-3 bullet points for each\n"
            "4. A concluding thought"
        ),
        output_key="blog_outline",  # Output stored in session state
    )


def create_writer_agent(retry_config):
    """
    Create an agent that writes blog posts based on an outline.

    This is the second step in the sequential pipeline. It receives the outline
    from the previous agent (via the {blog_outline} placeholder) and writes
    a full blog post.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured writer agent
    """
    return Agent(
        name="WriterAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "Following this outline strictly: {blog_outline}\n"
            "Write a brief, 200 to 300-word blog post with an engaging and "
            "informative tone."
        ),
        output_key="blog_draft",
    )


def create_editor_agent(retry_config):
    """
    Create an agent that edits and polishes blog drafts.

    This is the final step in the sequential pipeline. It receives the draft
    from the writer agent and improves it.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured editor agent
    """
    return Agent(
        name="EditorAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "Edit this draft: {blog_draft}\n"
            "Your task is to polish the text by fixing any grammatical errors, "
            "improving the flow and sentence structure, and enhancing overall clarity."
        ),
        output_key="final_blog",
    )


def create_blog_pipeline(outline_agent, writer_agent, editor_agent):
    """
    Create a sequential agent pipeline for blog post creation.

    SequentialAgent ensures agents run in a guaranteed, specific order. This is
    different from the orchestrated approach where the coordinator decides when
    to call agents. With SequentialAgent, the order is fixed and predictable.

    The output of one agent automatically becomes the input for the next agent
    via the {output_key} placeholders in their instructions.

    Args:
        outline_agent: Agent that creates the outline
        writer_agent: Agent that writes the blog post
        editor_agent: Agent that edits the blog post

    Returns:
        SequentialAgent: Configured sequential pipeline
    """
    return SequentialAgent(
        name="BlogPipeline",
        sub_agents=[outline_agent, writer_agent, editor_agent],
    )


# ============================================================================
# Section 4: Parallel Multi-Agent System
# ============================================================================


def create_tech_researcher(retry_config):
    """
    Create a researcher agent focused on AI/ML trends.

    This agent researches technology trends and provides concise reports.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured tech researcher agent
    """
    return Agent(
        name="TechResearcher",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "Research the latest AI/ML trends. Include 3 key developments, "
            "the main companies involved, and the potential impact. "
            "Keep the report very concise (100 words)."
        ),
        tools=[google_search],
        output_key="tech_research",
    )


def create_health_researcher(retry_config):
    """
    Create a researcher agent focused on medical breakthroughs.

    This agent researches health and medical news and provides concise reports.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured health researcher agent
    """
    return Agent(
        name="HealthResearcher",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "Research recent medical breakthroughs. Include 3 significant advances, "
            "their practical applications, and estimated timelines. "
            "Keep the report concise (100 words)."
        ),
        tools=[google_search],
        output_key="health_research",
    )


def create_finance_researcher(retry_config):
    """
    Create a researcher agent focused on fintech trends.

    This agent researches finance and fintech news and provides concise reports.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured finance researcher agent
    """
    return Agent(
        name="FinanceResearcher",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "Research current fintech trends. Include 3 key trends, "
            "their market implications, and the future outlook. "
            "Keep the report concise (100 words)."
        ),
        tools=[google_search],
        output_key="finance_research",
    )


def create_aggregator_agent(retry_config):
    """
    Create an aggregator agent that combines research findings.

    This agent runs after parallel research agents complete. It synthesises
    the outputs from all three researchers into a single executive summary.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured aggregator agent
    """
    return Agent(
        name="AggregatorAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "Combine these three research findings into a single executive summary:\n\n"
            "**Technology Trends:**\n{tech_research}\n\n"
            "**Health Breakthroughs:**\n{health_research}\n\n"
            "**Finance Innovations:**\n{finance_research}\n\n"
            "Your summary should highlight common themes, surprising connections, "
            "and the most important key takeaways from all three reports. "
            "The final summary should be around 200 words."
        ),
        output_key="executive_summary",
    )


def create_parallel_research_system(
    tech_researcher, health_researcher, finance_researcher, aggregator_agent
):
    """
    Create a parallel research system with an aggregator.

    This system demonstrates ParallelAgent by running three independent
    research tasks concurrently, then aggregating the results.

    The ParallelAgent runs all its sub-agents simultaneously, dramatically
    speeding up the workflow when tasks are independent.

    Args:
        tech_researcher: Agent that researches technology trends
        health_researcher: Agent that researches health breakthroughs
        finance_researcher: Agent that researches finance trends
        aggregator_agent: Agent that combines all research findings

    Returns:
        SequentialAgent: Configured research system with parallel execution
    """
    # ParallelAgent runs all sub-agents simultaneously
    parallel_research_team = ParallelAgent(
        name="ParallelResearchTeam",
        sub_agents=[tech_researcher, health_researcher, finance_researcher],
    )

    # SequentialAgent ensures parallel research completes before aggregation
    return SequentialAgent(
        name="ResearchSystem",
        sub_agents=[parallel_research_team, aggregator_agent],
    )


# ============================================================================
# Section 5: Loop Multi-Agent System
# ============================================================================


def create_initial_writer_agent(retry_config):
    """
    Create an agent that writes the first draft of a story.

    This agent runs once at the beginning to create the initial draft.
    The draft is then refined through the loop workflow.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured initial writer agent
    """
    return Agent(
        name="InitialWriterAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "Based on the user's prompt, write the first draft of a short story "
            "(around 100-150 words). Output only the story text, with no introduction "
            "or explanation."
        ),
        output_key="current_story",
    )


def create_critic_agent(retry_config):
    """
    Create an agent that critiques stories and provides feedback.

    This agent reviews stories and either approves them (by returning "APPROVED")
    or provides specific suggestions for improvement.

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured critic agent
    """
    return Agent(
        name="CriticAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "You are a constructive story critic. Review the story provided below.\n"
            "Story: {current_story}\n\n"
            "Evaluate the story's plot, characters, and pacing.\n"
            "- If the story is well-written and complete, you MUST respond with "
            'the exact phrase: "APPROVED"\n'
            "- Otherwise, provide 2-3 specific, actionable suggestions for improvement."
        ),
        output_key="critique",
    )


def exit_loop():
    """
    Exit function for the loop agent.

    This function is called by the refiner agent when the story is approved,
    signalling that the refinement loop should terminate.

    Returns:
        dict: Status dictionary indicating approval
    """
    return {"status": "approved", "message": "Story approved. Exiting refinement loop."}


def create_refiner_agent(retry_config):
    """
    Create an agent that refines stories based on critique.

    This agent is the "brain" of the loop. It reads the critique and either:
    1. Calls the exit_loop function if the story is approved
    2. Rewrites the story to incorporate feedback

    Args:
        retry_config: HTTP retry configuration for API calls

    Returns:
        Agent: Configured refiner agent
    """
    return Agent(
        name="RefinerAgent",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=(
            "You are a story refiner. You have a story draft and critique.\n\n"
            "Story Draft: {current_story}\n"
            "Critique: {critique}\n\n"
            "Your task is to analyze the critique.\n"
            '- IF the critique is EXACTLY "APPROVED", you MUST call the `exit_loop` '
            "function and nothing else.\n"
            "- OTHERWISE, rewrite the story draft to fully incorporate the feedback "
            "from the critique."
        ),
        output_key="current_story",
        tools=[FunctionTool(exit_loop)],
    )


def create_story_refinement_pipeline(initial_writer_agent, retry_config):
    """
    Create a story refinement pipeline using a loop agent.

    This system demonstrates LoopAgent by iteratively refining a story through
    cycles of critique and revision until it's approved or max iterations reached.

    The workflow:
    1. Initial writer creates the first draft
    2. Loop runs: Critic reviews → Refiner improves (or exits if approved)
    3. Loop continues until approval or max_iterations

    Args:
        initial_writer_agent: Agent that creates the initial story draft
        retry_config: HTTP retry configuration for API calls

    Returns:
        SequentialAgent: Configured story refinement pipeline
    """
    critic_agent = create_critic_agent(retry_config)
    refiner_agent = create_refiner_agent(retry_config)

    # LoopAgent runs critic and refiner repeatedly until exit condition
    story_refinement_loop = LoopAgent(
        name="StoryRefinementLoop",
        sub_agents=[critic_agent, refiner_agent],
        max_iterations=2,  # Prevents infinite loops
    )

    # SequentialAgent: Initial Write → Refinement Loop
    return SequentialAgent(
        name="StoryPipeline",
        sub_agents=[initial_writer_agent, story_refinement_loop],
    )


# ============================================================================
# Main Execution
# ============================================================================


async def run_sequential_pipeline(runner, query):
    """
    Run the sequential blog post pipeline with a given query.

    Args:
        runner: InMemoryRunner configured with the sequential agent
        query: The user's query/prompt

    Returns:
        Event: The response event from the agent
    """
    response = await runner.run_debug(query)
    return response


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
    Main function that sets up and runs the multi-agent systems.

    This function demonstrates all four workflow patterns:
    1. Orchestrated (commented out by default)
    2. Sequential (blog post pipeline)
    3. Parallel (multi-topic research)
    4. Loop (story refinement)

    Uncomment the section you want to run, or modify to run multiple examples.
    """
    # Load and verify API key from environment
    load_env_and_verify_api_key()
    print("ADK components imported successfully.")

    # Configure retry options for all agents
    retry_config = configure_retry_options()

    # ========================================================================
    # Section 3: Sequential Workflow Example
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 3: Sequential Workflow - Blog Post Creation")
    print("=" * 80)

    outline_agent = create_outline_agent(retry_config)
    writer_agent = create_writer_agent(retry_config)
    editor_agent = create_editor_agent(retry_config)

    print("Outline agent created.")
    print("Writer agent created.")
    print("Editor agent created.")

    blog_pipeline = create_blog_pipeline(outline_agent, writer_agent, editor_agent)
    print("Sequential blog pipeline created.")

    sequential_runner = InMemoryRunner(agent=blog_pipeline, app_name="agents")
    print("Sequential runner created.")

    blog_query = (
        "Write a blog post about the benefits of multi-agent systems for software developers"
    )
    print(f"\nRunning sequential pipeline with query: {blog_query}\n")

    blog_response = await sequential_runner.run_debug(blog_query)

    blog_text = extract_text_from_response(blog_response)
    if blog_text:
        print("\nSequential Pipeline - Final Response:")
        print("-" * 80)
        print(blog_text)
        print("-" * 80)
    else:
        print("No text response found in the sequential pipeline output.")

    # ========================================================================
    # Section 4: Parallel Workflow Example
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 4: Parallel Workflow - Multi-Topic Research")
    print("=" * 80)

    tech_researcher = create_tech_researcher(retry_config)
    health_researcher = create_health_researcher(retry_config)
    finance_researcher = create_finance_researcher(retry_config)
    aggregator_agent = create_aggregator_agent(retry_config)

    print("Tech researcher created.")
    print("Health researcher created.")
    print("Finance researcher created.")
    print("Aggregator agent created.")

    research_system = create_parallel_research_system(
        tech_researcher, health_researcher, finance_researcher, aggregator_agent
    )
    print("Parallel research system created.")

    parallel_runner = InMemoryRunner(agent=research_system, app_name="agents")
    print("Parallel runner created.")

    research_query = "Run the daily executive briefing on Tech, Health, and Finance"
    print(f"\nRunning parallel research system with query: {research_query}\n")

    research_response = await parallel_runner.run_debug(research_query)

    research_text = extract_text_from_response(research_response)
    if research_text:
        print("\nParallel Research System - Final Response:")
        print("-" * 80)
        print(research_text)
        print("-" * 80)
    else:
        print("No text response found in the parallel research system output.")

    # ========================================================================
    # Section 5: Loop Workflow Example
    # ========================================================================
    print("\n" + "=" * 80)
    print("Section 5: Loop Workflow - Story Refinement")
    print("=" * 80)

    initial_writer = create_initial_writer_agent(retry_config)
    print("Initial writer agent created.")

    story_pipeline = create_story_refinement_pipeline(initial_writer, retry_config)
    print("Story refinement pipeline created.")

    loop_runner = InMemoryRunner(agent=story_pipeline, app_name="agents")
    print("Loop runner created.")

    story_query = (
        "Write a short story about a lighthouse keeper who discovers a mysterious, glowing map"
    )
    print(f"\nRunning story refinement pipeline with query: {story_query}\n")

    story_response = await loop_runner.run_debug(story_query)

    story_text = extract_text_from_response(story_response)
    if story_text:
        print("\nStory Refinement Pipeline - Final Response:")
        print("-" * 80)
        print(story_text)
        print("-" * 80)
    else:
        print("No text response found in the story refinement pipeline output.")

    print("\n" + "=" * 80)
    print("All workflow examples completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
