import logging
import os
from urllib.parse import urlparse

import click
import httpx
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotifier, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from agent import TranslatorSDFAgent
from agent_executor import TranslatorSDFAgentExecutor
from dotenv import load_dotenv

# Load environment variables from .env file if present (local dev setup)
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Raised if a required provider API key is missing."""
    pass


def resolve_host_port(default_host: str, default_port: int):
    """
    Determine the host/port to bind the Translator SDF Agent server.

    Priority:
      1. TRANSLATOR_SDF_URL (full URL, parsed)
      2. TRANSLATOR_SDF_HOST + TRANSLATOR_SDF_PORT
      3. CLI-provided defaults
    """
    url = os.getenv("TRANSLATOR_SDF_URL")
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or default_host
        port = parsed.port or default_port
        scheme = parsed.scheme or "http"
        return host, port, f"{scheme}://{host}:{port}"
    host = os.getenv("TRANSLATOR_SDF_HOST", default_host)
    port = int(os.getenv("TRANSLATOR_SDF_PORT", str(default_port)))
    return host, port, f"http://{host}:{port}"


def get_provider_and_model():
    """
    Get the configured LLM provider and model from environment.
    Defaults to Google Gemini 2.5 Flash if not set.
    """
    provider = os.getenv("TRANSLATOR_SDF_PROVIDER", "Google").strip()
    model = os.getenv("TRANSLATOR_SDF_MODEL", "gemini-2.5-flash").strip()
    return provider, model


def validate_api_key(provider: str):
    """
    Ensure that the correct API key exists for the chosen provider.
    Raises MissingAPIKeyError if missing.
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


@click.command()
@click.option("--host", "cli_host", default="localhost")
@click.option("--port", "cli_port", default=10021)
def main(cli_host, cli_port):
    """
    Entry point: starts the Translator SDF Agent server.

    The Translator SDF Agent:
      - Combines a natural language description (.txt), a structured JSON description,
        and an MJCF file path.
      - Retrieves few-shot examples from the MJCF.
      - Produces a valid SDF (Simulation Description Format) file for Gazebo.
    """
    try:
        # Resolve host/port, preferring environment variables over CLI args
        host, port, service_url = resolve_host_port(cli_host, cli_port)

        # Ensure provider and required API key are configured
        provider, model = get_provider_and_model()
        validate_api_key(provider)

        # Define agent metadata
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        skill = AgentSkill(
            id="translate_sdf",
            name="Translator SDF Agent",
            description=(
                "Combines a .txt description and a .json description, and uses an MJCF file path "
                "to retrieve few-shot examples, producing an SDF for Gazebo."
            ),
            tags=[
                "sdf",
                "natural language",
                "json",
                "mjcf",
                "robotics",
                "gazebo",
                "file conversion",
            ],
            examples=[
                "Generate an SDF using description.txt, description.json, and model.mjcf",
                "Given natural language, JSON, and an MJCF file path, output the corresponding SDF.",
            ],
        )

        agent_card = AgentCard(
            name="Translator(SDF)",
            description=(
                "Generates an SDF by combining .txt and .json descriptions and retrieving "
                "few-shot examples from an MJCF file path."
            ),
            url=service_url,
            version="1.0.0",
            defaultInputModes=TranslatorSDFAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=TranslatorSDFAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # Build server request handling
        httpx_client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=TranslatorSDFAgentExecutor(),
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(httpx_client),
        )

        # Start the server application
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
