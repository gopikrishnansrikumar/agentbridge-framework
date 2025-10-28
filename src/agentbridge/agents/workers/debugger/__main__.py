"""
Debugger Agent service entrypoint.

This module boots a FastAPI-based A2A server that exposes a "Debugger" agent.
The agent launches Gazebo against provided SDF/URDF files, observes runtime
errors, applies targeted fixes, and relaunches up to three times. It is meant
to be used as the final validation step after model conversion.

Notes for reviewers:
- Environment-driven configuration (host/port, provider/model, API keys).
- Minimal in-memory infra (task store + push notifications) for simplicity.
- Functionality intentionally unchanged; comments/docstrings added for clarity.
"""

import logging
import os
from urllib.parse import urlparse

import click
import httpx
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotifier, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from agent import DebuggerAgent
from agent_executor import DebuggerAgentExecutor
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Raised when the expected API key for the selected provider is missing."""


def resolve_host_port(default_host: str, default_port: int):
    """
    Determine the host/port the service should bind to.

    Priority:
      1) DEBUGGER_URL (e.g., http://0.0.0.0:10032)
      2) DEBUGGER_HOST / DEBUGGER_PORT
      3) CLI defaults

    Args:
        default_host: Host fallback (from CLI).
        default_port: Port fallback (from CLI).

    Returns:
        (host, port, service_url) where service_url is a normalized scheme://host:port
    """
    # Prefer a single env var URL if present
    url = os.getenv("DEBUGGER_URL")
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or default_host
        port = parsed.port or default_port
        scheme = parsed.scheme or "http"
        return host, port, f"{scheme}://{host}:{port}"

    # Otherwise use host/port envs, falling back to CLI
    host = os.getenv("DEBUGGER_HOST", default_host)
    port = int(os.getenv("DEBUGGER_PORT", str(default_port)))
    return host, port, f"http://{host}:{port}"


def get_provider_and_model():
    """
    Read provider/model settings from environment variables.

    Returns:
        (provider, model) strings, already stripped.
    """
    provider = os.getenv("DEBUGGER_PROVIDER", "Google").strip()
    model = os.getenv("DEBUGGER_MODEL", "gemini-2.5-flash").strip()
    return provider, model


def validate_api_key(provider: str):
    """
    Ensure a corresponding API key exists for the selected provider.

    Supported providers:
      - google  -> GOOGLE_API_KEY
      - groq    -> GROQ_API_KEY
      - openai  -> OPENAI_API_KEY

    Args:
        provider: Provider name (case-insensitive).

    Returns:
        The API key value (string) if present.

    Raises:
        MissingAPIKeyError if the expected key is not set.
        ValueError for unsupported providers.
    """
    p = (provider or "").strip().lower()

    if p == "google":
        key = os.getenv("GOOGLE_API_KEY")
        if not key:
            raise MissingAPIKeyError("GOOGLE_API_KEY environment variable not set.")
        return key

    if p == "groq":
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise MissingAPIKeyError("GROQ_API_KEY environment variable not set.")
        return key

    if p == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise MissingAPIKeyError("OPENAI_API_KEY environment variable not set.")
        return key

    # Note: Message uses DESCRIBER_PROVIDER per original code; left as-is intentionally.
    raise ValueError(
        f"Unsupported DESCRIBER_PROVIDER: {provider}. Use 'Google', 'Groq', or 'OpenAI'."
    )


@click.command()
@click.option("--host", "cli_host", default="localhost")
@click.option("--port", "cli_port", default=10032)
def main(cli_host, cli_port):
    """Start the Debugger Agent server for validating SDF & URDF files."""
    try:
        # 1) Resolve bind address (ENV overrides CLI)
        host, port, service_url = resolve_host_port(cli_host, cli_port)

        # 2) Validate provider and ensure API key is available
        provider, model = get_provider_and_model()
        validate_api_key(provider)

        # 3) Describe agent capabilities and advertised skill
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        skill = AgentSkill(
            id="runtime_debug_gazebo",
            name="Gazebo Runtime Debugger Agent",
            description=(
                "Runs Gazebo with a given SDF or URDF file, monitors for runtime errors, and applies fixes "
                "based on terminal output. Performs up to 3 launch–fix cycles, stopping when the simulation "
                "runs without errors. Focuses on live debugging and outputs a structured report of issues and fixes. "
                "Use immediately after MJCF→SDF conversion as the last pipeline step."
            ),
            tags=[
                "gazebo",
                "runtime",
                "sdf",
                "urdf",
                "ros",
                "debug",
                "simulation",
                "auto-fix",
                "debugging",
                "testing",
                "validation",
                "error monitoring",
                "feedback loop",
                "terminal",
                "launch test",
            ],
            examples=[
                "Run and debug: /path/to/robot.sdf",
                "Run a debugging analysis: /path/to/robot.urdf",
                "Launch Gazebo with /home/user/world.urdf and fix runtime issues.",
                "Simulate and auto-correct runtime errors in /models/my_bot.urdf",
            ],
        )

        agent_card = AgentCard(
            name="Debugger",
            description=(
                "Debugger Agent that validates generated SDF/URDF files by actually running them in Gazebo. "
                "Catches and fixes runtime errors that static checks or unit tests cannot. "
                "Monitors terminal output, applies targeted fixes automatically, and relaunches until the model runs clean."
            ),
            url=service_url,  # from ENV
            version="1.0.0",
            defaultInputModes=DebuggerAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=DebuggerAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # 4) Wire up request handling and in-memory infra
        httpx_client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=DebuggerAgentExecutor(),  # executor signature unchanged
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(httpx_client),
        )

        # 5) Build and run the Starlette application via Uvicorn
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        import uvicorn

        uvicorn.run(server.build(), host=host, port=port)

    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)


if __name__ == "__main__":
    main()
