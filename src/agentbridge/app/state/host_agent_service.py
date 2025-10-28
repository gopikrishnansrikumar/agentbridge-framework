import json
import os
import sys
import traceback
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from a2a.types import FileWithBytes, Message, Part, Role, Task, TaskState
from dotenv import load_dotenv
from service.client.client import ConversationClient
from service.types import (
    Conversation,
    CreateConversationRequest,
    Event,
    GetEventRequest,
    ListAgentRequest,
    ListConversationRequest,
    ListMessageRequest,
    ListTaskRequest,
    MessageInfo,
    PendingMessageRequest,
    RegisterAgentRequest,
    SendMessageRequest,
)

from .state import (
    AppState,
    SessionTask,
    StateConversation,
    StateEvent,
    StateMessage,
    StateTask,
)

# Load environment variables from project root
APP_DIR = Path(__file__).resolve().parents[1]
load_dotenv(APP_DIR / ".env")


def _default_delegator_url() -> str:
    """
    Resolve the Delegator base URL from environment variables.

    - If DELEGATOR_URL is set, use it.
    - Otherwise, fall back to http://localhost:12000.
    - Always ensure a scheme (http://) is present.
    - Strip trailing slashes for consistency.
    """
    url = (os.getenv("DELEGATOR_URL") or "http://localhost:12000").strip()
    if not urlparse(url).scheme:
        url = "http://" + url
    return url.rstrip("/")


DELEGATOR_URL: str = _default_delegator_url()


# -------------------------------------------------------------------
# Conversation and Messaging Operations
# -------------------------------------------------------------------
async def ListConversations() -> list[Conversation]:
    """Retrieve all conversations from the Delegator service."""
    client = ConversationClient(DELEGATOR_URL)
    try:
        response = await client.list_conversation(ListConversationRequest())
        return response.result if response.result else []
    except Exception as e:
        print("Failed to list conversations:", e)
    return []


async def SendMessage(message: Message) -> Message | MessageInfo | None:
    """Send a message into an active conversation."""
    client = ConversationClient(DELEGATOR_URL)
    try:
        response = await client.send_message(SendMessageRequest(params=message))
        return response.result
    except Exception:
        traceback.print_exc()
        print("Failed to send message")
    return None


async def CreateConversation() -> Conversation:
    """Create a new conversation and return it."""
    client = ConversationClient(DELEGATOR_URL)
    try:
        response = await client.create_conversation(CreateConversationRequest())
        return (
            response.result
            if response.result
            else Conversation(conversation_id="", is_active=False)
        )
    except Exception as e:
        print("Failed to create conversation:", e)
    return Conversation(conversation_id="", is_active=False)


async def ListRemoteAgents():
    """Get all registered remote agents from the Delegator."""
    client = ConversationClient(DELEGATOR_URL)
    try:
        response = await client.list_agents(ListAgentRequest())
        return response.result
    except Exception as e:
        print("Failed to read agents:", e)


async def AddRemoteAgent(path: str):
    """Register a new agent from a given path."""
    client = ConversationClient(DELEGATOR_URL)
    try:
        await client.register_agent(RegisterAgentRequest(params=path))
    except Exception as e:
        print("Failed to register the agent:", e)


async def GetEvents() -> list[Event]:
    """Fetch all recent events (agent actions, messages, etc.)."""
    client = ConversationClient(DELEGATOR_URL)
    try:
        response = await client.get_events(GetEventRequest())
        return response.result if response.result else []
    except Exception as e:
        print("Failed to get events:", e)
    return []


async def GetProcessingMessages():
    """Retrieve currently pending messages (still being processed)."""
    client = ConversationClient(DELEGATOR_URL)
    try:
        response = await client.get_pending_messages(PendingMessageRequest())
        return dict(response.result)
    except Exception as e:
        print("Error getting pending messages:", e)


def GetMessageAliases():
    """Return any locally defined message aliases (currently empty)."""
    return {}


async def GetTasks():
    """List all tasks currently tracked by the Delegator."""
    client = ConversationClient(DELEGATOR_URL)
    try:
        response = await client.list_tasks(ListTaskRequest())
        return response.result
    except Exception as e:
        print("Failed to list tasks:", e)


async def ListMessages(conversation_id: str) -> list[Message]:
    """Get all messages for a given conversation ID."""
    client = ConversationClient(DELEGATOR_URL)
    try:
        response = await client.list_messages(
            ListMessageRequest(params=conversation_id)
        )
        return response.result if response.result else []
    except Exception as e:
        print("Failed to list messages:", e)
    return []


# -------------------------------------------------------------------
# State Synchronization
# -------------------------------------------------------------------
async def UpdateAppState(state: AppState, conversation_id: str):
    """
    Update the application state object with the latest data
    from conversations, tasks, and events.

    This keeps the UI synchronized with the backend Delegator state.
    """
    try:
        # Update conversation and message history
        if conversation_id:
            state.current_conversation_id = conversation_id
            messages = await ListMessages(conversation_id)
            state.messages = (
                [convert_message_to_state(x) for x in messages] if messages else []
            )

        # Update conversation list
        conversations = await ListConversations()
        state.conversations = (
            [convert_conversation_to_state(x) for x in conversations]
            if conversations
            else []
        )

        # Update task list
        state.task_list = [
            SessionTask(
                context_id=extract_conversation_id(task),
                task=convert_task_to_state(task),
            )
            for task in await GetTasks()
        ]

        # Update event list
        state.event_list = [convert_event_to_state(ev) for ev in await GetEvents()]

        # Pending background tasks
        state.background_tasks = await GetProcessingMessages()

        # Message alias mappings
        state.message_aliases = GetMessageAliases()

    except Exception as e:
        print("Failed to update state:", e)
        traceback.print_exc(file=sys.stdout)


async def UpdateApiKey(api_key: str):
    """
    Update the Google API key in both environment and Delegator backend.
    """
    import httpx

    try:
        os.environ["GOOGLE_API_KEY"] = api_key
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DELEGATOR_URL}/api_key/update", json={"api_key": api_key}
            )
            response.raise_for_status()
        return True
    except Exception as e:
        print("Failed to update API key:", e)
        return False


# -------------------------------------------------------------------
# Conversion Utilities
# -------------------------------------------------------------------
def convert_message_to_state(message: Message) -> StateMessage:
    """Convert a raw service Message into a StateMessage for UI use."""
    if not message:
        return StateMessage()

    return StateMessage(
        message_id=message.messageId,
        context_id=message.contextId or "",
        task_id=message.taskId or "",
        role=message.role.name,
        content=extract_content(message.parts),
    )


def convert_conversation_to_state(conversation: Conversation) -> StateConversation:
    """Convert a Conversation object into state representation."""
    return StateConversation(
        conversation_id=conversation.conversation_id,
        conversation_name=conversation.name,
        is_active=conversation.is_active,
        message_ids=[extract_message_id(x) for x in conversation.messages],
    )


def convert_task_to_state(task: Task) -> StateTask:
    """Convert a Task into StateTask, including artifacts and history."""
    output = (
        [extract_content(a.parts) for a in task.artifacts] if task.artifacts else []
    )

    if not task.history:
        return StateTask(
            task_id=task.id,
            context_id=task.contextId,
            state=TaskState.failed.name,
            message=StateMessage(
                message_id=str(uuid.uuid4()),
                context_id=task.contextId,
                task_id=task.id,
                role=Role.agent.name,
                content=[("No history", "text")],
            ),
            artifacts=output,
        )

    message = task.history[0]
    last_message = task.history[-1]
    if last_message != message:
        output = [extract_content(last_message.parts)] + output

    return StateTask(
        task_id=task.id,
        context_id=task.contextId,
        state=str(task.status.state),
        message=convert_message_to_state(message),
        artifacts=output,
    )


def convert_event_to_state(event: Event) -> StateEvent:
    """Convert an Event object into state representation."""
    return StateEvent(
        context_id=extract_message_conversation(event.content),
        actor=event.actor,
        role=event.content.role.name,
        id=event.id,
        content=extract_content(event.content.parts),
    )


def extract_content(message_parts: list[Part]) -> list[tuple[str | dict[str, Any], str]]:
    """
    Extract content from message parts into a list of (data, mime_type).
    Handles text, files, and JSON data.
    """
    parts: list[tuple[str | dict[str, Any], str]] = []
    if not message_parts:
        return []

    for part in message_parts:
        p = part.root
        if p.kind == "text":
            parts.append((p.text, "text/plain"))
        elif p.kind == "file":
            if isinstance(p.file, FileWithBytes):
                parts.append((p.file.bytes, p.file.mimeType or ""))
            else:
                parts.append((p.file.uri, p.file.mimeType or ""))
        elif p.kind == "data":
            try:
                json_data = json.dumps(p.data)
                if p.data.get("type") == "form":
                    parts.append((p.data, "form"))
                else:
                    parts.append((json_data, "application/json"))
            except Exception as e:
                print("Failed to dump data:", e)
                parts.append(("<data>", "text/plain"))
    return parts


def extract_message_id(message: Message) -> str:
    return message.messageId


def extract_message_conversation(message: Message) -> str:
    return message.contextId or ""


def extract_conversation_id(task: Task) -> str:
    """Get the conversation ID associated with a task, if any."""
    if task.contextId:
        return task.contextId
    if task.status.message:
        return task.status.message.contextId or ""
    return ""
