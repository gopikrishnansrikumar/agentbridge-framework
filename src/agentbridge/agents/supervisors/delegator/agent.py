import asyncio
import base64
import json
import os
import uuid

import httpx
from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    DataPart,
    Message,
    MessageSendConfiguration,
    MessageSendParams,
    Part,
    Task,
    TaskState,
    TextPart,
    JSONRPCError
)
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from .remote_agent_connection import RemoteAgentConnections, TaskUpdateCallback

load_dotenv()

from langsmith.integrations.otel import configure

# Configure observability for LangSmith tracing/monitoring
configure(project_name=os.getenv("LANGCHAIN_PROJECT", "delegator"))


def _get_model_name():
    """Return the model name based on environment variables."""
    provider = (os.getenv("PROVIDER") or "google").lower()
    return os.getenv("MODEL_NAME") or (
        "gemini-2.5-pro"
        if provider == "google"
        else "llama-3.3-70b-versatile" if provider == "groq" else "gpt-4.1-mini"
    )


class HostAgent:
    """
    The HostAgent coordinates communication with multiple remote agents.

    Responsibilities:
    - Register and keep track of available remote agents.
    - Provide the delegator agent (root agent) with the ability to query agents, 
      greet them, and delegate tasks.
    - Manage session and task state across conversations.
    """

    def __init__(
        self,
        remote_agent_addresses: list[str],
        http_client: httpx.AsyncClient,
        task_callback: TaskUpdateCallback | None = None,
    ):
        self.task_callback = task_callback
        self.httpx_client = http_client
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}

        # Initialize all provided remote agents by resolving their AgentCard
        for address in remote_agent_addresses:
            card_resolver = A2ACardResolver(http_client, address)
            card = card_resolver.get_agent_card()
            remote_connection = RemoteAgentConnections(http_client, card)
            self.remote_agent_connections[card.name] = remote_connection
            self.cards[card.name] = card

        # Store agent metadata for inclusion in delegator instructions
        agent_info = []
        for ra in self.list_remote_agents():
            agent_info.append(json.dumps(ra))
        self.agents = "\n".join(agent_info)

    def register_agent_card(self, card: AgentCard):
        """Register a new agent dynamically and update internal lists."""
        remote_connection = RemoteAgentConnections(self.httpx_client, card)
        self.remote_agent_connections[card.name] = remote_connection
        self.cards[card.name] = card

        agent_info = []
        for ra in self.list_remote_agents():
            agent_info.append(json.dumps(ra))
        self.agents = "\n".join(agent_info)

    def create_agent(self) -> Agent:
        """
        Create and return the delegator agent. 
        This agent is the "root" that orchestrates which remote agents handle tasks.
        """
        return Agent(
            model=_get_model_name(),
            name="Delegator",
            instruction=self.root_instruction,
            before_model_callback=self.before_model_callback,
            description=(
                "This agent orchestrates the decomposition of the user request into "
                "tasks that can be performed by the child agents."
            ),
            tools=[
                self.list_remote_agents,
                self.send_message,
                self.greet_agents,
            ],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        """
        Instruction text provided to the delegator agent at runtime.
        This guides how it should interact with remote agents and the user.
        """
        current_agent = self.check_state(context)
        return f"""You are an expert delegator responsible for sending user requests to the appropriate remote agents.

        Discovery:
        - Use `list_remote_agents` to list available remote agents with names and descriptions.
        - Display the list to the user clearly (no markdown formatting).
        - Use `greet_agents` to ping all agents if the user requests it.

        Execution:
        - Use `send_message` to delegate tasks to remote agents.
        - When the user outlines a multi-step plan, internally check what agents you have available and suggest changes to the plan if necessary (for example: You see that the Debugger Agent can also be useful in the workflow to validate the SDF file. In such cases you can suggest the user to include this agent to the plan). Once a proper plan is decided, inform the orchestartor that you are ready to proceed.
        - Ask the user for a complete step-by-step plan before executing tasks with remote agents.
        - If the user gives a task while one task is ongoing politely tell the user to wait till the current task finishes.
        - If the user asks for a task to be resent because it is not visible in the 'Recent Tasks' list, resend the task to the same remote agent.
        - If a worker agent is yet to finish its task and the user sends a new task, inform the user to wait till the current task finishes.
        - After sending a task to a remote agent, give it some time to respond before checking for updates and inform the user about the delay. 
        - If a remote agent reports an error reading a file path or similar, ask the user to provide the correct path but never handle file contents directly or ask the user to do so.
        - If a remote agent ends it execution with an error reinitiate the task and inform the user about this i.e. every remote agent can retry if it runs into some error during its execution.
        Be sure to include the remote agent name when you respond to the user.

        Caching:
        - Keep track of completed tasks and their outputs as file paths and executions results. If a user repeats the same request, return the cached result unless the user wants to re-run it.

        Focus:
        - Use tools and remote agents to execute tasks only. Do not fabricate results.
        - If unclear, ask the user for more details.
        - Do not plan complex workflows; only handle one remote agent task at a time.

        **VERY IMPORTANT**:
        - ONLY ONE WORKER AGENT CAN EXECUTE AT A TIME. So before sending a task to a remote agent, wait for the current task to finish before sending a new task to the same or another remote agent.
        - NOTE: Some agents like the Tester and Debugger agents can have iterations loops upto 3 cycles. You must wait for these agents to finish their entire execution before sending a new task to any agent.
        - IMPORTANT: However, if the user asks you to resend a task 2 times, saying that it is stuck, you must resend the task to the same remote agent.

        Include the remote agent name in all responses to the user.
        
        Agents:
        {self.agents}

        Current agent: {current_agent['active_agent']}
        """

    def check_state(self, context: ReadonlyContext):
        """Check and return the currently active agent from state."""
        state = context.state
        if (
            "context_id" in state
            and "session_active" in state
            and state["session_active"]
            and "agent" in state
        ):
            return {"active_agent": f'{state["agent"]}'}
        return {"active_agent": "None"}

    def before_model_callback(self, callback_context: CallbackContext, llm_request):
        """Ensure session state is active before the model runs."""
        state = callback_context.state
        if "session_active" not in state or not state["session_active"]:
            state["session_active"] = True

    def list_remote_agents(self):
        """List all available remote agents by name and description."""
        if not self.remote_agent_connections:
            return "No agents are currently available."

        lines = []
        for card in self.cards.values():
            lines.append(f"{card.name}: {card.description}")
        return "\n".join(lines)

    async def greet_agents(self, tool_context: ToolContext):
        """Send a greeting ('Hello') to all remote agents and collect responses."""

        async def greet(agent_name):
            try:
                response = await self.send_message(agent_name, "Hello", tool_context)
                if isinstance(response, list):
                    resp_str = " ".join(str(r) for r in response)
                else:
                    resp_str = str(response)
                return f"{agent_name}: {resp_str}"
            except Exception as e:
                return f"{agent_name}: ERROR: {str(e)}"

        tasks = [
            greet(agent_name) for agent_name in self.remote_agent_connections.keys()
        ]
        responses = await asyncio.gather(*tasks)
        return responses

    async def send_message(
        self, agent_name: str, message: str, tool_context: ToolContext
    ):
        """
        Send a task to a specific remote agent.

        This function manages session state (task IDs, context IDs, etc.),
        builds the message payload, and handles the agent’s response.

        Args:
            agent_name: Remote agent to send the message to.
            message: Text of the user request or task.
            tool_context: Execution context for the tool.

        Returns:
            A list of results (strings, data parts, etc.) depending on agent output.
        """
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")

        state = tool_context.state
        state["agent"] = agent_name
        client = self.remote_agent_connections[agent_name]

        if not client:
            raise ValueError(f"Client not available for {agent_name}")

        taskId = state.get("task_id", None)
        contextId = state.get("context_id", None)
        messageId = state.get("message_id", None)

        if not messageId:
            messageId = str(uuid.uuid4())

        request: MessageSendParams = MessageSendParams(
            id=str(uuid.uuid4()),
            message=Message(
                role="user",
                parts=[TextPart(text=message)],
                messageId=messageId,
                contextId=contextId,
                taskId=taskId,
            ),
            configuration=MessageSendConfiguration(
                acceptedOutputModes=["text", "text/plain", "image/png"],
            ),
        )

        response = await client.send_message(request, self.task_callback)

        # --- I ADDED THIS ENTIRE BLOCK ---
        # Check if the response is a JSONRPCError and handle it before proceeding.
        if isinstance(response, JSONRPCError):
            error_message = f"Agent '{agent_name}' returned an error: {response.message} (Code: {response.code})"
            state["session_active"] = False
            # Raising a ValueError will report the failure back to the agent framework.
            raise ValueError(error_message)
        # --- END OF ADDED BLOCK ---

        # Some agents may return a message directly instead of a task.
        if isinstance(response, Message):
            # Minor bug fix: Changed 'task.parts' to 'response.parts'
            return await convert_parts(response.parts, tool_context)

        task: Task = response

        # Update session status based on task state
        state["session_active"] = task.status.state not in [
            TaskState.completed,
            TaskState.canceled,
            TaskState.failed,
            TaskState.unknown,
        ]

        if task.contextId:
            state["context_id"] = task.contextId
        state["task_id"] = task.id

        # Handle specific task states
        if task.status.state == TaskState.input_required:
            tool_context.actions.skip_summarization = True
            tool_context.actions.escalate = True
        elif task.status.state == TaskState.canceled:
            raise ValueError(f"Agent {agent_name} task {task.id} is cancelled")
        elif task.status.state == TaskState.failed:
            raise ValueError(f"Agent {agent_name} task {task.id} failed")

        # Collect outputs from task status messages and artifacts
        response = []
        if task.status.message:
            response.extend(await convert_parts(task.status.message.parts, tool_context))
        if task.artifacts:
            for artifact in task.artifacts:
                response.extend(await convert_parts(artifact.parts, tool_context))

        return response


async def convert_parts(parts: list[Part], tool_context: ToolContext):
    """Convert a list of A2A parts into usable output values."""
    rval = []
    for p in parts:
        rval.append(await convert_part(p, tool_context))
    return rval


async def convert_part(part: Part, tool_context: ToolContext):
    """Convert a single A2A part into text, data, or file representation."""
    if part.root.kind == "text":
        return part.root.text
    elif part.root.kind == "data":
        return part.root.data
    elif part.root.kind == "file":
        # Convert file parts into Google GenAI Blob format and save as artifact
        file_id = part.root.file.name
        file_bytes = base64.b64decode(part.root.file.bytes)
        file_part = types.Part(
            inline_data=types.Blob(mime_type=part.root.file.mimeType, data=file_bytes)
        )
        tool_context.save_artifact(file_id, file_part)
        tool_context.actions.skip_summarization = True
        tool_context.actions.escalate = True
        return DataPart(data={"artifact-file-id": file_id})
    return f"Unknown type: {part.kind}"
