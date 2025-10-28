from typing import Callable

import httpx
from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    JSONRPCErrorResponse,
    Message,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)

# Type alias for callbacks that handle task updates from agents
TaskCallbackArg = Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent
TaskUpdateCallback = Callable[[TaskCallbackArg, AgentCard], Task]


class RemoteAgentConnections:
    """
    Maintains a connection to a single remote agent.

    Provides methods for sending messages to the agent, either in streaming
    mode (real-time task updates) or non-streaming mode (one-shot request/response).

    Attributes:
        agent_client: Underlying A2A client responsible for communication.
        card: Metadata describing the remote agent (capabilities, description, etc.).
        pending_tasks: Tracks task IDs currently in progress.
    """

    def __init__(self, client: httpx.AsyncClient, agent_card: AgentCard):
        self.agent_client = A2AClient(client, agent_card)
        self.card = agent_card
        self.pending_tasks = set()

    def get_agent(self) -> AgentCard:
        """Return the agent’s metadata card."""
        return self.card

    async def send_message(
        self,
        request: MessageSendParams,
        task_callback: TaskUpdateCallback | None,
    ) -> Task | Message | None:
        """
        Send a message or task request to the remote agent.

        Depending on the agent’s capabilities, this may use streaming mode 
        (incremental updates) or non-streaming mode.

        Args:
            request: The message/task request to send.
            task_callback: Optional callback for handling incremental task updates.

        Returns:
            - A `Message` if the agent replies directly with a message.
            - A `Task` if the agent executes a task.
            - An error object if the request fails.
        """
        if self.card.capabilities.streaming:
            task = None
            async for response in self.agent_client.send_message_streaming(
                SendStreamingMessageRequest(params=request)
            ):
                # --- FIX: check for error response first ---
                if isinstance(response.root, JSONRPCErrorResponse):
                    return response.root.error

                event = response.root.result

                # If the agent replies with a message, treat this as the end of interaction
                if isinstance(event, Message):
                    return event

                # Otherwise, handle task updates via the provided callback
                if task_callback and event:
                    task = task_callback(event, self.card)

                # If the event signals completion, exit the loop
                if hasattr(event, "final") and event.final:
                    break
            return task

        else:  # Non-streaming mode
            response = await self.agent_client.send_message(
                SendMessageRequest(params=request)
            )

            if isinstance(response.root, JSONRPCErrorResponse):
                return response.root.error

            if isinstance(response.root.result, Message):
                return response.root.result

            if task_callback:
                task_callback(response.root.result, self.card)

            return response.root.result
