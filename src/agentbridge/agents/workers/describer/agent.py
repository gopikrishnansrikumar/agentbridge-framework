"""
DescriberAgent

This agent is responsible for analyzing MuJoCo MJCF XML files and producing
two complementary outputs:
  1. A **natural language description** (.txt) suitable for human understanding.
  2. A **structured JSON description** (.json) capturing the file contents for reconstruction.

The agent is orchestrated using LangGraph's ReAct agent pattern with tool access.
It integrates with MCP (Model Context Protocol) tools for reading MJCF files
and saving generated descriptions. The design enforces academic principles of
reliability, reproducibility, and separation of concerns.
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

# In-memory checkpointing for conversation context
memory = MemorySaver()


class ResponseFormat(BaseModel):
    """
    Standardized schema for agent responses.

    Attributes:
        status: One of ["input_required", "completed", "error"].
        message: Human-readable message or instruction.
    """
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


# ---------------------------------------------------------------------------
# Provider and model configuration
# ---------------------------------------------------------------------------

def _get_provider() -> str:
    """Return the LLM provider name (Google, Groq, OpenAI)."""
    return os.getenv("DESCRIBER_PROVIDER", "Google").strip()


def _get_model(
    default_google="gemini-2.5-flash",
    default_groq="llama3-70b",
    default_openai="gpt-4.1-mini",
) -> str:
    """
    Select an appropriate LLM model, either from override in env or sensible defaults.
    """
    override = os.getenv("DESCRIBER_MODEL")
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
        raise RuntimeError(f"Unsupported DESCRIBER_PROVIDER: {provider}")


def _build_llm():
    """
    Build an LLM client for the chosen provider.

    Raises:
        RuntimeError: if required API key is missing or provider unsupported.
    """
    provider = _get_provider().lower()
    model = _get_model()

    if provider == "google":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        return ChatGoogleGenerativeAI(
            model=model, temperature=0, google_api_key=api_key
        )

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
        raise RuntimeError(f"Unsupported DESCRIBER_PROVIDER: {provider}")


def _mcp_config() -> dict:
    """
    Configuration for MCP (Model Context Protocol) client.
    Defines where to fetch tools (e.g., reading/saving files).
    """
    return {
        "mcp_tools": {
            "url": os.getenv("MCP_URL", "http://localhost:8000/sse"),
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
        }
    }


# ---------------------------------------------------------------------------
# Agent Definition
# ---------------------------------------------------------------------------

class DescriberAgent:
    """
    Agent that reads MJCF files and produces dual outputs: JSON + natural language.

    The SYSTEM_INSTRUCTION guides the LLM's reasoning and constrains tool usage.
    """

    SYSTEM_INSTRUCTION = (
        "You are a robotics simulation analyst who describes MuJoCo MJCF XML files "
        "and saves them to both .txt and .json files.\n"
        "\n"
        "Guidelines:\n"
        "- Always think step by step.\n"
        "- Text description: detailed, accurate, with a visual summary.\n"
        "- JSON description: precise, structured, capturing geometry, positions, and colors.\n"
        "\n"
        "Execution Steps:\n"
        "1. Use tool `read_mjcf_file(path)` to read the file.\n"
        "2. Generate a structured JSON description.\n"
        "3. Save JSON using `save_description_JSON` → data/description/description.json.\n"
        "4. Return the JSON path and confirm save.\n"
        "5. Generate a detailed natural language description.\n"
        "6. Save text using `save_description_NL` → data/description/description.txt.\n"
        "7. Return the text path and confirm save.\n"
        "8. After both saves, mark `response_status='completed'`.\n"
        "\n"
        "Rules:\n"
        "- Accept only MJCF file paths (never file content).\n"
        "- Never reveal file contents, only file paths.\n"
        "- Only one task at a time. If interrupted, politely defer.\n"
        "- On parse error: mark `response_status='error'`.\n"
        "- If no file path given: mark `response_status='input_required'`.\n"
        "\n"
        "Example:\n"
        "INPUT: 'Describe this MJCF file: path/to/file.xml'\n"
        "OUTPUT: {'response_status': 'completed', 'message': 'Descriptions saved to data/description/...'}"
    )

    def __init__(self):
        self.model = _build_llm()
        self.graph = None

    async def invoke(self, query, sessionId) -> Dict[str, Any]:
        """
        Single-turn execution of the agent.

        Args:
            query: User query (e.g., file path).
            sessionId: Unique identifier for the task/session.

        Returns:
            Structured agent response as a dictionary.
        """
        client = MultiServerMCPClient(_mcp_config())
        tools = await client.get_tools()

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
        Stream intermediate reasoning steps, tool calls, and tool responses,
        along with the final structured result at the end.
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

        seen_contents = set()
        async for item in self.graph.astream(inputs, config, stream_mode="values"):
            message = item["messages"][-1]

            # Capture agent thoughts (internal reasoning exposed as text)
            if isinstance(message, AIMessage):
                # Ensure content is a string before processing
                content_text = ""
                if isinstance(message.content, list):
                    # If content is a list, join its parts into a single string
                    content_text = "".join(str(part) for part in message.content)
                elif isinstance(message.content, str):
                    # If content is already a string, use it directly
                    content_text = message.content
                
                # Now, safely check and process the string version
                if (
                    content_text
                    and content_text.strip()
                    and content_text not in seen_contents
                ):
                    seen_contents.add(content_text)
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": content_text.strip(), # This is now safe
                        "type": "agent_thought",
                    }
                # Capture when the agent decides to call a tool
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        args_str = (
                            tool_call["args"]
                            if isinstance(tool_call["args"], str)
                            else str(tool_call["args"])
                        )
                        tool_msg = (
                            f"Using tool **{tool_call['name']}** with: `{args_str}`"
                        )
                        if tool_msg not in seen_contents:
                            seen_contents.add(tool_msg)
                            yield {
                                "is_task_complete": False,
                                "require_user_input": False,
                                "content": tool_msg,
                                "type": "tool_call",
                            }

            # Capture responses returned from tools
            elif isinstance(message, ToolMessage):
                tool_resp = f"Tool **{message.name}** response: {message.content}"
                if tool_resp not in seen_contents:
                    seen_contents.add(tool_resp)
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": tool_resp,
                        "type": "tool_response",
                    }

        # Yield the final structured response once available
        final = self.get_agent_response(config)
        final_content = final.get("content")
        if final_content and final_content not in seen_contents:
            final["type"] = "final"
            seen_contents.add(final_content)
            yield final

    def get_agent_response(self, config):
        """
        Retrieve the structured response from agent state.

        Returns:
            Dict indicating completion, input requirement, or error.
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

        # Fallback if no structured response is available
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    # Content types the agent supports by default
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
