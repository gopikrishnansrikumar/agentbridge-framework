# main.py
import argparse
import asyncio

from agent_builder import build_agent
from dotenv import load_dotenv
from runners import astream_plan, stream_plan


def main():
    """
    Entry point for running the orchestrator.

    This script allows execution of the agent in either:
      - synchronous mode (default), or
      - asynchronous mode (with live streaming updates).

    Command-line arguments:
        --task   : A task prompt for the orchestrator. If omitted, the user will be prompted interactively.
        --async  : Run in asynchronous streaming mode.
    """
    load_dotenv()  # Load environment variables from .env if available

    parser = argparse.ArgumentParser(
        description="Stream a ReAct plan with live tool events."
    )
    parser.add_argument(
        "--task",
        type=str,
        help="Task prompt for the orchestrator (if omitted, will prompt).",
    )
    parser.add_argument(
        "--async", dest="use_async", action="store_true", help="Use async streaming."
    )
    args = parser.parse_args()

    # Use provided task or fall back to interactive input
    task = args.task or input("Enter your task: ").strip()

    # Build the orchestrator agent (configured in agent_builder.py)
    agent = build_agent()

    # Execute the plan using either synchronous or asynchronous streaming
    if args.use_async:
        asyncio.run(astream_plan(agent, task))
    else:
        # stream_plan internally manages its own asyncio loop
        stream_plan(agent, task)


if __name__ == "__main__":
    main()
