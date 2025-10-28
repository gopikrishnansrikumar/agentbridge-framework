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

# Shared memory for conversation state (LangGraph checkpointer)
memory = MemorySaver()


class ResponseFormat(BaseModel):
    """
    Defines the structured response schema for the DebuggerAgent.

    Attributes:
        status: One of "input_required", "completed", or "error".
        message: A natural language explanation or result.
    """
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


# -------------------------------------------------------------------
# Provider / model selection
# -------------------------------------------------------------------

def _provider() -> str:
    """Read the active LLM provider (Google, Groq, OpenAI) from env."""
    return os.getenv("DEBUGGER_PROVIDER", "Google").strip()


def _model() -> str:
    """
    Determine which model to use.

    Priority:
      1. DEBUGGER_MODEL (explicit override)
      2. Sensible defaults based on provider.
    """
    override = os.getenv("DEBUGGER_MODEL")
    if override:
        return override.strip()

    if _provider().lower() == "google":
        return "gemini-2.5-flash"
    elif _provider().lower() == "groq":
        return "llama3-70b"
    elif _provider().lower() == "openai":
        return "gpt-4.1-mini"  # default for OpenAI
    else:
        raise RuntimeError(f"Unsupported DEBUGGER_PROVIDER: {_provider()}")


def _build_llm():
    """
    Construct a LangChain chat model instance for the selected provider.
    Requires the correct API key to be present in the environment.
    """
    prov = _provider().lower()
    model = _model()

    if prov == "google":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set for Google provider")
        return ChatGoogleGenerativeAI(model=model, temperature=0, google_api_key=api_key)

    elif prov == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set for Groq provider")
        return ChatGroq(model=model, temperature=0, groq_api_key=api_key)

    elif prov == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set for OpenAI provider")
        return ChatOpenAI(model=model, temperature=0, api_key=api_key)

    else:
        raise RuntimeError(f"Unsupported DEBUGGER_PROVIDER: {prov}")


def _mcp_config() -> dict:
    """
    Build MCP client configuration.

    Defaults:
      - URL: http://localhost:8000/sse
      - Transport: SSE
    """
    return {
        "mcp_tools": {
            "url": os.getenv("MCP_URL", "http://localhost:8000/sse"),
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
        }
    }


# -------------------------------------------------------------------
# Debugger Agent
# -------------------------------------------------------------------

class DebuggerAgent:
    """
    The DebuggerAgent encapsulates logic for validating SDF/URDF files
    by running Gazebo simulations and applying targeted fixes.

    Key behaviors:
      - Runs Gazebo with given file.
      - If errors occur, applies inferred fixes and retries.
      - Stops after max 3 attempts or success.
      - Returns a structured response (ResponseFormat).

    Restrictions:
      - Only accepts file paths (never file contents).
      - Only processes one task at a time.
      - Politely declines unrelated tasks.
    """

    SYSTEM_INSTRUCTION = (
        "You run Gazebo simulations with SDF/URDF files and apply targeted fixes based on runtime errors.\n"
        "Inputs required:\n"
        "- A valid SDF or URDF file path.\n\n"
        "PROCESS:\n"
        "1) Launch Gazebo with the file.\n"
        "2) If errors occur, infer fixes from terminal output and apply them.\n"
        "3) Repeat up to 3 iterations or until the run succeeds.\n"
        "4) On success, copy the final working file to the MJCF directory.\n\n"
        "ERROR HANDLING:\n"
        "- If XML is invalid, stop and return an error message.\n"
        "- If file path is missing, set response_status='input_required'.\n"
        "- Set response_status='completed' if simulation succeeds.\n"
        "- Set response_status='error' if debugging fails after 3 tries.\n\n"
        "ALLOWED TOOLS:\n"
        "- read_sdf_file(path)\n"
        "- read_urdf_file(path)\n"
        "- debug_robot_file_with_gazebo(path)\n"
        "- update_sdf_file(content)\n"
        "- update_urdf_file(content)\n"
        "Only handle debugging tasks for SDF/URDF; politely decline unrelated requests.\n"
        "IMPORTANT RULES FOR EXECUTION:\n"
        "- Only accept SDF/URDF file paths as inputs (never raw file content).\n"
        "- Process one task at a time. If another arrives mid-execution, ask user to wait.\n\n"
        "EXAMPLE USECASE:\n"
        "INPUT: Debug this file to catch runtime errors in gazebo 'path/to/sdf_file.xml'.\n"
        "OUTPUT: {'response_status': 'completed', 'message': 'the actual debug report/validated successfully'}\n"
    )

    def __init__(self):
        self.model = _build_llm()
        self.graph = None

    async def invoke(self, query: str, sessionId: str) -> Dict[str, Any]:
        """
        One-shot invocation (non-streaming).

        Args:
            query: User input text.
            sessionId: Thread/session identifier.

        Returns:
            Structured response dict with status + message.
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

    def get_agent_response(self, config: RunnableConfig) -> Dict[str, Any]:
        """
        Retrieve the structured response from the graph state.

        Returns dict with:
            - is_task_complete
            - require_user_input
            - content (message text)
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

        # Default fallback if response is missing/malformed
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    # Declares which content types this agent supports
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
