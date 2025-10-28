"""
Spawner AGV SDF Agent Server.

This script launches a FastAPI-based A2A agent service that:
  - Accepts requests to load and visualize SDF (.sdf) world files in Gazebo.
  - Spawns an Automated Guided Vehicle (AGV) inside the environment.
  - Provides structured metadata (AgentCard) for interoperability.

Environment variable precedence:
  1. SPAWNER_AGV_URL (full URL, overrides host/port)
  2. SPAWNER_AGV_HOST / SPAWNER_AGV_PORT
  3. CLI options (--host, --port)
"""

import logging
import os
from urllib.parse import urlparse

import click
import httpx
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from agent import SpawnerAGVSDFAgent
from agent_executor import SpawnerAGVSDFAgentExecutor
from dotenv import load_dotenv

# Load environment configuration
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Raised when a required API key is missing from the environment."""
    pass


# -----------------------------
# Host/Port Resolution
# -----------------------------

def resolve_host_port(default_host: str, default_port: int):
    """
    Resolve host, port, and service URL for the agent server.

    Precedence:
      1. SPAWNER_AGV_URL (full URL form, e.g. http://0.0.0.0:10042)
      2. SPAWNER_AGV_HOST + SPAWNER_AGV_PORT
      3. CLI defaults
    """
    url = os.getenv("SPAWNER_AGV_URL")
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or default_host
        port = parsed.port or default_port
        scheme = parsed.scheme or "http"
        return host, port, f"{scheme}://{host}:{port}"

    host = os.getenv("SPAWNER_AGV_HOST", default_host)
    port = int(os.getenv("SPAWNER_AGV_PORT", str(default_port)))
    return host, port, f"http://{host}:{port}"


# -----------------------------
# Provider + API Key Validation
# -----------------------------

def get_provider_and_model():
    """Read provider and model name from environment (defaults: Google + gemini-2.5-flash)."""
    provider = os.getenv("SPAWNER_AGV_PROVIDER", "Google").strip()
    model = os.getenv("SPAWNER_AGV_MODEL", "gemini-2.5-flash").strip()
    return provider, model


def validate_api_key(provider: str):
    """Ensure that the correct API key is set for the chosen provider."""
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
        f"Unsupported SPAWNER_AGV_PROVIDER: {provider}. Use 'Google', 'Groq', or 'OpenAI'."
    )


# -----------------------------
# CLI Entrypoint
# -----------------------------

@click.command()
@click.option("--host", "cli_host", default="localhost")
@click.option("--port", "cli_port", default=10042)
def main(cli_host, cli_port):
    """Starts the Spawner AGV Agent server."""
    try:
        # Resolve bind address (ENV > CLI)
        host, port, service_url = resolve_host_port(cli_host, cli_port)

        # Validate provider + API key
        provider, model = get_provider_and_model()
        validate_api_key(provider)

        # Define agent capabilities and skills metadata
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        skill = AgentSkill(
            id="spawn_world",
            name="World Spawner AGV Tool",
            description=(
                "Takes an SDF (.sdf) world file as input and loads it into Gazebo for "
                "visualization, spawning an Automated Guided Vehicle (AGV) inside."
            ),
            tags=[
                "sdf",
                "gazebo",
                "robotics",
                "simulation",
                "visualization",
                "world file",
            ],
            examples=[
                "Load and visualize an SDF world file in Gazebo with an AGV included.",
                "Given an SDF file path, launch it in Gazebo for inspection with an AGV.",
            ],
        )

        agent_card = AgentCard(
            name="Spawner AGV (SDF World)",
            description=(
                "Launches and visualizes SDF world files in Gazebo by loading the "
                "specified .sdf file and spawning an AGV within the environment."
            ),
            url=service_url,
            version="1.0.0",
            defaultInputModes=SpawnerAGVSDFAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=SpawnerAGVSDFAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # Build request handler with agent executor
        httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=SpawnerAGVSDFAgentExecutor(),
            task_store=InMemoryTaskStore(),
            # push_notifier intentionally omitted (no streaming push for this service)
        )

        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        # Run server with Uvicorn
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
