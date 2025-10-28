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

# Persistent memory store for agent state
memory = MemorySaver()


class ResponseFormat(BaseModel):
    """
    Defines the structured format of responses returned by the agent.

    Attributes:
        status (Literal): Indicates the state of execution. Options:
            - "input_required": additional input needed.
            - "completed": task successfully completed.
            - "error": execution failed.
        message (str): Human-readable response message.
    """
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


# ---------------------------------------------------------------------
# Utility functions for provider and model resolution
# ---------------------------------------------------------------------

def _get_provider() -> str:
    """Return the configured provider (Google, Groq, or OpenAI)."""
    return os.getenv("DESCRIBER_PROVIDER", "Google").strip()


def _get_model(
    default_google="gemini-2.5-flash",
    default_groq="llama3-70b",
    default_openai="gpt-4.1-mini",
) -> str:
    """
    Resolve the model name to use based on environment configuration.
    Falls back to provider-specific defaults if no override is set.
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
    Construct the appropriate Large Language Model (LLM) client
    based on provider and model selection.
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
    """Configuration for Multi-Server MCP client (tools interface)."""
    return {
        "mcp_tools": {
            "url": os.getenv("MCP_URL", "http://localhost:8000/sse"),
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
        }
    }


# ---------------------------------------------------------------------
# Core Agent
# ---------------------------------------------------------------------

class SpawnerAGVSDFAgent:
    """
    Agent responsible for spawning an AGV within an SDF world file
    and launching the environment in Gazebo.

    Execution Rules:
      - Accepts only SDF file paths (never raw content).
      - Uses the tool `spawn_agv_gazebo(path)` to perform spawning.
      - Tracks task state using structured responses:
        * 'input_required' if no file path is given.
        * 'completed' if Gazebo loads successfully.
        * 'error' if Gazebo fails to load.
      - Declines unrelated or out-of-scope tasks.
    """

    SYSTEM_INSTRUCTION = (
        "You take an SDF (.sdf) world file path as input and launch it in Gazebo with the AGV included.\n\n"
        "Workflow:\n"
        "1) Retrieve the user-provided SDF file path.\n"
        "2) Use the tool `spawn_agv_gazebo(path)` to create and spawn the AGV-included world file.\n"
        "3) If any errors occur, report them and stop.\n\n"
        "Status guidelines:\n"
        "- 'input_required' if the SDF file path is missing.\n"
        "- 'completed' when Gazebo loads the SDF without errors.\n"
        "- 'error' if Gazebo fails to open the SDF successfully.\n"
        "Only handle SDF spawning for AGVs; politely decline unrelated topics."
    )

    def __init__(self):
        self.model = _build_llm()
        self.graph = None

    # -----------------------------------------------------------------
    # High-level Invocation
    # -----------------------------------------------------------------
    async def invoke(self, query, sessionId) -> Dict[str, Any]:
        """
        Run the agent once on a given query.
        Returns a structured response with task status and message.
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

    # -----------------------------------------------------------------
    # Streaming Invocation
    # -----------------------------------------------------------------
    async def stream(self, query, sessionId) -> AsyncIterable[Dict[str, Any]]:
        """
        Stream intermediate reasoning steps, tool invocations, and
        final results back to the caller in real-time.
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

            if isinstance(message, AIMessage):
                # Agent's internal reasoning
                if message.content and message.content.strip() not in seen_contents:
                    seen_contents.add(message.content.strip())
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": message.content.strip(),
                        "type": "agent_thought",
                    }
                # Explicit tool calls
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
                # Tool responses
                tool_resp = f"Tool **{message.name}** response: {message.content}"
                if tool_resp not in seen_contents:
                    seen_contents.add(tool_resp)
                    yield {
                        "is_task_complete": False,
                        "require_user_input": False,
                        "content": tool_resp,
                        "type": "tool_response",
                    }

        # Final response once graph execution completes
        final = self.get_agent_response(config)
        final_content = final.get("content")
        if final_content and final_content not in seen_contents:
            final["type"] = "final"
            seen_contents.add(final_content)
            yield final

    # -----------------------------------------------------------------
    # Helper: Response Interpretation
    # -----------------------------------------------------------------
    def get_agent_response(self, config):
        """
        Extracts the structured response from the current graph state
        and maps it into a task status dictionary.
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

        # Fallback in case of unexpected state
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    # Supported content types for input/output
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
