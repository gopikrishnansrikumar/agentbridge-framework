"""
Prechecker Agent Server Entrypoint.

This module launches the Prechecker Agent as an A2A (Agent-to-Agent) service.
The Prechecker is responsible for validating MuJoCo MJCF XML files before they
enter the multi-agent pipeline. It performs schema and structural checks to ensure
that downstream agents (Describer, Translator, Tester, Debugger) only process
well-formed inputs.

Validation checks include:
  - Required XML sections
  - Proper nesting of tags (body, geom, inertial, etc.)
  - Duplicate names
  - Invalid or missing attributes

Outputs:
  - A plain text report (.txt)
  - A Markdown report (.md)

This agent serves as the first "gatekeeper" in the robotics simulation workflow.
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
from agent import PrecheckerAgent
from agent_executor import PrecheckerAgentExecutor
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Raised when the required API key for the chosen provider is missing."""


# -------------------------------------------------------------------
# Configuration helpers
# -------------------------------------------------------------------

def get_provider_and_model_from_env():
    """
    Determine which provider (Google, Groq, OpenAI) and model should be used.

    Returns:
        Tuple (provider, model) as strings.
    """
    provider = os.getenv("PRECHECKER_PROVIDER", "Google").strip()
    model = os.getenv("PRECHECKER_MODEL", "gemini-2.5-flash").strip()
    return provider, model


def get_api_key_for_provider(provider: str) -> str:
    """
    Retrieve the API key for the given provider.

    Supported:
      - Google  -> GOOGLE_API_KEY
      - Groq    -> GROQ_API_KEY
      - OpenAI  -> OPENAI_API_KEY

    Raises:
        MissingAPIKeyError if the key is not set.
        ValueError if the provider is unsupported.
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

    raise ValueError(
        f"Unsupported PRECHECKER_PROVIDER: {provider}. Use 'Google', 'Groq', or 'OpenAI'."
    )


def resolve_host_port(default_host: str, default_port: int):
    """
    Resolve bind host/port for the Prechecker server.

    Priority:
      1. PRECHECKER_URL (full URL, e.g., http://0.0.0.0:10011)
      2. PRECHECKER_HOST / PRECHECKER_PORT environment variables
      3. CLI defaults

    Returns:
        Tuple (host, port, url)
    """
    url = os.getenv("PRECHECKER_URL")
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or default_host
        port = parsed.port or default_port
        return host, port, f"{parsed.scheme or 'http'}://{host}:{port}"

    host = os.getenv("PRECHECKER_HOST", default_host)
    port = int(os.getenv("PRECHECKER_PORT", str(default_port)))
    return host, port, f"http://{host}:{port}"


# -------------------------------------------------------------------
# CLI Entrypoint
# -------------------------------------------------------------------

@click.command()
@click.option("--host", "cli_host", default="localhost")
@click.option("--port", "cli_port", default=10011)
def main(cli_host, cli_port):
    """Start the Prechecker Agent server."""
    try:
        # 1) Resolve host/port (ENV takes precedence over CLI)
        host, port, service_url = resolve_host_port(cli_host, cli_port)

        # 2) Check provider/model configuration
        provider, model = get_provider_and_model_from_env()
        get_api_key_for_provider(provider)

        # 3) Define agent metadata (capabilities and skill)
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        skill = AgentSkill(
            id="precheck",
            name="Prechecker Agent",
            description=(
                "Validates a MuJoCo MJCF XML file before it enters the pipeline. "
                "Performs schema and structural checks (e.g., required sections, correct nesting "
                "of body/geom/inertial tags, duplicate names, invalid attributes). "
                "Outputs a detailed validation report in both plain text (.txt) and Markdown (.md)."
            ),
            tags=[
                "mjcf",
                "mujoco",
                "xml",
                "robotics",
                "validation",
                "checker",
                "report",
            ],
            examples=[
                "Validate this MJCF file and generate a structured validation report."
            ],
        )

        agent_card = AgentCard(
            name="Prechecker",
            description=(
                "Validates MuJoCo MJCF XML files by performing schema and structural checks. "
                "Acts as the first gatekeeper in the multi-agent pipeline before Describer, "
                "Translator, Tester, and Debugger."
            ),
            url=service_url,  # pulled from ENV
            version="1.0.0",
            defaultInputModes=PrecheckerAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=PrecheckerAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # 4) Build the execution stack (executor, task store, push notifier)
        httpx_client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=PrecheckerAgentExecutor(),
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(httpx_client),
        )

        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        # 5) Launch Uvicorn server
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
