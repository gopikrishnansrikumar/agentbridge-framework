"""A UI host service to interact with the agent framework.

Usage:
  uv main.py
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx
import mesop as me
from components.api_key_dialog import api_key_dialog
from components.page_scaffold import page_scaffold
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware
from pages.agent_list import agent_list_page
from pages.conversation import conversation_page
from pages.conversations_list import conversations_home_page_content
from pages.event_list import event_list_page
from pages.home import landing_page
from pages.messages import agent_messages_page as agent_messages_page_content
from pages.task_list import task_list_page
from pages.tools import tools_list_page
from service.server.server import ConversationServer
from state import host_agent_service
from state.state import AppState

# Load environment variables from .env in the app directory
APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR / ".env")


def _delegator_url() -> str:
    """Return the Delegator base URL (used for JSON-RPC calls from the UI).

    Fallback: http://localhost:12000  
    Ensures URL has scheme and no trailing slash.
    """
    url = (os.getenv("DELEGATOR_URL") or "http://localhost:12000").strip()
    if not urlparse(url).scheme:
        url = "http://" + url
    return url.rstrip("/")


def _bind_host_port() -> tuple[str, int]:
    """Resolve host and port for uvicorn bind.

    Priority:
      1) Explicit overrides via AB_HOST / AB_PORT
      2) Values parsed from DELEGATOR_URL
      3) Default: 0.0.0.0:12000
    """
    ab_host = os.getenv("AB_HOST")
    ab_port = os.getenv("AB_PORT")
    if ab_host or ab_port:
        return (ab_host or "0.0.0.0", int(ab_port or "12000"))

    parsed = urlparse(_delegator_url())
    host = parsed.hostname or "0.0.0.0"
    port = parsed.port or 12000
    return host, int(port)


def on_load(e: me.LoadEvent):  # pylint: disable=unused-argument
    """Initialize UI state when a page is loaded."""
    state = me.state(AppState)
    me.set_theme_mode(state.theme_mode)

    # Restore conversation_id if provided as query param
    if "conversation_id" in me.query_params:
        state.current_conversation_id = me.query_params["conversation_id"]
    else:
        state.current_conversation_id = ""

    # API key / Vertex AI setup
    uses_vertex_ai = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").upper() == "TRUE"
    api_key = os.getenv("GOOGLE_API_KEY", "")

    if uses_vertex_ai:
        state.uses_vertex_ai = True
    elif api_key:
        state.api_key = api_key
    else:
        # Ask user for API key interactively if not set
        state.api_key_dialog_open = True


# CSP policy for loading frontend components
security_policy = me.SecurityPolicy(
    allowed_script_srcs=[
        "https://cdn.jsdelivr.net",
    ]
)

# ------------------ Page Routes ------------------ #
@me.page(
    path="/",
    title="Agent Bridge",
    on_load=on_load,
    security_policy=security_policy,
    stylesheets=["/static/custom.css"],
)
def home_page():
    landing_page()


@me.page(
    path="/agent_messages",
    title="Messages",
    on_load=on_load,
    security_policy=security_policy,
    stylesheets=["/static/custom.css"],
)
def agent_messages_page():
    """Agent conversations view."""
    state = me.state(AppState)
    api_key_dialog()
    with page_scaffold():
        agent_messages_page_content(state)


@me.page(
    path="/conversations",
    title="Conversations",
    on_load=on_load,
    security_policy=security_policy,
    stylesheets=["/static/custom.css"],
)
def conversations_page():
    """List of past conversations."""
    state = me.state(AppState)
    api_key_dialog()
    with page_scaffold():
        conversations_home_page_content(state)


@me.page(
    path="/agents",
    title="Agents",
    on_load=on_load,
    security_policy=security_policy,
    stylesheets=["/static/custom.css"],
)
def agents_page():
    """Registered agents view."""
    api_key_dialog()
    agent_list_page(me.state(AppState))


@me.page(
    path="/conversation",
    title="Conversation",
    on_load=on_load,
    security_policy=security_policy,
    stylesheets=["/static/custom.css"],
)
def chat_page():
    """Single conversation view."""
    api_key_dialog()
    conversation_page(me.state(AppState))


@me.page(
    path="/event_list",
    title="Event List",
    on_load=on_load,
    security_policy=security_policy,
    stylesheets=["/static/custom.css"],
)
def event_page():
    """Delegator events log."""
    api_key_dialog()
    event_list_page(me.state(AppState))


@me.page(
    path="/task_list",
    title="Task List",
    on_load=on_load,
    security_policy=security_policy,
    stylesheets=["/static/custom.css"],
)
def task_page():
    """Current and completed tasks view."""
    api_key_dialog()
    task_list_page(me.state(AppState))


@me.page(
    path="/tools",
    title="Tools",
    on_load=on_load,
    security_policy=security_policy,
    stylesheets=["/static/custom.css"],
)
def tools_page():
    """Registered tools view."""
    api_key_dialog()
    tools_list_page(me.state(AppState))


# ------------------ HTTPX Client Wrapper ------------------ #
class HTTPXClientWrapper:
    """Simple lifecycle-managed singleton wrapper around httpx.AsyncClient."""

    async_client: httpx.AsyncClient = None

    def start(self):
        """Instantiate client (called on FastAPI startup)."""
        self.async_client = httpx.AsyncClient(timeout=30)

    async def stop(self):
        """Close client (called on FastAPI shutdown)."""
        await self.async_client.aclose()
        self.async_client = None

    def __call__(self):
        """Return the client instance if running."""
        assert self.async_client is not None
        return self.async_client


# Global objects shared with server
httpx_client_wrapper = HTTPXClientWrapper()
agent_server = None


# ------------------ FastAPI Lifespan ------------------ #
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler to manage startup and shutdown tasks."""
    httpx_client_wrapper.start()
    ConversationServer(app, httpx_client_wrapper())
    app.openapi_schema = None
    app.mount(
        "/",
        WSGIMiddleware(
            me.create_wsgi_app(debug_mode=os.environ.get("DEBUG_MODE", "") == "true")
        ),
    )
    app.setup()
    yield
    await httpx_client_wrapper.stop()


# ------------------ Entrypoint ------------------ #
if __name__ == "__main__":
    import uvicorn

    app = FastAPI(lifespan=lifespan)

    # Resolve bind host/port and Delegator URL
    host, port = _bind_host_port()
    delegator_base = _delegator_url()

    # Store delegator_base for other services to use
    host_agent_service.server_url = delegator_base

    uvicorn.run(
        app,
        host=host,
        port=port,
        timeout_graceful_shutdown=0,
    )
