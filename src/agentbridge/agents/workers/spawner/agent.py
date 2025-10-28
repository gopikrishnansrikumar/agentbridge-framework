"""
Spawner Agent.

This module defines the `SpawnerAgent`, responsible for modifying world files
(SDF or URDF) by spawning new objects at specified coordinates. It integrates
with LangChain + LangGraph to enable reasoning, planning, and tool use in a
robotics simulation context.

The SpawnerAgent:
  - Accepts SDF/URDF file paths as input.
  - Reads the file using the appropriate tool.
  - Updates the file by inserting objects into the world model.
  - Returns updated artifacts, while tracking status (input required, error, or completed).
"""

import os
from collections.abc import AsyncIterable
from typing import Any, Dict, Literal

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel

# In-memory checkpointing for LangGraph (conversation state persistence)
memory = MemorySaver()


class ResponseFormat(BaseModel):
    """Schema for agent responses (ensures structured output)."""

    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


# -----------------------------
# LLM Provider + Model Selection
# -----------------------------

def _get_provider() -> str:
    """Read the LLM provider (Google, Groq, OpenAI) from environment variables."""
    return os.getenv("SPAWNER_PROVIDER", "Google").strip()


def _get_model(
    default_google="gemini-2.5-flash",
    default_groq="llama3-70b",
    default_openai="gpt-4.1-mini",
) -> str:
    """Choose the model name for the selected provider, with defaults per backend."""
    override = os.getenv("SPAWNER_MODEL")
    if override:
        return override.strip()

    provider = _get_provider().lower()
    if provider == "google":
        return default_google
    elif provider == "groq":
        return default_groq
    elif provider == "openai":
        return default_openai
    else:
        raise RuntimeError(f"Unsupported SPAWNER_PROVIDER: {provider}")


def _build_llm():
    """Construct the appropriate chat model instance (Google, Groq, or OpenAI)."""
    provider = _get_provider().lower()
    model = _get_model()

    if provider == "google":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        return ChatGoogleGenerativeAI(model=model, temperature=0, google_api_key=api_key)

    elif provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set")
        return ChatGroq(model=model, temperature=0, groq_api_key=api_key)

    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        return ChatOpenAI(model=model, temperature=0, api_key=api_key)

    else:
        raise RuntimeError(f"Unsupported SPAWNER_PROVIDER: {provider}")


def _mcp_config() -> dict:
    """Configuration for accessing MCP tools (e.g., file readers and updaters)."""
    return {
        "mcp_tools": {
            "url": os.getenv("MCP_URL", "http://localhost:8000/sse"),
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
        }
    }


# -----------------------------
# SpawnerAgent Implementation
# -----------------------------

class SpawnerAgent:
    """
    The Spawner Agent modifies SDF/URDF world files by inserting objects.

    SYSTEM_INSTRUCTION guides the reasoning process, including:
      - When to require input (e.g., missing file path).
      - Which tools to call (read/update SDF or URDF).
      - Status updates (input_required, completed, error).
    """

    SYSTEM_INSTRUCTION = (
        "You take an SDF (.sdf) or URDF (.urdf) world file path as input and "
        "add a specified object at the provided coordinates to the world file.\n\n"
        "Workflow:\n"
        "1) Retrieve the user-provided SDF/URDF file path.\n"
        "2) Determine if the file is SDF or URDF.\n"
        "3) Use the correct tool to read the file (`read_sdf_file` or `read_urdf_file`).\n"
        "4) Insert the new object and update the file using the appropriate tool "
        "(`update_sdf_file` or `update_urdf_file`).\n\n"
        "Status guidelines:\n"
        "- Use 'input_required' if no file path is provided.\n"
        "- Use 'completed' after successfully saving the updated file.\n"
        "- Use 'error' if changes cannot be applied.\n\n"
        "Interaction rules:\n"
        "- Only handle spawning tasks for SDF/URDF files.\n"
        "- Politely decline unrelated requests.\n"
    )

    def __init__(self):
        self.model = _build_llm()
        self.graph = None  # initialized per request

    # -----------------------------
    # Agent Invocation
    # -----------------------------

    async def invoke(self, query, sessionId) -> Dict[str, Any]:
        """
        Synchronous invocation of the agent (one-shot request).

        Args:
            query: User-provided text query.
            sessionId: Identifier for conversation/thread state.

        Returns:
            Structured agent response (dict).
        """
        client = MultiServerMCPClient(_mcp_config())
        tools = await client.get_tools()

        # Build a reasoning agent with the system prompt + tools
        self.graph = create_react_agent(
            self.model,
            tools=tools,
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat,
        )

        config: RunnableConfig = {"configurable": {"thread_id": sessionId}}
        await self.graph.ainvoke({"messages": [("user", query)]}, config)
        return self.get_agent_response(config)

    async def stream(self, query, sessionId) -> AsyncIterable[Dict[str, Any]]:
        """
        Stream agent responses step-by-step (thoughts, tool calls, tool responses).

        Args:
            query: User query string.
            sessionId: Conversation/thread identifier.

        Yields:
            Dict containing structured agent updates (thoughts, tool calls, final results).
        """
        inputs = {"messages": [("user", query)]}
        config = {"configurable": {"thread_id": sessionId}}

        client = MultiServerMCPClient(_mcp_config())
        tools = await client.get_tools()

        self.graph = create_react_agent(
            self.model,
            tools=tools,
            checkpointer=memory,
            prompt=self.SYSTEM_INSTRUCTION,
            response_format=ResponseFormat,
        )

        seen_contents = set()  # prevent duplicate outputs

        # Process agent messages as they stream in
        async for item in self.graph.astream(inputs, config, stream_mode="values"):
            message = item["messages"][-1]

            if isinstance(message, AIMessage):
                # Intermediate agent reasoning/thoughts
                if (
                    message.content
                    and message.content.strip()
                    and message.content not in seen_contents
                ):
                    seen_contents.add(message.content)
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message.content.strip(),
                        "type": "agent_thought",
                    }

                # Tool call events
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        args_str = (
                            tool_call["args"]
                            if isinstance(tool_call["args"], str)
                            else str(tool_call["args"])
                        )
                        tool_msg = f"Using tool **{tool_call['name']}** with: `{args_str}`"
                        if tool_msg not in seen_contents:
                            seen_contents.add(tool_msg)
                            yield {
                                "is_task_complete": False,
                                "require_user_input": False,
                                "content": tool_msg,
                                "type": "tool_call",
                            }

            elif isinstance(message, ToolMessage):
                # Responses returned by external tools
                tool_resp = f"Tool **{message.name}** response: {message.content}"
                if tool_resp not in seen_contents:
                    seen_contents.add(tool_resp)
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": tool_resp,
                        "type": "tool_response",
                    }

        # Final structured response
        final = self.get_agent_response(config)
        final_content = final.get("content")
        if final_content and final_content not in seen_contents:
            final["type"] = "final"
            seen_contents.add(final_content)
            yield final

    # -----------------------------
    # Structured Response Retrieval
    # -----------------------------

    def get_agent_response(self, config):
        """
        Retrieve the structured response from the current graph state.

        Returns:
            dict: Containing task completion status, user input requirements, and message.
        """
        current_state = self.graph.get_state(config)
        structured_response = current_state.values.get("structured_response")

        if structured_response and isinstance(structured_response, ResponseFormat):
            if structured_response.status == "input_required":
                return {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "content": structured_response.message,
                }
            if structured_response.status == "error":
                return {
                    "is_task_complete": False,
                    "require_user_input": True,
                    "content": structured_response.message,
                }
            if structured_response.status == "completed":
                return {
                    "is_task_complete": True,
                    "require_user_input": False,
                    "content": structured_response.message,
                }

        # Default fallback response
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    # Supported content types for input/output
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
