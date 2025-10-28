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

# Memory store for keeping track of conversation state during a session
memory = MemorySaver()


class ResponseFormat(BaseModel):
    """
    Defines the standard structure for agent responses.

    Attributes:
        status: Response status → "input_required", "completed", or "error".
        message: Textual explanation or output message for the user.
    """

    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


def _get_provider() -> str:
    """Return the LLM provider (default = Google)."""
    return os.getenv("DESCRIBER_PROVIDER", "Google").strip()


def _get_model(
    default_google="gemini-2.5-flash",
    default_groq="llama3-70b",
    default_openai="gpt-4.1-mini",
) -> str:
    """
    Return the model name for the chosen provider.

    Priority:
      1. DESCRIBER_MODEL environment variable (manual override).
      2. Default model depending on provider.
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
    Instantiate and return the appropriate LLM client for the selected provider.
    Each case checks for the corresponding API key.
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
    """Return configuration for the MCP (Model Context Protocol) tools server."""
    return {
        "mcp_tools": {
            "url": os.getenv("MCP_URL", "http://localhost:8000/sse"),
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
        }
    }


class TranslatorSDFAgent:
    """
    TranslatorSDFAgent converts combined natural language (.txt) and JSON (.json)
    robot/environment descriptions into valid SDF (Simulation Description Format)
    files for Gazebo. It follows a tool-augmented reasoning process.
    """

    SYSTEM_INSTRUCTION = (
        "You translate robot/environment descriptions from natural language (.txt) and JSON (.json) into valid SDF files for Gazebo.\n"
        "Think step-by-step.\n\n"
        "Process:\n"
        "1) Read the user-provided .txt and .json using the tools 'read_description_file_NL' and 'read_description_file_JSON'.\n"
        "2) List all contextual and structural information you got from the description files.\n"
        "3) Generate and save a valid SDF using TXT+JSON along with your own knowledge of SDF files for Gazebo.\n"
        "4) Save the generated SDF file using the tool 'save_sdf_file'.\n"
        "5) Reply with the full path of the saved SDF file and a summary of how you converted it to SDF and what conventions you followed.\n\n"
        "Notes:\n"
        "- You can generate SDF directly without additional tools (besides reading/saving).\n"
        "- Save the SDF alongside the original MJCF path, same basename, `.sdf` extension.\n"
        "- Reply with the full path of the saved `.sdf`.\n"
        "- If you are assigned tasks while executing another task, politely say that you are busy and cannot accept any tasks at the moment.\n"
        "- NEVER invent materials/meshes/textures; only reference paths explicitly provided.\n\n"
        "Response status:\n"
        "- 'input_required' if MJCF/TXT/JSON paths are missing.\n"
        "- 'completed' after saving the SDF.\n"
        "- 'error' if parsing or saving fails.\n"
        "IMPORTANT RULES FOR EXECUTION:\n"
        "- Only accept file paths (path/to/description.txt, path/to/description.json, path/to/mjcf_file) as inputs for your tasks and NEVER the actual descriptions or file content.\n"
        "- NEVER return the actual file content of the generated SDF file.\n"
        "- ALWAYS return the file path of the generated SDF file once saving is done.\n"
        "- ONLY process one task at a time. If the user sends a second task while one is executing, politely ask them to wait.\n\n"
        "EXAMPLE USECASE:\n"
        "INPUT: Create a valid SDF file using natural language description path/to/description.txt, JSON description path/to/description.json and the file 'path/to/mjcf_file.xml'.\n"
        "OUTPUT: {'response_status': 'completed', 'message': 'Generated SDF file saved to path/to/sdf_file.'}\n\n"
    )

    def __init__(self):
        self.model = _build_llm()
        self.graph = None

    async def invoke(self, query, sessionId) -> Dict[str, Any]:
        """
        Run the agent once with the given query and return its structured response.
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
        Inspect the agent's state and return a structured response
        based on the ResponseFormat schema.
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
        # Fallback if no structured response could be parsed
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    # Supported input/output content types for this agent
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
