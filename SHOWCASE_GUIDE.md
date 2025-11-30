# Fleet Safety Platform - Showcase Guide

This guide explains how to run the Fleet Safety Platform to showcase **Observability**, **Session Management**, and **Memory** features using the Google Agent Development Kit (ADK).

## Quick Start: ADK Web UI

The ADK Web UI provides visual traces, tool call logs, and conversation history.

1. **Start the Web UI:**

    ```bash
    make playground
    ```

    Or manually:

    ```bash
    uv run adk web app/agents
    ```

2. **Open in Browser:**
    Navigate to `http://localhost:8000` (or the port shown in the terminal).

3. **Select Agent:**
    Choose `fleet_safety_agent` from the sidebar.

## Demo Scenarios

### Scenario 1: Observability & Traceability

**Goal:** Show how the Orchestrator coordinates multiple agents and how we can trace every step.

1. **User Query:**
    > "Plan a safe route for vehicle v001 (Heavy Truck) driven by driver d001 from The Strand London to Bushey Heath leaving now."
2. **Observe in Web UI:**
    * Watch the **Traces** tab populate in real-time.
    * See the **Orchestrator** call `RoutePlanner`.
    * See `RoutePlanner` call the MCP tool `get_directions`.
    * See `SafetyScorer` evaluate the routes.
    * **Highlight:** Click on a tool call to show the raw JSON payload (proof of real integration).

### Scenario 2: Session Memory

**Goal:** Demonstrate that the agent remembers context within the session.

1. **User Query (Follow-up):**
    > "Which of those routes had the lowest risk score?"
2. **Observe:**
    * The agent answers without needing to re-plan the route.
    * It accesses the session history to retrieve the previous analysis.

### Scenario 3: Long-Term Memory

**Goal:** Show the agent using `load_memory` to recall past context.

1. **User Query:**
    > "What is the standard safety protocol for critical alerts?"
    *(Or if you have populated memory: "What did we decide for vehicle v001 yesterday?")*
2. **Observe:**
    * Look for a `load_memory` tool call in the trace.

## Evaluation (ADK Eval)

**Run Evaluation:**

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

**What this does:**

* Loads the `FleetSafetyOrchestrator` via `app/agent.py`.
* Runs the scenarios defined in `integration.evalset.json`.
* Scores the agent based on **Tool Usage Accuracy** and **Response Quality**.

## Under the Hood

* **`app/agent.py`**: The entry point that configures the `FleetSafetyOrchestrator` and exports `app` for ADK.
* **`app/agent_engine_app.py`**: Production wrapper with telemetry, feedback, and artifact management for Vertex AI Agent Engine deployment.
* **`app/app_utils/`**: Deployment CLI, telemetry setup, and Pydantic models from the Agent Starter Pack.
* **MCP Integration**: The system connects to the Google Maps MCP server for live data.

## Deployed Agent Testing

After deploying with `make deploy`, you can test the deployed agent:

```bash
# Query the deployed agent
uv run python scripts/query_deployed_agent.py --query "What is the fleet status?"

# Interactive mode
uv run python scripts/query_deployed_agent.py
```

Or use the **GCP Console Playground** link provided after deployment.

> **Note:** Route planning requires the MCP server, which only works locally (stdio transport). Basic queries like fleet status work in the deployed version.

## Troubleshooting

* **MCP Connection Error:** Ensure `google-maps-mcp-server` is installed and `GOOGLE_MAPS_API_KEY` is set in `.env`.
* **Database Lock:** If using persistent sessions, ensure no other process is holding the `data/fleet_safety.db` lock.
* **Deployment Fails:** Check that `gcloud` is authenticated and the project has Vertex AI API enabled (`make setup-dev-env`).
