#!/usr/bin/env bash
set -e

# Activate venv
if [ ! -d ".venv" ]; then
  echo "❌ No virtual environment found. Run ./run_wizard.sh first."
  exit 1
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Starting AgentBridge..."
uv run agentbridge --hide-access --all-workers
