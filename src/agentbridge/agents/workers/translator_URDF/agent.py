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

# Simple in-memory checkpoint store to keep session state
memory = MemorySaver()


class ResponseFormat(BaseModel):
    """
    Standard schema for structured responses.

    Attributes:
        status: one of ["input_required", "completed", "error"].
        message: a short explanation or result text for the user.
    """
    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


def _provider() -> str:
    """Return the configured LLM provider (default = Google)."""
    return os.getenv("TRANSLATOR_URDF_PROVIDER", "Google").strip()


def _model() -> str:
    """
    Select the model name depending on the provider.
    Environment variable TRANSLATOR_URDF_MODEL overrides defaults.
    """
    override = os.getenv("TRANSLATOR_URDF_MODEL")
    if override:
        return override.strip()

    prov = _provider().lower()
    if prov == "google":
        return "gemini-2.5-flash"
    elif prov == "groq":
        return "llama3-70b"
    elif prov == "openai":
        return "gpt-4.1-mini"  # default for OpenAI
    else:
        raise RuntimeError(f"Unsupported TRANSLATOR_URDF_PROVIDER: {prov}")


def _build_llm():
    """
    Build and return a chat model client based on provider and model name.
    Raises RuntimeError if the required API key is missing.
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
        raise RuntimeError(f"Unsupported TRANSLATOR_URDF_PROVIDER: {prov}")


def _mcp_config() -> dict:
    """Return configuration for MCP (Model Context Protocol) tool server."""
    return {
        "mcp_tools": {
            "url": os.getenv("MCP_URL", "http://localhost:8000/sse"),
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
        }
    }


class TranslatorURDFAgent:
    """
    Agent for converting robot/environment descriptions into URDF.

    Inputs:
      - Natural language description (.txt)
      - Structured description (.json)
      - MJCF file path (used to retrieve few-shot examples)

    Output:
      - A valid URDF file for Gazebo/ROS saved to disk.
    """

    SYSTEM_INSTRUCTION = (
        "You translate robot/environment descriptions from natural language (.txt) and JSON (.json) into valid URDF for Gazebo/ROS.\n"
        "Think step-by-step.\n\n"
        "Process:\n"
        "1) Use 'read_mjcf_file' tool to read the content of the provided MJCF file path.\n"
        "2) Use `retrieve_few_shot_examples_urdf(mjcf_path)` to fetch relevant MJCF↔URDF example pairs.\n"
        "3) Study the examples for structure and conventions.\n"
        "4) Read the user-provided .txt and .json using the tools 'read_description_file_NL' and 'read_description_file_JSON'.\n"
        "5) Generate a valid URDF using the MJCF content, TXT+JSON content, and conventions observed in the examples.\n"
        "6) Save the generated URDF file using the tool 'save_urdf_file'.\n\n"
        "Notes:\n"
        "- You can generate URDF directly without additional tools (besides reading/saving).\n"
        "- Save the URDF alongside the original MJCF path, same basename, `.urdf` extension.\n"
        "- Reply with the full path of the saved `.urdf`.\n"
        "- If you are assigned tasks while executing another task, politely decline.\n"
        "- NEVER invent materials/meshes/textures; only reference explicitly provided paths.\n\n"
        "Response status:\n"
        "- 'input_required' if MJCF/TXT/JSON paths are missing.\n"
        "- 'completed' after saving the URDF.\n"
        "- 'error' if parsing or saving fails.\n\n"
        "IMPORTANT RULES FOR EXECUTION:\n"
        "- Only accept file paths as inputs, never the raw file content.\n"
        "- NEVER return the actual file content of the generated URDF file.\n"
        "- ALWAYS return the file path of the generated URDF once saving is done.\n"
        "- Process one task at a time; ask the user to wait if another request arrives.\n\n"
        "EXAMPLE USECASE:\n"
        "INPUT: Create a valid URDF file using natural language description path/to/description.txt, JSON description path/to/description.json and the original file 'path/to/mjcf_file.xml'.\n"
        "OUTPUT: {'response_status': 'completed', 'message': 'Generated URDF file saved to path/to/urdf_file.'}\n\n"
    )

    def __init__(self):
        self.model = _build_llm()
        self.graph = None

    async def invoke(self, query, sessionId) -> Dict[str, Any]:
        """
        Execute the agent on a single query and return the structured result.
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
        followed by the final structured result.
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

            # Handle agent reasoning output
            if isinstance(message, AIMessage):
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
                # Handle tool call events
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

            # Handle tool responses
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

        # Yield the final result if available
        final = self.get_agent_response(config)
        final_content = final.get("content")
        if final_content and final_content not in seen_contents:
            final["type"] = "final"
            seen_contents.add(final_content)
            yield final

    def get_agent_response(self, config):
        """
        Inspect the agent's state and return the last structured response.
        Falls back to a generic error if no structured response is present.
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
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    # Supported input/output types for this agent
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
