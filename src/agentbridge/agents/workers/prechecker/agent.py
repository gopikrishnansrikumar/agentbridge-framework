"""
Prechecker Agent.

This agent validates MuJoCo MJCF XML files before they are passed further down
the robotics multi-agent pipeline. It provides early detection of malformed XML,
structural inconsistencies, and semantic issues.

Responsibilities:
  - Perform schema and structural validation (via `validate_mjcf_file`).
  - Conduct deeper semantic analysis by reading the file content.
  - Differentiate between minor issues (warnings) and major errors (blocking).
  - Produce a Markdown validation report summarizing findings.
  - Return structured responses with explicit `response_status`.

Integration:
  - Built on top of LangGraph's `create_react_agent`.
  - Uses external MCP tools to read and validate MJCF files.
  - Returns streaming updates for transparency and debugging.
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

# In-memory checkpointing for conversation state
memory = MemorySaver()


class ResponseFormat(BaseModel):
    """
    Defines the expected response structure for the Prechecker Agent.

    Attributes:
        status: One of ["input_required", "completed", "error"]
        message: Human-readable message or validation summary
    """
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


# ---- Provider / Model utilities ----
def _get_provider() -> str:
    """Return the configured LLM provider (default: Google)."""
    return os.getenv("PRECHECKER_PROVIDER", "Google").strip()


def _get_model(
    default_google="gemini-2.5-flash",
    default_groq="llama3-70b",
    default_openai="gpt-4.1-mini",
) -> str:
    """
    Resolve the model name from environment or provider defaults.
    """
    override = os.getenv("PRECHECKER_MODEL")
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
        raise RuntimeError(f"Unsupported PRECHECKER_PROVIDER: {provider}")


def _build_llm():
    """
    Instantiate the appropriate LLM client based on provider and API key.
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
        raise RuntimeError(f"Unsupported PRECHECKER_PROVIDER: {provider}")


def _mcp_config() -> dict:
    """Return configuration for the MCP (tooling) client."""
    return {
        "mcp_tools": {
            "url": os.getenv("MCP_URL", "http://localhost:8000/sse"),
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
        }
    }


class PrecheckerAgent:
    """
    The Prechecker Agent validates MJCF files before they enter the main workflow.

    Workflow:
      1. Run schema/structural validation (via `validate_mjcf_file`).
      2. If errors are present:
         - Minor issues → log as warnings, continue.
         - Major errors → stop execution, set status="error".
      3. If structural checks pass, perform semantic analysis using `read_mjcf_file`.
      4. Return a Markdown validation report with findings.
      5. Signal completion or request further input as needed.
    """

    # Instruction prompt given to the LLM
    SYSTEM_INSTRUCTION = (
        "You are a robotics simulation validation agent called the Prechecker Agent. "
        "Your role is to perform two-stage validation on MuJoCo MJCF XML files before they enter the pipeline.\n"
        "You think step-by-step always.\n"
        "\n"
        "Your Tasks step-by-step:\n"
        "1. Use tool `validate_mjcf_file` to run schema and structural validation checks and obtain a detailed validation report (Markdown string).\n"
        "2. If errors are found:\n"
        "   - Minor issues (e.g., formatting) → include them but allow file to proceed.\n"
        "   - Major errors (e.g., malformed XML, invalid geom types) → stop, set status='error', request corrected file.\n"
        "3. If no blocking errors, perform semantic self-analysis by reading the file (`read_mjcf_file`).\n"
        "   - Identify deeper issues (duplicate names, invalid attributes).\n"
        "   - Treat major problems as fatal errors; minor ones as warnings.\n"
        "4. Return a Markdown validation report containing all findings.\n"
        "5. Set status='completed' once the validation report is delivered.\n"
        "\n"
        "Rules:\n"
        "- Only accept MJCF file paths, never raw XML content.\n"
        "- Do not output file contents, only structured validation reports.\n"
        "- Handle one task at a time.\n"
        "- Politely decline unrelated requests.\n"
    )

    def __init__(self):
        """Initialize the agent with the chosen LLM backend."""
        self.model = _build_llm()
        self.graph = None

    async def invoke(self, query, sessionId) -> Dict[str, Any]:
        """
        Invoke the PrecheckerAgent in one-shot (non-streaming) mode.

        Args:
            query: User task description or file path.
            sessionId: Unique identifier for the session.

        Returns:
            Structured response containing validation results.
        """
        client = MultiServerMCPClient(_mcp_config())
        tools = await client.get_tools()

        # Build the reactive agent graph
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
        Stream PrecheckerAgent outputs step-by-step.

        Args:
            query: User query or MJCF file path.
            sessionId: Thread/session identifier.

        Yields:
            Dict messages containing progress updates, tool calls, tool responses,
            and final structured output.
        """
        inputs = {"messages": [("user", query)]}
        config = {"configurable": {"thread_id": sessionId}}

        client = MultiServerMCPClient(_mcp_config())
        tools = await client.get_tools()

        # Create agent graph for streaming
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

            if isinstance(message, AIMessage):
                # Stream intermediate model thoughts
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
                # Stream tool calls
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

            elif isinstance(message, ToolMessage):
                # Stream tool responses
                tool_resp = f"Tool **{message.name}** response: {message.content}"
                if tool_resp not in seen_contents:
                    seen_contents.add(tool_resp)
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": tool_resp,
                        "type": "tool_response",
                    }

        # Yield the final structured response
        final = self.get_agent_response(config)
        if final.get("content") and final["content"] not in seen_contents:
            final["type"] = "final"
            yield final

    def get_agent_response(self, config):
        """
        Retrieve the final structured response from the agent state.
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
        # Fallback response
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    # Supported input/output content types for this agent
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
