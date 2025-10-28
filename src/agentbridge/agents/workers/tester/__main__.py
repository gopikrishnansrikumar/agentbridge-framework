import logging
import os
from urllib.parse import urlparse

import click
import httpx
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotifier, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from agent import ValidatorAgent
from agent_executor import ValidatorAgentExecutor
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Raised when a required API key is missing from environment variables."""
    pass


def resolve_host_port(default_host: str, default_port: int):
    """
    Determine the host and port where the Validator Agent server should run.

    Priority order:
    1. TESTER_URL (full URL, takes precedence if set)
    2. TESTER_HOST / TESTER_PORT
    3. CLI defaults (passed into main)
    """
    url = os.getenv("TESTER_URL")
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or default_host
        port = parsed.port or default_port
        scheme = parsed.scheme or "http"
        return host, port, f"{scheme}://{host}:{port}"
    host = os.getenv("TESTER_HOST", default_host)
    port = int(os.getenv("TESTER_PORT", str(default_port)))
    return host, port, f"http://{host}:{port}"


def get_provider_and_model():
    """
    Fetch provider and model configuration for the Validator Agent.
    Defaults to Google with the gemini-2.5-flash model.
    """
    provider = os.getenv("TESTER_PROVIDER", "Google").strip()
    model = os.getenv("TESTER_MODEL", "gemini-2.5-flash").strip()
    return provider, model


def validate_api_key(provider: str):
    """
    Validate that the correct API key is set for the chosen provider.
    Raises MissingAPIKeyError if no key is found.
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
        f"Unsupported TESTER_PROVIDER: {provider}. Use 'Google', 'Groq', or 'OpenAI'."
    )


@click.command()
@click.option("--host", "cli_host", default="localhost")
@click.option("--port", "cli_port", default=10031)
def main(cli_host, cli_port):
    """
    Entry point for starting the Validator Agent server.

    The Validator Agent validates and auto-corrects SDF/URDF files
    for Gazebo/ROS by running XML/schema checks, applying fixes if necessary,
    and generating a structured validation report.
    """
    try:
        # Determine the service URL, host, and port
        host, port, service_url = resolve_host_port(cli_host, cli_port)

        # Ensure provider and API key are valid
        provider, model = get_provider_and_model()
        validate_api_key(provider)

        # Define what the agent is capable of
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)

        # Define the agent's skill description
        skill = AgentSkill(
            id="validate_and_correct_sdf_urdf",
            name="SDF/URDF Validation & Correction Agent",
            description=(
                "Validates and auto-corrects SDF (Simulation Description Format) or URDF (Unified Robot Description Format) "
                "files for Gazebo/ROS. Accepts a file path or content, runs XML/schema checks, verifies required tags, "
                "and fixes issues automatically. Performs up to 3 validate–fix cycles, or stops when all checks pass. "
                "Produces a structured validation report to ensure generated files are ready for simulation."
            ),
            tags=[
                "sdf", "urdf", "gazebo", "ros", "validation", "correction",
                "robotics", "xml", "file check", "test report", "auto-fix",
            ],
            examples=[
                "Validate and fix an SDF file: /path/to/robot.sdf",
                "Check and auto-correct /home/user/world.sdf for Gazebo.",
                "Validate and correct a URDF for ROS: /path/to/robot.urdf",
                "Test and fix /home/user/my_robot.urdf for simulation.",
            ],
        )

        # Construct the agent's metadata card
        agent_card = AgentCard(
            name="Tester",
            description=(
                "Validates and auto-corrects SDF and URDF files for Gazebo/ROS. "
                "Runs automated checks, applies fixes (up to 3 cycles), and outputs a structured report."
            ),
            url=service_url,
            version="1.0.0",
            defaultInputModes=ValidatorAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ValidatorAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # Build the request handler and server application
        httpx_client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=ValidatorAgentExecutor(),
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(httpx_client),
        )
        server = A2AStarletteApplication(
            agent_card=agent_card, http_handler=request_handler
        )

        # Start the server with Uvicorn
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
