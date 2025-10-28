import asyncio
import os
from urllib.parse import urlparse

from agent_builder import build_agent
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from runners import astream_plan

load_dotenv()

# Initialize FastAPI application
app = FastAPI(title="Agent Orchestrator")

# Build the orchestrator agent once at startup (kept warm in memory)
app.state.agent = build_agent()

# Lock ensures that only one task runs at a time (serialize execution)
app.state.agent_lock = asyncio.Lock()


class TaskRequest(BaseModel):
    """
    Schema for task requests received by the orchestrator server.

    Attributes:
        task: The user’s input prompt.
        use_async: If True, run in asynchronous streaming mode.
    """
    task: str
    use_async: bool = False  # mirrors CLI flag for consistency


@app.get("/health")
async def health():
    """
    Health-check endpoint.

    Returns:
        JSON object confirming the server is alive.
    """
    return {"status": "ok"}


@app.post("/run")
async def run_task(req: TaskRequest):
    """
    Main execution endpoint.

    Accepts a task request and streams execution results using the orchestrator agent.
    The lock ensures that tasks do not overlap, preserving the single-agent constraint.

    Args:
        req: A `TaskRequest` object containing the task and async flag.

    Returns:
        JSON status report including execution mode (sync/async).
    """
    async with app.state.agent_lock:  # serialize agent execution
        agent = app.state.agent
        if req.use_async:
            await astream_plan(agent, req.task)
            return {"status": "completed", "mode": "async"}
        # Even in "sync" mode, execution still uses async under the hood
        await astream_plan(agent, req.task)
        return {"status": "completed", "mode": "sync"}


def _bind_host_port() -> tuple[str, int]:
    """
    Determine host and port for the FastAPI server.

    Priority order:
      1. Explicit HOST / PORT environment variables.
      2. Parsed from ORCHESTRATOR_URL in the environment (if set).
      3. Defaults to 0.0.0.0:10000.

    Returns:
        (host, port) tuple for uvicorn binding.
    """
    host_env = os.getenv("HOST")
    port_env = os.getenv("PORT")
    if host_env or port_env:
        return (host_env or "0.0.0.0", int(port_env or "10000"))

    url = (os.getenv("ORCHESTRATOR_URL") or "http://0.0.0.0:10000").strip()
    if "://" not in url:
        url = "http://" + url
    parsed = urlparse(url)
    host = parsed.hostname or "0.0.0.0"
    port = parsed.port or 10000
    return host, int(port)


if __name__ == "__main__":
    import uvicorn

    host, port = _bind_host_port()
    reload = os.getenv("RELOAD", "true").lower() == "true"

    if reload:
        # When reload is enabled, uvicorn must receive the import string
        uvicorn.run("server:app", host=host, port=port, reload=True)
    else:
        # When reload is off, we can pass the app instance directly
        uvicorn.run(app, host=host, port=port, reload=False)
