import dataclasses
from typing import Any, Literal, Tuple

import mesop as me
from pydantic.dataclasses import dataclass

# Type alias for message content, which may be plain text or structured data
ContentPart = str | dict[str, Any]


# -------------------------------------------------------------------
# Core state models for conversations, messages, tasks, and events
# -------------------------------------------------------------------
@dataclass
class StateConversation:
    """Conversation state model (UI-facing).

    Represents a single conversation with metadata and associated messages.
    """

    conversation_id: str = ""
    conversation_name: str = ""
    is_active: bool = True
    message_ids: list[str] = dataclasses.field(default_factory=list)


@dataclass
class StateMessage:
    """Message state model (UI-facing).

    Holds message identifiers, role, and message content.
    """

    message_id: str = ""
    task_id: str = ""
    context_id: str = ""
    role: str = ""
    # Content is stored as a list of (value, media type) pairs.
    content: list[Tuple[ContentPart, str]] = dataclasses.field(default_factory=list)


@dataclass
class StateTask:
    """Task state model (UI-facing).

    Represents a unit of work within a conversation, with state and artifacts.
    """

    task_id: str = ""
    context_id: str | None = None
    state: str | None = None
    message: StateMessage = dataclasses.field(default_factory=StateMessage)
    artifacts: list[list[Tuple[ContentPart, str]]] = dataclasses.field(
        default_factory=list
    )


@dataclass
class SessionTask:
    """Wraps a StateTask with the conversation ID it belongs to."""

    context_id: str = ""
    task: StateTask = dataclasses.field(default_factory=StateTask)


@dataclass
class StateEvent:
    """Event state model (UI-facing).

    Used for logging events that occur within conversations and tasks.
    """

    context_id: str = ""
    actor: str = ""
    role: str = ""
    id: str = ""
    # Each entry is a (value, media type) pair.
    content: list[Tuple[ContentPart, str]] = dataclasses.field(default_factory=list)


# -------------------------------------------------------------------
# Application-wide state containers
# -------------------------------------------------------------------
@me.stateclass
class AppState:
    """Global Mesop application state."""

    sidenav_open: bool = False
    auto_scroll_enabled: bool = True
    theme_mode: Literal["system", "light", "dark"] = "dark"

    # Conversation data
    current_conversation_id: str = ""
    conversations: list[StateConversation]
    messages: list[StateMessage]

    # Task and event tracking
    task_list: list[SessionTask] = dataclasses.field(default_factory=list)
    event_list: list[StateEvent] = dataclasses.field(default_factory=list)
    background_tasks: dict[str, str] = dataclasses.field(default_factory=dict)

    # Message aliases (e.g., shorthand replacements for user input)
    message_aliases: dict[str, str] = dataclasses.field(default_factory=dict)

    # Form state
    completed_forms: dict[str, dict[str, Any] | None] = dataclasses.field(
        default_factory=dict
    )
    form_responses: dict[str, str] = dataclasses.field(default_factory=dict)

    # UI and polling settings
    polling_interval: int = 1

    # API key management
    api_key: str = ""
    uses_vertex_ai: bool = False
    api_key_dialog_open: bool = False


@me.stateclass
class SettingsState:
    """UI settings state, mainly for supported output formats."""

    output_mime_types: list[str] = dataclasses.field(
        default_factory=lambda: [
            "image/*",
            "text/plain",
        ]
    )
