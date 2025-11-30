#!/bin/bash
# Fleet Safety Agent Evaluation Script
# Aligned with Agent Starter Pack structure

set -e  # Exit on error

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║       Fleet Safety Agent Evaluation Pipeline              ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Layer 1: Unit Tests
echo "[Layer 1] Running Unit Tests..."
uv run pytest tests/unit/ -v
echo "✅ Unit tests passed."
echo ""

# Layer 2: Integration Tests (Code/Logic)
echo "[Layer 2] Running Integration Tests..."
uv run pytest tests/integration/ -v
echo "✅ Integration tests passed."
echo ""

# Layer 3: ADK Evaluations (Agent/Cognition)
echo "[Layer 3] Running ADK Evaluations..."
uv run adk eval \
    app/agents/fleet_safety \
    app/agents/fleet_safety/evaluation/comprehensive.evalset.json \
    --config_file_path=app/agents/fleet_safety/evaluation/comprehensive_config.json \
    --print_detailed_results

echo "✅ ADK Evaluations passed."
echo ""

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║       ✅ All evaluations passed successfully!             ║"
echo "╚═══════════════════════════════════════════════════════════╝"
exit 0
