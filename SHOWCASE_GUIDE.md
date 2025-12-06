# Fleet Safety Platform - Showcase Guide

A practical guide for running the Fleet Safety Platform and demonstrating its **Multi-Agent Architecture**, **Observability**, and **Memory** features.

## Getting Started

### Fire Up the ADK Web UI

The Web UI gives you visual traces, tool call logs, and conversation history—essential for understanding what's happening under the hood.

```bash
make playground
```

Or if you prefer doing things manually:

```bash
uv run adk web app/agents
```

Then open `http://localhost:8000` in your browser and select `fleet_safety` from the sidebar.

## How the Multi-Agent System Works

We're using ADK's `AgentTool` pattern here. This is important—it means sub-agents appear as **nested invocations** in the trace, so you can actually see the orchestrator delegating work.

```text
fleet_safety_orchestrator (root agent)
├── route_planner_agent    → Generates routes via Google Maps MCP
├── safety_scorer_agent    → Evaluates route safety (0-100 score)
├── risk_monitor_agent     → Monitors real-time telemetry
├── analytics_agent        → Historical analysis & predictions
└── rerouter_agent         → Dynamic re-routing for active trips
```

**What you'll see in the trace:**

1. The orchestrator's LLM deciding which agent to call
2. A nested `invocation` block when a sub-agent runs
3. The sub-agent's own LLM making its decisions
4. Tool calls within each sub-agent

This is different from just calling Python methods directly—with `AgentTool`, each sub-agent genuinely runs as its own agent with its own reasoning.

## Demo Scenarios

### Scenario 1: Route Planning with Safety Scoring

**What we're demonstrating:** Multiple agents working together—specifically `route_planner_agent` and `safety_scorer_agent`.

**Use this prompt:**

> "Plan a safe route for vehicle v001 (Heavy Truck) driven by driver d001 from The Strand London to Bushey Heath. Evaluate the safety of each route option considering the driver's experience and current conditions, then recommend the safest option with risk mitigation advice."

**What to look for in the Trace tab:**

- The orchestrator calling `get_fleet_status`, `get_vehicle_info`, `get_driver_info` first
- A nested `route_planner_agent` invocation—expand this to see MCP calls like `get_directions`
- A nested `safety_scorer_agent` invocation—this calls `score_route` and analyses road characteristics
- The final response aggregating everything with safety scores and recommendations

**Why this matters:** The key thing here is that the orchestrator isn't doing all the work itself. It's genuinely delegating to specialist agents, and you can see each one reasoning independently.

### Scenario 2: Fleet-Wide Risk Assessment

**What we're demonstrating:** The `analytics_agent` and `risk_monitor_agent` working together for a comprehensive view.

**Use this prompt:**

> "Give me a comprehensive safety analysis of vehicle v001. Include its current risk status, historical safety trends over the past 30 days, and any incident patterns. What proactive measures should we take?"

**What to look for:**

- `risk_monitor_agent` being invoked—this handles current/real-time risk
- `analytics_agent` being invoked—this pulls historical data and trends
- The orchestrator combining insights from both

### Scenario 3: Emergency Rerouting

**What we're demonstrating:** The `rerouter_agent` handling a dynamic situation.

**Use this prompt:**

> "Vehicle v001 is currently on an active trip from London to Birmingham but there's been a major accident reported on the M1. Evaluate whether we should reroute the vehicle and if so, calculate an alternative route with safety assessment."

**What to look for:**

- `rerouter_agent` evaluating the situation
- Potentially chaining to `route_planner_agent` for alternatives
- Potentially chaining to `safety_scorer_agent` to compare options

### Scenario 4: Executive Dashboard

**What we're demonstrating:** The orchestrator aggregating insights from multiple sources.

**Use this prompt:**

> "Generate an executive dashboard for today's fleet operations. Include fleet status, active safety alerts, top risk factors across all vehicles, and recommendations for improvement."

**What to look for:**

- `get_fleet_status` tool call (this is a direct tool on the orchestrator)
- `analytics_agent` invocation for KPIs and trends
- A nicely formatted dashboard output

### Scenario 5: EV-Specific Route Planning

**What we're demonstrating:** Vehicle-specific handling—EVs have different constraints (range, charging).

**Use this prompt:**

> "Plan a route for vehicle v002 (Electric Van, 85% charge) driven by driver d002 from Central London to Cambridge. Consider charging requirements and range anxiety factors in the safety assessment."

**What to look for:**

- Different handling compared to diesel vehicles
- Range and charging considerations in the route planning
- EV-specific risk factors in safety scoring (e.g., cold weather battery drain)

### Scenario 6: Session Memory

**What we're demonstrating:** The agent remembering context within a session.

**First, ask:**

> "Plan a safe route for vehicle v001 from The Strand London to Bushey Heath."

**Then follow up with:**

> "Which of those routes had the lowest risk score and why?"

**What to look for:**

- The second query doesn't re-invoke route planning
- The agent uses session history to answer
- No duplicate MCP calls—it remembers what it already fetched

### Scenario 7: Long-Term Memory

**What we're demonstrating:** The `load_memory` tool for recalling past context.

**Use this prompt:**

> "What were the safety recommendations we discussed for vehicle v001's previous trips?"

**What to look for:**

- A `load_memory` tool call in the trace
- The agent attempting to retrieve historical context

## Reading the Trace

When you expand an invocation in the Trace tab, you'll see a hierarchy like this:

```text
invocation (total time)
└── invoke_agent fleet_safety_orchestrator
    ├── call_llm (orchestrator thinking)
    ├── execute_tool get_fleet_status
    ├── execute_tool get_vehicle_info
    ├── call_llm (deciding to call sub-agent)
    └── execute_tool route_planner_agent
        └── invocation (sub-agent time)     ← THIS IS THE KEY BIT
            └── invoke_agent route_planner_agent
                ├── call_llm (route planner thinking)
                └── execute_tool generate_route_options
```

**Icons to watch for:**

- ⚡ (bolt) = Tool call started
- ✓ (check) = Tool call completed
- Nested `invocation` blocks = Sub-agent calls via `AgentTool`

The nested invocation is what tells you a proper sub-agent delegation happened, not just a Python function call.

## Running Evaluations

To run the evaluation suite:

```bash
make eval
```

Or manually:

```bash
uv run adk eval \
    app/agents/fleet_safety \
    app/agents/fleet_safety/evaluation/integration.evalset.json \
    --config_file_path=app/agents/fleet_safety/evaluation/eval_config.json \
    --print_detailed_results
```

This loads the orchestrator, runs test scenarios, and scores based on tool usage accuracy and response quality.

## Key Files

If you want to understand how this all fits together:

- **`app/agents/fleet_safety/agent.py`** — Entry point. Creates all the agents and registers them with the orchestrator using `AgentTool`.
- **`app/agents/fleet_safety/orchestrator.py`** — The central coordinator. Look at `register_agents()` to see how `AgentTool` wrappers are added.
- **`app/agents/fleet_safety/*_agent.py`** — The specialist agents. Each has its own `instruction` and `tools`.

## Testing Deployed Agents

After deploying with `make deploy`:

```bash
# Single query
uv run python scripts/query_deployed_agent.py --query "What is the fleet status?"

# Interactive mode
uv run python scripts/query_deployed_agent.py
```

Or use the GCP Console Playground link from the deployment output.

**Note:** Full route planning needs the MCP server. Set `MCP_SERVER_URL` in your deployment environment for remote access.
