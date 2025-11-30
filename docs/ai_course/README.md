# 5-Day AI Agents Intensive Course with Google

A 5 day course using the Agent Development Kit (ADK) framework to build AI agents with Google's Gemini models.

## Background

This project is designed to gain a better understanding of Agentic AI using Google's Agent Development Kit (ADK). Traditional large language models (LLMs) respond to prompts with text, but they cannot take actions or use external tools. Agentic AI extends this capability by enabling AI systems to reason, take actions, observe results, and iteratively improve their responses.

ADK provides a framework for building, deploying, and orchestrating AI agents and multi-agent systems. It applies software development principles to AI agent creation, making it feel more like traditional software development with robust debugging, versioning, and deployment capabilities.

The project follows the Kaggle 5-day Agents course, implementing examples from all five days that demonstrate:

- **Day 1**: Building single agents and multi-agent systems with different workflow patterns
- **Day 2**: Creating custom tools, using Model Context Protocol (MCP), and handling long-running operations
- **Day 3**: Managing agent sessions, context compaction, and long-term memory
- **Day 4**: Observability, debugging, and systematic agent evaluation
- **Day 5**: Agent-to-agent (A2A) communication and deployment

## Concepts

### What is an AI Agent?

A traditional LLM follows a simple pattern: **Prompt → LLM → Text Response**.

An AI agent extends this by adding the ability to take actions: **Prompt → Agent → Thought → Action → Observation → Final Answer**.

For example, if you ask an agent "What's the weather in London?", it can:

1. Think about what information it needs
2. Take action by calling a weather API or searching the web
3. Observe the results
4. Provide a final answer based on that information

### Multi-Agent Systems

Instead of one agent trying to do everything, you can build a team of specialised agents that collaborate. Each agent has one clear job (e.g., one agent only does research, another only writes). This makes them easier to build, test, and maintain.

The project demonstrates three workflow patterns:

1. **Orchestrated Agents**: A coordinator agent decides when to call sub-agents based on the task
2. **Sequential Agents**: A fixed pipeline where agents run in a guaranteed order (like an assembly line)
3. **Parallel Agents**: Independent agents that run concurrently to speed up workflows

## Setup

### Prerequisites

- Python 3.12 or higher
- A Google API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

### Installation

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Create a `.env` file in the project root with your Google API key:

   ```bash
   GOOGLE_API_KEY=your_api_key_here
   ```

   The `helpers.py` module will automatically load this key when you run the scripts.

## Project Structure

- `kaggle_notebooks/` - Jupyter notebooks corresponding to each script
- `kaggle_notebooks_to_scripts/` - All example scripts organised by day:
  - `day-1-a.py` - Single agent with Google Search tool
  - `day-1-b.py` - Multi-agent systems (orchestrated, sequential, parallel, loop)
  - `day-2a.py` - Custom function tools and code execution
  - `day-2b.py` - Model Context Protocol (MCP) and long-running operations
  - `day-3a.py` - Session management and context compaction
  - `day-3b.py` - Long-term memory management
  - `day-4a.py` - Observability and debugging
  - `day-4b.py` - Agent evaluation
  - `day-5a.py` - Agent-to-agent (A2A) communication

## Running the Agents

### Command Line Interface

### Direct Script Execution

Run the example scripts directly:

#### Day 1-A: Single Agent with Google Search

```bash
uv run python docs/ai_course/kaggle_notebooks_to_scripts/day-1-a.py
```

Demonstrates a simple agent that can answer questions by using Google Search when it needs current information.

#### Day 1-B: Multi-Agent Systems

```bash
uv run python docs/ai_course/kaggle_notebooks_to_scripts/day-1-b.py
```

Demonstrates four multi-agent workflow patterns:

- **Orchestrated**: Coordinator agent decides when to call sub-agents
- **Sequential**: Fixed pipeline (outline → write → edit) for blog post creation
- **Parallel**: Independent agents run concurrently for multi-topic research
- **Loop**: Iterative refinement until a condition is met (story refinement)

#### Day 2-A: Agent Tools

```bash
uv run python docs/ai_course/kaggle_notebooks_to_scripts/day-2a.py
```

Demonstrates:

- Custom function tools for currency conversion
- Agent tools (using agents as tools for delegation)
- Built-in code executor for reliable calculations

#### Day 2-B: Advanced Tool Patterns

```bash
uv run python docs/ai_course/kaggle_notebooks_to_scripts/day-2b.py
```

Demonstrates:

- Model Context Protocol (MCP) integration with external servers
- Long-running operations (tools that pause for human approval)
- Resumable workflows with state management

#### Day 3-A: Agent Sessions

```bash
uv run python docs/ai_course/kaggle_notebooks_to_scripts/day-3a.py
```

Demonstrates:

- Session management for stateful conversations
- Persistent sessions with DatabaseSessionService
- Context compaction to manage conversation history
- Session state for structured data storage

#### Day 3-B: Agent Memory

```bash
uv run python docs/ai_course/kaggle_notebooks_to_scripts/day-3b.py
```

Demonstrates:

- Long-term memory initialisation and management
- Manual and automatic memory ingestion from sessions
- Memory retrieval using `load_memory` and `preload_memory` tools
- Automatic memory storage with callbacks

#### Day 4-A: Agent Observability

```bash
uv run python docs/ai_course/kaggle_notebooks_to_scripts/day-4a.py
```

Demonstrates:

- Logging configuration for debugging
- Debugging techniques with ADK Web UI
- Production logging with LoggingPlugin
- Custom plugins with callbacks

#### Day 4-B: Agent Evaluation

```bash
uv run python docs/ai_course/kaggle_notebooks_to_scripts/day-4b.py
```

Demonstrates:

- Creating evaluation test cases and configurations
- Understanding evaluation metrics (response_match_score, tool_trajectory_avg_score)
- Running evaluations via CLI
- Analysing evaluation results

#### Day 5-A: Agent-to-Agent Communication

```bash
uv run python docs/ai_course/kaggle_notebooks_to_scripts/day-5a.py
```

Demonstrates:

- Exposing agents via A2A protocol with agent cards
- Consuming remote agents using RemoteA2aAgent
- Cross-organisation and cross-language agent communication

Note: Requires a separate server to be running for full testing.

## Learning Resources

This project is based on the Kaggle 5-day Agents course. Each day has corresponding scripts in `docs/ai_course/kaggle_notebooks_to_scripts/` and notebooks in `docs/ai_course/kaggle_notebooks/`:

### Day 1: Foundations

- **Day 1-A: From Prompt to Action** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-1a-from-prompt-to-action)

  - Introduces the concept of AI agents
  - Shows how to build a single agent with tools
  - Demonstrates the difference between LLMs and agents

- **Day 1-B: Agent Architectures** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-1b-agent-architectures)

  - Explains multi-agent systems and when to use them
  - Demonstrates orchestrated agents (coordinator pattern)
  - Shows sequential workflows for guaranteed execution order
  - Introduces parallel and loop patterns

### Day 2: Tools and Best Practices

- **Day 2-A: Agent Tools** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-2a-agent-tools)

  - Custom function tools
  - Agent tools (agents as tools)
  - Built-in code executor for reliable calculations

- **Day 2-B: Agent Tools Best Practices** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-2b-agent-tools-best-practices)

  - Model Context Protocol (MCP) integration
  - Long-running operations with human-in-the-loop
  - Resumable workflows

### Day 3: Sessions and Memory

- **Day 3-A: Agent Sessions** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-3a-agent-sessions)

  - Session management and state
  - Persistent sessions with databases
  - Context compaction for long conversations
  - Session state for structured data

- **Day 3-B: Agent Memory** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-3b-agent-memory)

  - Long-term memory initialisation
  - Memory ingestion and retrieval
  - Automatic memory management with callbacks

### Day 4: Observability and Evaluation

- **Day 4-A: Agent Observability** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-4a-agent-observability)

  - Logging and debugging
  - Production observability with plugins
  - Custom plugins and callbacks

- **Day 4-B: Agent Evaluation** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-4b-agent-evaluation)

  - Creating evaluation test cases
  - Evaluation metrics and thresholds
  - Running and analysing evaluations

### Day 5: Communication and Deployment

- **Day 5-A: Agent-to-Agent Communication** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-5a-agent2agent-communication)

  - A2A protocol for agent communication
  - Exposing agents with agent cards
  - Consuming remote agents
  - Cross-organisation collaboration

- **Day 5-B: Agent Deployment** - [Kaggle Notebook](https://www.kaggle.com/code/kaggle5daysofai/day-5b-agent-deployment)

  - Deploying agents to Vertex AI Agent Engine
  - Production deployment considerations

### Additional Documentation

- [ADK Documentation](https://github.com/google/adk)
- [ADK Quickstart for Python](https://github.com/google/adk/blob/main/docs/quickstart.md)
- [ADK Agents Overview](https://github.com/google/adk/blob/main/docs/agents.md)
- [ADK Tools Overview](https://github.com/google/adk/blob/main/docs/tools.md)

## Code Examples Explained

### Day 1-A: Single Agent

The `day-1-a.py` script creates a simple agent that can answer questions by using Google Search when needed. The agent:

1. Receives a user query
2. Decides if it needs to search for current information
3. Uses the Google Search tool if necessary
4. Provides a final answer based on the search results

This demonstrates the core concept: agents can take actions, not just respond with text.

### Day 1-B: Multi-Agent System Architectures

The `day-1-b.py` script demonstrates four workflow patterns:

**Orchestrated Agents (Research System):**

- A coordinator agent decides when to call specialised sub-agents
- Research Agent: Searches for information using Google Search
- Summariser Agent: Creates concise summaries from research findings
- The coordinator orchestrates the workflow by calling these agents as tools

**Sequential Agents (Blog Pipeline):**

- A fixed pipeline where agents run in guaranteed order
- Outline Agent: Creates a blog post outline
- Writer Agent: Writes the blog post based on the outline
- Editor Agent: Polishes and improves the draft
- Each agent's output automatically becomes the next agent's input

**Parallel Agents (Multi-Topic Research):**

- Independent agents run concurrently for speed
- Tech, Health, and Finance researchers work simultaneously
- Aggregator agent combines their findings into an executive summary

**Loop Agents (Story Refinement):**

- Iterative refinement until a condition is met
- Initial writer creates a draft
- Critic provides feedback
- Refiner improves the story until approved

### Code Example: Day 2-A (Agent Tools)

The `day-2a.py` script demonstrates:

- **Custom Function Tools**: Converting Python functions into agent tools (e.g., currency conversion with fee lookup and exchange rates)
- **Agent Tools**: Using other agents as tools for delegation (e.g., a calculation specialist agent)
- **Built-in Code Executor**: Improving reliability by executing Python code in a sandbox rather than relying on LLM arithmetic

### Code Example: Day 2-B (Advanced Tool Patterns)

The `day-2b.py` script demonstrates:

- **Model Context Protocol (MCP)**: Connecting to external MCP servers (e.g., image generation server)
- **Long-Running Operations**: Tools that can pause agent execution to request human approval
- **Resumable Workflows**: Handling pause and resume with state management using `ResumabilityConfig`

### Code Example: Day 3-A (Agent Sessions)

The `day-3a.py` script demonstrates:

- **Session Management**: Understanding sessions, events, and state in conversations
- **Persistent Sessions**: Using `DatabaseSessionService` to store sessions in SQLite
- **Context Compaction**: Automatically summarising conversation history to manage context length
- **Session State**: Managing structured data (key-value pairs) across conversation turns

### Code Example: Day 3-B (Agent Memory)

The `day-3b.py` script demonstrates:

- **Memory Initialisation**: Setting up `InMemoryMemoryService` for long-term knowledge storage
- **Manual Memory Storage**: Transferring session data to memory using `add_session_to_memory()`
- **Memory Retrieval**: Using `load_memory` (reactive) and `preload_memory` (proactive) tools
- **Automatic Memory Storage**: Using callbacks to automatically save sessions to memory after each turn

### Code Example: Day 4-A (Agent Observability)

The `day-4a.py` script demonstrates:

- **Logging Configuration**: Setting up DEBUG-level file logging for debugging
- **Debugging Techniques**: Using ADK Web UI traces and events to find issues
- **Production Logging**: Using `LoggingPlugin` for comprehensive production observability
- **Custom Plugins**: Building custom plugins with callbacks for specific needs

### Code Example: Day 4-B (Agent Evaluation)

The `day-4b.py` script demonstrates:

- **Creating Evaluation Test Cases**: Defining test scenarios with expected responses and tool usage
- **Evaluation Configuration**: Setting pass/fail thresholds for metrics
- **Evaluation Metrics**: Understanding `response_match_score` (text similarity) and `tool_trajectory_avg_score` (tool usage correctness)
- **Running Evaluations**: Using `adk eval` CLI command for automated testing

### Code Example: Day 5-A (Agent-to-Agent Communication)

The `day-5a.py` script demonstrates:

- **Exposing Agents via A2A**: Using `to_a2a()` to make agents accessible with agent cards
- **Consuming Remote Agents**: Using `RemoteA2aAgent` to integrate external agents as sub-agents
- **Cross-Organisation Communication**: Enabling agents from different teams/companies to collaborate
- **A2A Protocol**: Standardised protocol for agent-to-agent communication across networks and languages

## Next Steps

To continue learning:

1. **Experiment with agent instructions**: Modify agent instructions to change their behaviour and see how it affects responses
2. **Add custom tools**: Create your own function tools for specific use cases
3. **Build multi-agent systems**: Combine different workflow patterns (orchestrated, sequential, parallel, loop) for complex tasks
4. **Explore observability**: Use the ADK web interface to see detailed traces of agent reasoning and tool usage
5. **Implement memory**: Add long-term memory to agents for personalised experiences
6. **Evaluate your agents**: Create test cases and run evaluations to measure agent performance
7. **Deploy agents**: Learn about deploying agents to production with Vertex AI Agent Engine
8. **Build for the Capstone**: Apply all concepts to create a submission for the Kaggle Capstone Project

## Capstone Project

This project is part of the Kaggle 5-Day AI Agents Intensive Course (10-14 November 2025). Participants can apply what they've learned by building AI agents and submitting them to the [Capstone Competition](https://www.kaggle.com/competitions/agents-intensive-capstone-project).

### Project Tracks

Submissions can be made to one of four tracks:

- **Concierge Agents**: Agents useful for individuals in their daily lives (meal planning, shopping, travel planning, etc.)
- **Agents for Good**: Agents that tackle problems in education, healthcare, or sustainability
- **Enterprise Agents**: Agents designed to improve business workflows, analyse data, or automate customer support
- **Freestyle**: An open category for innovative agents that don't fit neatly into the other tracks

### Submission Requirements

Submissions must demonstrate at least three of the following key concepts from the course:

- Multi-agent systems (orchestrated, parallel, sequential, or loop agents)
- Tools (MCP, custom tools, built-in tools, OpenAPI tools)
- Long-running operations (pause/resume agents)
- Sessions and memory management
- Observability (logging, tracing, metrics)
- Agent evaluation
- A2A Protocol
- Agent deployment

Submissions are evaluated on:

- **The Pitch** (30 points): Problem statement, solution architecture, and value proposition
- **The Implementation** (70 points): Technical implementation quality, code architecture, and meaningful use of agents
- **Bonus Points** (20 points): Effective use of Gemini, agent deployment, and video submission

### Timeline

- Submission deadline: 1 December 2025, 11:59 AM Pacific Time
- Winners announced: Before the end of December 2025

All participants receive a Kaggle badge and certificate of participation. Top projects in each track receive Kaggle swag and social media recognition.

For full details, submission guidelines, and evaluation criteria, visit the [competition page](https://www.kaggle.com/competitions/agents-intensive-capstone-project).
