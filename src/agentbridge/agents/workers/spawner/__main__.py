"""
Spawner Agent Server.

This module starts the Spawner Agent service, which integrates into the
multi-agent robotics pipeline. The Spawner Agent is responsible for modifying
simulation world files (SDF or URDF) by inserting requested objects, enabling
dynamic construction of simulated environments.

Key Features:
  - Exposes the agent as an HTTP service using A2AStarletteApplication.
  - Supports streaming updates and structured skill descriptions.
  - Validates provider setup (Google, Groq, OpenAI) before startup.
  - Provides CLI options for host/port overrides.

Environment variables (with priority order):
  - SPAWNER_URL (full URL, overrides host/port)
  - SPAWNER_HOST / SPAWNER_PORT
  - CLI flags (--host / --port)
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
from agent import SpawnerAgent
from agent_executor import SpawnerAgentExecutor
from dotenv import load_dotenv

# Load .env configuration
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Raised when a required API key is not found in environment variables."""
    pass


def resolve_host_port(default_host: str, default_port: int):
    """
    Resolve the host, port, and service URL for binding the server.

    Priority:
      1. SPAWNER_URL (complete URL form, e.g., http://host:port)
      2. SPAWNER_HOST / SPAWNER_PORT
      3. CLI defaults
    """
    url = os.getenv("SPAWNER_URL")
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or default_host
        port = parsed.port or default_port
        scheme = parsed.scheme or "http"
        return host, port, f"{scheme}://{host}:{port}"

    host = os.getenv("SPAWNER_HOST", default_host)
    port = int(os.getenv("SPAWNER_PORT", str(default_port)))
    return host, port, f"http://{host}:{port}"


def get_provider_and_model():
    """
    Retrieve provider and model for the Spawner Agent from environment.
    Defaults to Google / gemini-2.5-flash if unspecified.
    """
    provider = os.getenv("SPAWNER_PROVIDER", "Google").strip()
    model = os.getenv("SPAWNER_MODEL", "gemini-2.5-flash").strip()
    return provider, model


def validate_api_key(provider: str):
    """
    Ensure the required API key for the given provider is available.

    Args:
        provider: One of 'Google', 'Groq', or 'OpenAI'.

    Raises:
        MissingAPIKeyError: if the expected API key is missing.
        ValueError: if provider is unsupported.
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
        f"Unsupported SPAWNER_PROVIDER: {provider}. Use 'Google', 'Groq', or 'OpenAI'."
    )


@click.command()
@click.option("--host", "cli_host", default="localhost")
@click.option("--port", "cli_port", default=10041)
def main(cli_host, cli_port):
    """
    Starts the Spawner Agent server.

    Responsibilities:
      - Resolve service host and port from environment or CLI.
      - Validate LLM provider and API key availability.
      - Build an AgentCard describing capabilities and skills.
      - Start an A2AStarletteApplication with the SpawnerAgentExecutor.
    """
    try:
        # Resolve bind address (ENV overrides CLI)
        host, port, service_url = resolve_host_port(cli_host, cli_port)

        # Validate provider + API key presence
        provider, model = get_provider_and_model()
        validate_api_key(provider)

        # Define agent capabilities
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        # Define agent skill metadata
        skill = AgentSkill(
            id="spawn_world",
            name="World Spawner Tool",
            description=(
                "Takes an SDF (.sdf) or URDF (.urdf) world file as input and "
                "adds a requested object to the world file."
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
                "Given an SDF file path of a warehouse world, add a shelf at the center.",
                "Given a URDF file path of a warehouse world, add a forklift at the center.",
            ],
        )

        # Construct the agent card with identity and metadata
        agent_card = AgentCard(
            name="Spawner",
            description=(
                "Updates and visualizes an SDF or URDF world file in Gazebo "
                "by adding specified objects to the file."
            ),
            url=service_url,  # from ENV or CLI
            version="1.0.0",
            defaultInputModes=SpawnerAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=SpawnerAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # Request handler links the executor with task management
        request_handler = DefaultRequestHandler(
            agent_executor=SpawnerAgentExecutor(),
            task_store=InMemoryTaskStore(),
            # push_notifier intentionally omitted for this service
        )

        # Build the server application
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
