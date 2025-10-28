import logging
import os
from urllib.parse import urlparse

import click
import httpx
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotifier, InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from agent import TranslatorMSFAgent
from agent_executor import TranslatorMSFAgentExecutor
from dotenv import load_dotenv

# Load .env file if available (local development)
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MissingAPIKeyError(Exception):
    """Raised if the expected API key for a provider is not set."""
    pass


def resolve_host_port(default_host: str, default_port: int):
    """
    Determine the host and port to bind the Translator MSF Agent server.

    Priority:
      1. TRANSLATOR_MSF_URL (parsed as full URL)
      2. TRANSLATOR_MSF_HOST and TRANSLATOR_MSF_PORT environment variables
      3. CLI-provided defaults
    """
    url = os.getenv("TRANSLATOR_MSF_URL")
    if url:
        parsed = urlparse(url)
        host = parsed.hostname or default_host
        port = parsed.port or default_port
        scheme = parsed.scheme or "http"
        return host, port, f"{scheme}://{host}:{port}"
    host = os.getenv("TRANSLATOR_MSF_HOST", default_host)
    port = int(os.getenv("TRANSLATOR_MSF_PORT", str(default_port)))
    return host, port, f"http://{host}:{port}"


def get_provider_and_model():
    """
    Get the configured LLM provider and model.
    Defaults to Google Gemini 2.5 Flash if none are specified.
    """
    provider = os.getenv("TRANSLATOR_MSF_PROVIDER", "Google").strip()
    model = os.getenv("TRANSLATOR_MSF_MODEL", "gemini-2.5-flash").strip()
    return provider, model


def validate_api_key(provider: str):
    """
    Ensure the required API key exists for the given provider.
    Supported providers: Google, Groq, OpenAI.
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
@click.option("--port", "cli_port", default=10023)
def main(cli_host, cli_port):
    """
    Start the Translator MSF Agent server.

    The Translator MSF Agent:
      - Translates .msf files (Model Specification Format) into SDF for Gazebo.
      - Uses retrieved few-shot examples to guide the translation process.
      - Exposes its functionality via an A2A server application.
    """
    try:
        # Resolve the bind host/port, preferring ENV over CLI args
        host, port, service_url = resolve_host_port(cli_host, cli_port)

        # Validate chosen provider and its API key
        provider, model = get_provider_and_model()
        validate_api_key(provider)

        # Define agent metadata
        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        skill = AgentSkill(
            id="translate_MSF",
            name="Translator MSF Agent",
            description=(
                "Translates MSF files (path/to/msf_file.msf) with the help of retrieved few-shot examples, "
                "producing an SDF for Gazebo."
            ),
            tags=[
                "sdf",
                "natural language",
                "json",
                "msf",
                "robotics",
                "gazebo",
                "file conversion",
            ],
            examples=[
                "Generate an SDF using model.msf",
                "Given an MSF file path, output the corresponding SDF.",
            ],
        )

        agent_card = AgentCard(
            name="Translator(MSF)",
            description=(
                "Generates an SDF for MSF (.msf) files with the help of retrieved "
                "few-shot examples from the MSF file path."
            ),
            url=service_url,
            version="1.0.0",
            defaultInputModes=TranslatorMSFAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=TranslatorMSFAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        # Build request handling layer
        httpx_client = httpx.AsyncClient()
        request_handler = DefaultRequestHandler(
            agent_executor=TranslatorMSFAgentExecutor(),
            task_store=InMemoryTaskStore(),
            push_notifier=InMemoryPushNotifier(httpx_client),
        )

        # Create and run the server
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
