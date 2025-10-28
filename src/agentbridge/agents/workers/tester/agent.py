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

# Use in-memory checkpointing so agent can remember reasoning within a session
memory = MemorySaver()


class ResponseFormat(BaseModel):
    """Structured response format expected from the Validator Agent."""

    status: Literal["input_required", "completed", "error"] = "input_required"
    message: str


def _provider() -> str:
    """Return the selected LLM provider (default = Google)."""
    return os.getenv("TESTER_PROVIDER", "Google").strip()


def _model() -> str:
    """
    Return the model name to use for the chosen provider.
    Falls back to a sensible default per provider if no override is set.
    """
    override = os.getenv("TESTER_MODEL")
    if override:
        return override.strip()

    prov = _provider().lower()
    if prov == "google":
        return "gemini-2.5-flash"
    elif prov == "groq":
        return "llama3-70b"
    elif prov == "openai":
        return "gpt-4.1-mini"  # safe default for OpenAI
    else:
        raise RuntimeError(f"Unsupported TESTER_PROVIDER: {prov}")


def _build_llm():
    """
    Instantiate the chat model client for the chosen provider.
    Requires the corresponding API key in the environment.
    """
    prov = _provider().lower()
    model = _model()

    if prov == "google":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set for Google provider")
        return ChatGoogleGenerativeAI(
            model=model, temperature=0, google_api_key=api_key
        )

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
        raise RuntimeError(f"Unsupported TESTER_PROVIDER: {prov}")


def _mcp_config() -> dict:
    """Return configuration for MCP (Model Context Protocol) tools server."""
    return {
        "mcp_tools": {
            "url": os.getenv("MCP_URL", "http://localhost:8000/sse"),
            "transport": os.getenv("MCP_TRANSPORT", "sse"),
        }
    }


class ValidatorAgent:
    """
    The ValidatorAgent validates and corrects SDF/URDF files by
    orchestrating tool calls and applying corrections based on validation output.
    """

    SYSTEM_INSTRUCTION = (
        "Your role is that of a robotics engineer with the task: validate and correct SDF and URDF files using tools.\n"
        "You think step-by-step, calling tools as needed to validate and fix the files.\n\n" 

        "Required input:\n"
        "- A valid SDF or URDF file path (or file content).\n\n"
        "PROCESS:\n"
        "1) Read and validate the SDF/URDF using tools.\n"
        "2) If required tags (e.g., <inertial>) are missing/invalid, apply corrections.\n"
        "3) Run up to 3 correction–validation cycles.\n"
        "4) After corrections, save the updated file and return the validation report.\n\n"

        "ERROR HANDLING:\n"
        "- If the file is unreadable or invalid XML, return an error and stop.\n"
        "- If input paths are missing, set response_status='input_required'.\n"
        "- Set response_status='completed' when the file is valid.\n"
        "- Set response_status='error' if corrections fail or the file is unfixable.\n\n"

        "ALLOWED TOOLS:\n"
        "- validate_sdf_file\n"
        "- validate_urdf_file\n"
        "- update_sdf_file\n"
        "- update_urdf_file\n"

        "If the validation tools suggest fixes, apply them yourself.\n"
        "Politely decline unrelated requests."

        "IMPORTANT RULES FOR EXECUTION:\n"
        "- Only accept SDF/URDF file path as inputs for your tasks and NEVER the actual file content.\n"
        "- ONLY process one task at a time. If the user send a second task while the current task is executing politely ask the user to wait.\n\n"
    )

    def __init__(self):
        self.model = _build_llm()
        self.graph = None

    async def invoke(self, query, sessionId) -> Dict[str, Any]:
        """
        Run the agent once with the given query and session ID.
        Returns the structured response from the agent.
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
        Inspect the current agent state and return a structured dictionary
        based on the ResponseFormat (input_required, error, completed).
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

    # Supported content types for this agent
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]
