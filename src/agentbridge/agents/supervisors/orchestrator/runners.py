import asyncio
import re
import time

from langchain_core.messages import HumanMessage
from ratelimit import limits, sleep_and_retry
from settings import RECURSION_LIMIT


# =====================================================
# Rate-limiting and retry helpers for non-streaming calls
# =====================================================

@sleep_and_retry
@limits(calls=15, period=60)
def _invoke_rate_limited(agent, *args, **kwargs):
    """
    Wrapper around `agent.invoke` that applies a rate limit.

    Limits:
        - 15 calls per 60 seconds
    """
    return agent.invoke(*args, **kwargs)


def _extract_retry_delay(error_msg, default_delay=30):
    """
    Parse retry delay (in seconds) from an error message string.

    Args:
        error_msg: The error message to inspect.
        default_delay: Default delay if no value is found.

    Returns:
        int: Number of seconds to wait before retrying.
    """
    m = re.search(r"retry_delay\s*{\s*seconds:\s*(\d+)", str(error_msg))
    return int(m.group(1)) if m else default_delay


def invoke_with_retry(agent, *args, retries=3, **kwargs):
    """
    Attempt to call the agent with retry logic for rate limiting errors.

    Retries up to `retries` times if error indicates resource exhaustion (429).
    Waits for the delay specified in the error (if present), or a default of 30s.

    Args:
        agent: The agent instance to call.
        retries: Maximum number of retries allowed.

    Raises:
        RuntimeError: If retries are exhausted without success.

    Returns:
        The result of `agent.invoke`.
    """
    for i in range(retries):
        try:
            return _invoke_rate_limited(agent, *args, **kwargs)
        except Exception as e:
            s = str(e)
            if "429" in s or "ResourceExhausted" in s:
                delay = _extract_retry_delay(s)
                print(f"[Rate limit] Retry {i+1}/{retries} in {delay}s...")
                time.sleep(delay)
            else:
                raise
    raise RuntimeError("Failed due to repeated rate limiting.")


# =====================================================
# Streaming execution functions (async and sync versions)
# =====================================================

async def astream_plan(agent, task: str):
    """
    Run the agent asynchronously and stream output events.

    This function prints incremental outputs from the agent in real-time
    while filtering out system-level noise (e.g., tool start/end markers).

    Args:
        agent: The ReAct agent instance.
        task: The user’s task prompt.
    """
    print("\n=== Streaming ReAct Agent Output (async) ===\n")
    inputs = {"messages": [HumanMessage(content=task)]}
    config = {"recursion_limit": RECURSION_LIMIT}

    async for event in agent.astream_events(inputs, version="v2", config=config):
        kind = event["event"]

        line_to_print = None  # placeholder for actual agent text

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            text = getattr(chunk, "content", None) or getattr(chunk, "delta", None)
            if text:
                line_to_print = text

        elif kind in {"on_tool_start", "on_tool_end", "on_chain_start", "on_chain_end"}:
            # Suppress tool/chain lifecycle markers to keep output clean
            continue

        # Print filtered agent outputs line by line
        if line_to_print:
            for ln in str(line_to_print).splitlines():
                if ln.strip():  # skip empty/whitespace lines
                    print(ln, flush=True)

    print()  # final newline at end


def stream_plan(agent, task: str):
    """
    Synchronous wrapper around `astream_plan`.

    Runs the async streaming function inside its own event loop.
    """
    asyncio.run(astream_plan(agent, task))
