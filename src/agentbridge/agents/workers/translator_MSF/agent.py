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

# In-memory checkpointing: keeps track of conversation state within a session
memory = MemorySaver()


class ResponseFormat(BaseModel):
    """
    Standardized structure for agent responses.

    Fields:
      - status: one of ["input_required", "completed", "error"]
      - message: human-readable message to return to the user
    """

    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


def _get_provider() -> str:
    """Return the selected LLM provider (default = Google)."""
    return os.getenv("DESCRIBER_PROVIDER", "Google").strip()


def _get_model(
    default_google="gemini-2.5-flash",
    default_groq="llama3-70b",
    default_openai="gpt-4.1-mini",
) -> str:
    """
    Select the appropriate model name for the current provider.

    If DESCRIBER_MODEL is set in the environment, that takes priority.
    Otherwise, use sensible defaults depending on the provider.
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
    Initialize and return the appropriate chat model client based on provider.
    Each branch checks for the required API key in the environment.
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
    Return configuration for connecting to the MCP (Model Context Protocol) tools server.
    """
    return {
        "mcp_tools": {
            "url": os.getenv("MCP_URL", "http://localhost:8000/sse"),
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
        }
    }


class TranslatorMSFAgent:
    """
    TranslatorMSFAgent is responsible for converting MSF files (Mock Simulation Format)
    into valid SDF files for Gazebo, with the help of retrieved few-shot examples.
    """

    SYSTEM_INSTRUCTION = (
        "You translate MSF (Mock Simulation Format) files into valid SDF files for Gazebo.\n"
        "Think step-by-step.\n\n"
        "Process:\n"
        "1) Use 'read_msf_file' tool to read the content of the provided MSF file path.\n"
        "2) Use `retrieve_few_shot_examples_msf(msf_path)` to fetch relevant MSF↔SDF example pairs.\n"
        "3) Study the examples carefully for conventions and rules for MSF↔SDF conversion.\n"
        "4) List all conventions, perturbations (value offsets) and structures you observe in the examples.\n"
        "5) Generate a valid SDF using the MSF content and the conventions observed in the examples along with your own knowledge of SDF files for Gazebo.\n"
        "6) Save the generated SDF file using the tool 'save_sdf_file'\n"
        "7) Reply with the full path of the saved SDF file and a summary of how you converted it to SDF and what conventions you followed.\n\n"
        "Notes:\n"
        "- You can generate SDF directly without additional tools (besides reading/saving).\n"
        "- Save the SDF alongside the original MSF path, same basename, `.sdf` extension.\n"
        "- Reply with the full path of the saved `.sdf`.\n"
        "- If you are assigned tasks while executing another task, politely say that you are busy and cannot accept any tasks at the moment.\n"
        "- NEVER invent materials/meshes/textures; only reference paths explicitly provided.\n\n"
        "Response status:\n"
        "- 'input_required' if MSF path is missing.\n"
        "- 'completed' after saving the SDF.\n"
        "- 'error' if parsing or saving fails.\n"
        "IMPORTANT RULES FOR EXECUTION:\n"
        "- Only accept file path (path/to/msf_file) as input for your tasks and NEVER the actual content of msf file content.\n"
        "- NEVER return the actual file content of the generated SDF file.\n"
        "- ALWAYS return the file path of generated SDF file once saving is done.\n"
        "- ONLY process one task at a time. If the user send a second task while the current task is executing politely ask the user to wait.\n\n"
        "EXAMPLE USECASE:\n"
        "INPUT: Create a valid SDF file using the file 'path/to/msf_file.msf'.\n"
        "OUTPUT: {'response_status': 'completed', 'message': 'Generated SDF file saved to path/to/sdf_file.'}\n\n"
    )

    def __init__(self):
        self.model = _build_llm()
        self.graph = None

    async def invoke(self, query, sessionId) -> Dict[str, Any]:
        """
        Run the agent for a single query and return the structured response.
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
        Stream intermediate reasoning, tool calls, and tool responses to the client.
        Yields incremental events until the final structured response is available.
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

            # Capture agent thoughts and reasoning steps
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
                # Capture tool calls made by the agent
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

        # At the end, yield the final structured response
        final = self.get_agent_response(config)
        final_content = final.get("content")
        if final_content and final_content not in seen_contents:
            final["type"] = "final"
            seen_contents.add(final_content)
            yield final

    def get_agent_response(self, config):
        """
        Look up the agent's current state and return a structured response
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
        # Fallback if no structured response is present
        return {
            "is_task_complete": False,
            "require_user_input": True,
            "content": "We are unable to process your request at the moment. Please try again.",
        }

    # Supported content types for this agent
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
