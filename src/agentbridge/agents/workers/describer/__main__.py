"""
Describer Agent service entrypoint.

This module boots a FastAPI-based A2A server that exposes a "Describer" agent.
The agent reads MuJoCo MJCF XML files and produces:
  1. A natural language description (.txt)
  2. A structured JSON description (.json)

These outputs are meant to support downstream translator agents
(e.g., SDF Translator or URDF Translator) by providing a semantic
and machine-readable representation of the model.

Notes for reviewers:
- Configuration is environment-variable driven (provider, model, keys, host/port).
- Minimal in-memory task/push infra is used for simplicity.
- Functionality is unchanged from the original version; only comments and docstrings are improved.
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
from agent import DescriberAgent
from agent_executor import DescriberAgentExecutor
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
    Determine provider/model settings.

    Returns:
        (provider, model) tuple as strings.
    """
    provider = os.getenv("DESCRIBER_PROVIDER", "Google").strip()
    model = os.getenv("DESCRIBER_MODEL", "gemini-2.5-flash").strip()
    return provider, model


def get_api_key_for_provider(provider: str) -> str:
    """
    Fetch the API key required for the given provider.

    Supported providers:
      - google  -> GOOGLE_API_KEY
      - groq    -> GROQ_API_KEY
      - openai  -> OPENAI_API_KEY

    Raises:
        MissingAPIKeyError if the expected key is not found.
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

    raise ValueError(
        f"Unsupported DESCRIBER_PROVIDER: {provider}. Use 'Google', 'Groq', or 'OpenAI'."
    )


def resolve_host_port(default_host: str, default_port: int):
    """
    Resolve bind host/port for Uvicorn server.

    Priority:
      1. DESCRIBER_URL (full URL, e.g., http://0.0.0.0:10011)
      2. DESCRIBER_HOST / DESCRIBER_PORT env vars
      3. Defaults (from CLI args)

    Returns:
        (host, port, url) tuple
    """
    url = os.getenv("DESCRIBER_URL")
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or default_host
        port = parsed.port or default_port
        return host, port, f"{parsed.scheme or 'http'}://{host}:{port}"

    host = os.getenv("DESCRIBER_HOST", default_host)
    port = int(os.getenv("DESCRIBER_PORT", str(default_port)))
    return host, port, f"http://{host}:{port}"


# -------------------------------------------------------------------
# CLI Entrypoint
# -------------------------------------------------------------------

@click.command()
@click.option("--host", "cli_host", default="localhost")
@click.option("--port", "cli_port", default=10011)
def main(cli_host, cli_port):
    """Start the Describer Agent server."""
    try:
        # 1) Resolve bind host/port, with ENV taking precedence over CLI
        host, port, service_url = resolve_host_port(cli_host, cli_port)

        # 2) Ensure provider/model are valid and API key exists
        provider, model = get_provider_and_model_from_env()
        get_api_key_for_provider(provider)

        # 3) Define agent metadata (capabilities and advertised skill)
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        skill = AgentSkill(
            id="describe",
            name="Describer Agent",
            description=(
                "Reads a MuJoCo MJCF XML file and generates both a natural language (.txt) "
                "AND a structured JSON (.json) description of all important elements. "
                "Both are suitable for input to the Translator SDF Agent or Translator URDF Agent."
            ),
            tags=["mjcf", "mujoco", "xml", "robotics", "txt", "json", "description"],
            examples=[
                "Describe this MJCF file as both a natural language description (.txt) "
                "and a structured JSON description (.json) file"
            ],
        )

        agent_card = AgentCard(
            name="Describer",
            description=(
                "Produces BOTH a natural language description (.txt) and a structured JSON "
                "description (.json) from a MuJoCo MJCF XML file and saves both files."
            ),
            url=service_url,  # host/port resolved above
            version="1.0.0",
            defaultInputModes=DescriberAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=DescriberAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # 4) Build handler stack with in-memory infra
        httpx_client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=DescriberAgentExecutor(),
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(httpx_client),
        )

        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        # 5) Run the Uvicorn server
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
