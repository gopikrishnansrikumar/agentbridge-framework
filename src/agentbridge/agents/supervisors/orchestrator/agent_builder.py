# agent_builder.py
import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from settings import SYSTEM_PROMPT
from tools import (
    fetch_filtered_events_and_tasks,
    list_remote_agents,
    save_plan,
    send_message,
    start_conversation,
    wait_twenty_seconds,
)

load_dotenv()


def _build_model():
    """
    Select and initialize the appropriate LLM backend based on environment configuration.

    The provider is determined by the `ORCHESTRATOR_PROVIDER` environment variable,
    and the specific model can be overridden using `ORCHESTRATOR_MODEL`.

    Supported providers:
      - Google (Gemini models)
      - Groq (LLaMA models)
      - OpenAI (GPT models)

    Returns:
        A LangChain chat model instance (Google, Groq, or OpenAI).
    """
    provider = (os.getenv("ORCHESTRATOR_PROVIDER") or "google").lower()
    model_name = os.getenv("ORCHESTRATOR_MODEL") or (
        "gemini-2.5-pro"
        if provider == "google"
        else "llama-3.3-70b-versatile" if provider == "groq" else "gpt-4.1-mini"
    )

    if provider == "google":
        # Requires GOOGLE_API_KEY in environment
        return ChatGoogleGenerativeAI(model=model_name, temperature=0)
    elif provider == "groq":
        # Requires GROQ_API_KEY in environment
        return ChatGroq(model=model_name, temperature=0)
    elif provider == "openai":
        # Requires OPENAI_API_KEY in environment
        return ChatOpenAI(model=model_name, temperature=0)
    else:
        raise ValueError(f"Unsupported PROVIDER: {provider}")


def build_agent():
    """
    Construct the main orchestrator agent.

    The agent is configured with:
      - The selected chat model (from `_build_model`)
      - A set of tools that allow interaction with remote agents, 
        planning, messaging, and event/task retrieval
      - A system prompt that provides role-specific guidance

    Returns:
        A LangGraph ReAct agent instance ready for orchestration tasks.
    """
    model = _build_model()
    agent = create_react_agent(
        model=model,
        tools=[
            wait_twenty_seconds,
            list_remote_agents,
            start_conversation,
            save_plan,
            send_message,
            fetch_filtered_events_and_tasks,
        ],
        prompt=SYSTEM_PROMPT,
    )
    return agent
