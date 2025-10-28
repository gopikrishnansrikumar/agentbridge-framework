"""
ApplicationManager: Abstract interface for managing conversations, agents,
messages, tasks, and events.

This defines the contract that concrete manager implementations (e.g.,
ADKHostManager) must fulfill to support the AgentBridge system. By abstracting
this interface, the frontend and server components can interact with managers
without depending on a specific backend implementation.
"""

from abc import ABC, abstractmethod

from a2a.types import AgentCard, Message, Task
from service.types import Conversation, Event


class ApplicationManager(ABC):
    """
    Abstract base class for application managers.

    A manager coordinates conversations, agents, and tasks. It exposes
    methods for creating conversations, processing messages, registering
    agents, and querying system state (conversations, tasks, events, etc.).
    """

    @abstractmethod
    def create_conversation(self) -> Conversation:
        """
        Start a new conversation and return its representation.
        """
        pass

    @abstractmethod
    def sanitize_message(self, message: Message) -> Message:
        """
        Optionally adjust a message before processing (e.g., associate it
        with an active task if needed).
        """
        pass

    @abstractmethod
    async def process_message(self, message: Message):
        """
        Process an incoming message:
          - Run it through the backend logic/agent framework.
          - Generate events and update tasks accordingly.
        """
        pass

    @abstractmethod
    def register_agent(self, url: str):
        """
        Register a new agent with the system from its URL or base address.
        """
        pass

    @abstractmethod
    def get_pending_messages(self) -> list[tuple[str, str]]:
        """
        Return a list of (message_id, status_text) for messages still being
        processed by agents or tasks.
        """
        pass

    @abstractmethod
    def get_conversation(self, conversation_id: str | None) -> Conversation | None:
        """
        Retrieve a conversation by its ID, or return None if not found.
        """
        pass

    # --- Properties that expose current state ---

    @property
    @abstractmethod
    def conversations(self) -> list[Conversation]:
        """All known conversations managed by this application."""
        pass

    @property
    @abstractmethod
    def tasks(self) -> list[Task]:
        """All tasks known to the manager (active or completed)."""
        pass

    @property
    @abstractmethod
    def agents(self) -> list[AgentCard]:
        """Registered agents available to the system."""
        pass

    @property
    @abstractmethod
    def events(self) -> list[Event]:
        """Chronological list of all emitted events."""
        pass
