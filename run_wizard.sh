#!/usr/bin/env bash
set -e

echo "Setting up AgentBridge Wizard..."

# Create venv if not exists
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment with uv..."
  uv venv
fi

# Activate venv
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
uv pip install streamlit pyyaml ruamel.yaml psutil pandas

# Install project in editable mode
echo "Installing project in editable mode..."
uv pip install -e .

# Run the wizard
echo "Starting AgentBridge Setup Wizard..."
streamlit run wizard.py
