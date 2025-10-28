import asyncio
import datetime
import uuid

from a2a.types import (
    AgentCard,
    Artifact,
    DataPart,
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)

# from service.server import test_image
from service.server.application_manager import ApplicationManager
from service.types import Conversation, Event
from utils.agent_card import get_agent_card


class InMemoryFakeAgentManager(ApplicationManager):
    """
    A minimal in-memory implementation of the ApplicationManager interface.

    This "fake" manager is useful for UI testing and demonstration purposes.
    It simulates conversations, tasks, and events without requiring a live
    backend or connected agents. Instead, it cycles through a set of
    pre-canned responses defined in `_message_queue`.
    """

    _conversations: list[Conversation]
    _messages: list[Message]
    _tasks: list[Task]
    _events: list[Event]
    _pending_message_ids: list[str]
    _next_message_idx: int
    _agents: list[AgentCard]

    def __init__(self):
        # In-memory state stores
        self._conversations = []
        self._messages = []
        self._tasks = []
        self._events = []
        self._pending_message_ids = []
        self._next_message_idx = 0  # controls which canned message is returned next
        self._agents = []
        self._task_map = {}

    # ---------------- Conversation and Message Handling ----------------

    def create_conversation(self) -> Conversation:
        """Start a new in-memory conversation and return it."""
        conversation_id = str(uuid.uuid4())
        c = Conversation(conversation_id=conversation_id, is_active=True)
        self._conversations.append(c)
        return c

    def sanitize_message(self, message: Message) -> Message:
        """
        Optionally attach a task ID to the message if the last message in
        the conversation was tied to an active (still open) task.
        """
        if message.contextId:
            conversation = self.get_conversation(message.contextId)
        if not conversation:
            return message

        if conversation.messages:
            last_task_id = conversation.messages[-1].taskId
            if last_task_id and task_still_open(
                next((x for x in self._tasks if x.id == last_task_id), None)
            ):
                message.taskId = last_task_id

        return message

    async def process_message(self, message: Message):
        """
        Process a user message:
          1. Append it to the message/event logs.
          2. Simulate a task submission.
          3. Wait a short delay (based on index).
          4. Return the next canned message from `_message_queue`.
        """
        self._messages.append(message)
        message_id = message.messageId
        context_id = message.contextId or ""
        task_id = message.taskId or ""

        if message_id:
            self._pending_message_ids.append(message_id)

        conversation = self.get_conversation(context_id)
        if conversation:
            conversation.messages.append(message)

        # Record the incoming message as an event
        self._events.append(
            Event(
                id=str(uuid.uuid4()),
                actor="host",
                content=message,
                timestamp=datetime.datetime.utcnow().timestamp(),
            )
        )

        # Simulate creating a task bound to this message
        task = Task(
            id=task_id,
            contextId=context_id,
            status=TaskStatus(state=TaskState.submitted, message=message),
            history=[message],
        )
        if self._next_message_idx != 0:
            self.add_task(task)

        # Simulate async processing
        await asyncio.sleep(self._next_message_idx)
        response = self.next_message()

        if conversation:
            conversation.messages.append(response)

        # Record the response as an event
        self._events.append(
            Event(
                id=str(uuid.uuid4()),
                actor="host",
                content=response,
                timestamp=datetime.datetime.utcnow().timestamp(),
            )
        )

        self._pending_message_ids.remove(message_id)

        # Mark the task as completed and attach the response as an artifact
        if task:
            task.status.state = TaskState.completed
            task.artifacts = [
                Artifact(
                    name="response",
                    parts=response.parts,
                    artifactId=str(uuid.uuid4()),
                )
            ]
            task.history.append(response)
            self.update_task(task)

    # ---------------- Task and Event Management ----------------

    def add_task(self, task: Task):
        """Add a new task to memory."""
        self._tasks.append(task)

    def update_task(self, task: Task):
        """Update an existing task in place."""
        for i, t in enumerate(self._tasks):
            if t.id == task.id:
                self._tasks[i] = task
                return

    def add_event(self, event: Event):
        """Append an event to the log."""
        self._events.append(event)

    def next_message(self) -> Message:
        """
        Return the next canned response from `_message_queue`.
        Cycles back to the beginning when the end is reached.
        """
        message = _message_queue[self._next_message_idx]
        self._next_message_idx = (self._next_message_idx + 1) % len(_message_queue)
        return message

    # ---------------- Queries ----------------

    def get_conversation(self, conversation_id: str | None) -> Conversation | None:
        """Retrieve a conversation by ID, or None if not found."""
        if not conversation_id:
            return None
        return next((c for c in self._conversations if c.conversation_id == conversation_id), None)

    def get_pending_messages(self) -> list[tuple[str, str]]:
        """
        Return the status of all pending messages.
        Each tuple = (message_id, short status string).
        """
        rval: list[tuple[str, str]] = []
        for message_id in self._pending_message_ids:
            if message_id in self._task_map:
                task_id = self._task_map[message_id]
                task = next((x for x in self._tasks if x.id == task_id), None)
                if not task:
                    rval.append((message_id, ""))
                elif task.history and task.history[-1].parts:
                    if len(task.history) == 1:
                        rval.append((message_id, "Working..."))
                    else:
                        part = task.history[-1].parts[0]
                        rval.append(
                            (
                                message_id,
                                part.root.text if part.root.kind == "text" else "Working...",
                            )
                        )
            else:
                rval.append((message_id, ""))
            return rval
        return [(x, "") for x in self._pending_message_ids]

    def register_agent(self, url):
        """Register a fake agent by loading its card and storing it in memory."""
        agent_data = get_agent_card(url)
        if not agent_data.url:
            agent_data.url = url
        self._agents.append(agent_data)

    # ---------------- Properties ----------------

    @property
    def agents(self) -> list[AgentCard]:
        return self._agents

    @property
    def conversations(self) -> list[Conversation]:
        return self._conversations

    @property
    def tasks(self) -> list[Task]:
        return self._tasks

    @property
    def events(self) -> list[Event]:
        # For simplicity, return an empty list here
        return []


# -------------------------------------------------------------------
# Global conversation ID used for the canned message queue
# -------------------------------------------------------------------
_contextId = str(uuid.uuid4())

# Predefined fake agent responses.
# These cycle in order whenever process_message() is called.
_message_queue: list[Message] = [
    Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text="Hello"))],
        contextId=_contextId,
        messageId=str(uuid.uuid4()),
    ),
    Message(
        role=Role.agent,
        parts=[
            Part(
                root=DataPart(
                    data={
                        "type": "form",
                        "form": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Enter your name",
                                    "title": "Name",
                                },
                                "date": {
                                    "type": "string",
                                    "format": "date",
                                    "description": "Birthday",
                                    "title": "Birthday",
                                },
                            },
                            "required": ["date"],
                        },
                        "form_data": {
                            "name": "John Smith",
                        },
                        "instructions": "Please provide your birthday and name",
                    }
                )
            ),
        ],
        contextId=_contextId,
        messageId=str(uuid.uuid4()),
    ),
    Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text="I like cats"))],
        contextId=_contextId,
        messageId=str(uuid.uuid4()),
    ),
    # test_image.make_test_image(_contextId),  # Example of extending with image messages
    Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text="And I like dogs"))],
        contextId=_contextId,
        messageId=str(uuid.uuid4()),
    ),
]
