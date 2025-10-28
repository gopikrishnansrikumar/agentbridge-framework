import json
from typing import Any

import httpx
from service.types import (
    AgentClientHTTPError,
    AgentClientJSONError,
    CreateConversationRequest,
    CreateConversationResponse,
    GetEventRequest,
    GetEventResponse,
    JSONRPCRequest,
    ListAgentRequest,
    ListAgentResponse,
    ListConversationRequest,
    ListConversationResponse,
    ListMessageRequest,
    ListMessageResponse,
    ListTaskRequest,
    ListTaskResponse,
    PendingMessageRequest,
    PendingMessageResponse,
    RegisterAgentRequest,
    RegisterAgentResponse,
    SendMessageRequest,
    SendMessageResponse,
)


class ConversationClient:
    """
    ConversationClient provides a typed wrapper around the JSON-RPC API
    exposed by the ConversationServer.

    It handles serialization/deserialization of requests and responses,
    abstracts away raw HTTP calls, and ensures errors are reported in a
    consistent way.

    This client is used by the UI state management layer to interact with
    the backend in an asynchronous, non-blocking manner.
    """

    def __init__(self, base_url: str):
        """
        Initialize the client with the server base URL.
        The URL should point to the ConversationServer (e.g., http://localhost:12000).
        """
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Core request method
    # ------------------------------------------------------------------

    async def _send_request(self, request: JSONRPCRequest) -> dict[str, Any]:
        """
        Send a JSON-RPC request to the ConversationServer and return
        the decoded JSON response as a dictionary.

        Handles HTTP and JSON decode errors explicitly and raises
        domain-specific exceptions for clarity.
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url + "/" + request.method,
                    json=request.model_dump(mode="json", exclude_none=True),
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                print("http error", e)
                raise AgentClientHTTPError(e.response.status_code, str(e)) from e
            except json.JSONDecodeError as e:
                print("decode error", e)
                raise AgentClientJSONError(str(e)) from e

    # ------------------------------------------------------------------
    # High-level typed API methods
    # ------------------------------------------------------------------

    async def send_message(self, payload: SendMessageRequest) -> SendMessageResponse:
        """Send a message into a conversation and return its confirmation info."""
        return SendMessageResponse(**await self._send_request(payload))

    async def create_conversation(
        self, payload: CreateConversationRequest
    ) -> CreateConversationResponse:
        """Start a new conversation and return its details."""
        return CreateConversationResponse(**await self._send_request(payload))

    async def list_conversation(
        self, payload: ListConversationRequest
    ) -> ListConversationResponse:
        """Fetch the list of all active conversations."""
        return ListConversationResponse(**await self._send_request(payload))

    async def get_events(self, payload: GetEventRequest) -> GetEventResponse:
        """Fetch all events recorded so far (system + agent actions)."""
        return GetEventResponse(**await self._send_request(payload))

    async def list_messages(self, payload: ListMessageRequest) -> ListMessageResponse:
        """List all messages within a given conversation."""
        return ListMessageResponse(**await self._send_request(payload))

    async def get_pending_messages(
        self, payload: PendingMessageRequest
    ) -> PendingMessageResponse:
        """Get a mapping of messages still being processed."""
        return PendingMessageResponse(**await self._send_request(payload))

    async def list_tasks(self, payload: ListTaskRequest) -> ListTaskResponse:
        """List all tasks known to the system (submitted, active, or completed)."""
        return ListTaskResponse(**await self._send_request(payload))

    async def register_agent(
        self, payload: RegisterAgentRequest
    ) -> RegisterAgentResponse:
        """Register a new agent into the system by providing its base URL."""
        return RegisterAgentResponse(**await self._send_request(payload))

    async def list_agents(self, payload: ListAgentRequest) -> ListAgentResponse:
        """Return the list of agents currently registered."""
        return ListAgentResponse(**await self._send_request(payload))
