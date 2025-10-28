import os
import re
import time
import uuid
from urllib.parse import urlparse

import httpx
import requests
from dotenv import load_dotenv
from langchain_core.tools import tool

load_dotenv()


# -------------------------------------------------------------------
# Delegator URL Resolution
# -------------------------------------------------------------------

def _resolve_delegator_base() -> str:
    """
    Resolve the base URL for the Delegator service.

    Reads `DELEGATOR_URL` from the environment, normalizes it,
    and ensures it includes a scheme and no trailing slash.

    Fallback: http://localhost:12000
    """
    url = os.getenv("DELEGATOR_URL", "http://localhost:12000").strip()
    if not url:
        url = "http://localhost:12000"
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "http://" + url  # add scheme if omitted
    return url.rstrip("/")


DELEGATOR_URL = _resolve_delegator_base()


# -------------------------------------------------------------------
# Tool: wait_twenty_seconds
# -------------------------------------------------------------------

@tool
def wait_twenty_seconds() -> str:
    """
    Simple blocking delay tool.

    Pauses execution for 20 seconds, useful for workflows
    where agents need to wait for external results to appear.
    """
    time.sleep(20)
    return "Waited for 20 seconds."


# -------------------------------------------------------------------
# Tool: list_remote_agents
# -------------------------------------------------------------------

@tool
def list_remote_agents() -> str:
    """
    Query the Delegator service for available remote agents.

    Calls the /agent/list endpoint and returns a human-readable
    summary of each agent, including:
      - name, description, URL, version
      - tags, default input/output modes
      - skills (with description/examples)

    Returns:
        A formatted string for inspection by planners/LLMs.
    """
    try:
        url = f"{DELEGATOR_URL}/agent/list"
        response = requests.post(url, headers={"accept": "application/json"}, json={})
        response.raise_for_status()
        data = response.json()
        if not data.get("result"):
            return "No remote agents found."

        out = []
        for agent in data["result"]:
            name = agent.get("name", "Unnamed")
            desc = agent.get("description", "No description provided")
            url_ = agent.get("url", "N/A")
            version = agent.get("version", "N/A")
            tags = ", ".join(agent.get("tags", [])) if agent.get("tags") else "None"
            input_modes = (
                ", ".join(agent.get("defaultInputModes", []))
                if agent.get("defaultInputModes")
                else "Not specified"
            )
            output_modes = (
                ", ".join(agent.get("defaultOutputModes", []))
                if agent.get("defaultOutputModes")
                else "Not specified"
            )
            skills = agent.get("skills", [])
            skills_strs = []
            for s in skills:
                skills_strs.append(
                    f"  - Skill ID: {s.get('id', 'N/A')}\n"
                    f"    Name: {s.get('name', 'N/A')}\n"
                    f"    Description: {s.get('description', 'N/A')}\n"
                    f"    Tags: {', '.join(s.get('tags', [])) if s.get('tags') else 'None'}\n"
                    f"    Examples: {s.get('examples', ['None'])}"
                )
            skills_block = "\n".join(skills_strs) if skills_strs else "  None"

            out.append(
                f"---\n"
                f"Name: {name}\n"
                f"Description: {desc}\n"
                f"URL: {url_}\n"
                f"Version: {version}\n"
                f"Tags: {tags}\n"
                f"Default Input Modes: {input_modes}\n"
                f"Default Output Modes: {output_modes}\n"
                f"Skills:\n{skills_block}\n"
                f"---"
            )
        return "\n".join(out)

    except Exception as e:
        return f"Failed to list remote agents: {e}"


# -------------------------------------------------------------------
# Tool: start_conversation
# -------------------------------------------------------------------

@tool
def start_conversation() -> str:
    """
    Initiate a new conversation with the Delegator.

    Calls the /conversation/create endpoint and returns
    the conversation ID and its active status.
    """
    try:
        url = f"{DELEGATOR_URL}/conversation/create"
        headers = {"accept": "application/json"}
        response = requests.post(url, headers=headers, json={})
        response.raise_for_status()
        data = response.json()

        if "result" in data and "conversation_id" in data["result"]:
            conversation_id = data["result"]["conversation_id"]
            is_active = data["result"].get("is_active", False)
            return (
                f"Conversation started successfully!\n"
                f"Conversation ID: {conversation_id}\n"
                f"Active: {is_active}"
            )
        else:
            return f"Failed to create conversation. Response: {data}"

    except Exception as e:
        return f"Failed to start conversation: {e}"


# -------------------------------------------------------------------
# Tool: save_plan
# -------------------------------------------------------------------

@tool
def save_plan(content: str) -> str:
    """
    Save the generated plan to a Markdown file.

    Args:
        content: The plan text (string, expected Markdown).

    Behavior:
        - Saves to `tasks/logs/plan.md`
        - Ensures directory exists
        - Overwrites any existing plan file

    Returns:
        Status message with absolute file path or error.
    """
    try:
        if not isinstance(content, str):
            return "Error: content must be a string."

        path = os.path.abspath("tasks/logs/plan.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        to_write = content.rstrip() + "\n"  # clean trailing newline

        with open(path, "w", encoding="utf-8") as f:
            f.write(to_write)

        os.path.getsize(path)  # sanity check
        return f"Saved plan.md at {path}"

    except Exception as e:
        return f"Failed to save plan.md: {e}"


# -------------------------------------------------------------------
# Tool: send_message
# -------------------------------------------------------------------

@tool
def send_message(conversation_id: str, message: str) -> str:
    """
    Send a message to the Delegator HostAgent service.

    Args:
        conversation_id: The UUID of the conversation (from /conversation/create).
        message: Text message to send.

    Returns:
        The backend API response (JSON) as a string.
    """
    headers = {"accept": "application/json", "Content-Type": "application/json"}
    info = f"Sending message to conversation {conversation_id}: {message}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "contextId": conversation_id,
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "parts": [{"type": "text", "text": message}],
        },
    }
    response = httpx.post(
        f"{DELEGATOR_URL}/message/send", headers=headers, json=payload, timeout=30
    )
    response.raise_for_status()
    time.sleep(5)  # allow delegator to respond
    return f"{info}\nAPI response: {response.json()}"


# -------------------------------------------------------------------
# Tool: fetch_filtered_events_and_tasks
# -------------------------------------------------------------------

@tool
def fetch_filtered_events_and_tasks(conversation_id: str) -> str:
    """
    Fetch a compact snapshot of tasks and conversations for a given context.

    Calls:
        - /events/get
        - /task/list

    Produces a Markdown summary containing:
      - Recent Tasks: names, condensed outputs, brief history
      - Recent Conversations: last few relevant messages

    Also logs snapshots to:
      - tasks/logs/conversation_log.md
      - tasks/logs/conversation_id.txt
    """
    headers = {"accept": "application/json", "Content-Type": "application/json"}

    def make_rpc_call(method_name):
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method_name,
            "params": {},
        }
        url = f"{DELEGATOR_URL}/{method_name}"
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("result", [])

    # Cleaners for large/structured content
    MAX_LEN = 300
    XML_BLOCK_RE = re.compile(r"<[^>]+>.*</[^>]+>", re.DOTALL)
    JSON_BLOCK_RE = re.compile(r"\{\s*\"[^}]+\"\s*:\s*[^}]+\}", re.DOTALL)

    def clean_text(s: str) -> str:
        if not s:
            return ""
        s = s.strip()

        if XML_BLOCK_RE.search(s):
            s = "[XML CONTENT]"
        elif JSON_BLOCK_RE.search(s) and ".json" not in s:
            s = "[JSON CONTENT]"

        if len(s) > MAX_LEN:
            s = s[:MAX_LEN].rstrip() + "..."
        return s

    try:
        # === EVENTS ===
        events = make_rpc_call("events/get")
        if not events:
            snapshot = (
                f"Recent Tasks:\n  (none)\n\n"
                f"Recent Conversations:\n  No events returned for conversation {conversation_id}."
            )
        else:
            formatted_events, actor_labels = [], []
            for event in events:
                content = event.get("content", {})
                if content.get("contextId") != conversation_id:
                    continue

                parts = content.get("parts", [])
                full_text = "".join(
                    p.get("text", "") for p in parts if p.get("kind") == "text"
                )
                full_text = clean_text(full_text)
                if not full_text:
                    continue

                actor = event.get("actor", "Unknown")
                if actor == "user":
                    actor = "Orchestrator(You)"

                formatted_events.append(f"{actor}: {full_text}")
                actor_labels.append(actor)

            total_msgs = len(formatted_events)
            if total_msgs <= 10:
                trimmed_events = formatted_events
            else:
                last_orch_index = 0
                for i in range(total_msgs - 1, -1, -1):
                    if actor_labels[i] == "Orchestrator(You)":
                        last_orch_index = i
                        break
                if last_orch_index >= total_msgs - 20:
                    trimmed_events = formatted_events[-20:]
                else:
                    trimmed_events = formatted_events[last_orch_index:]

            # === TASKS ===
            tasks = make_rpc_call("task/list")
            tasks_lines = []
            for task in tasks:
                if task.get("contextId") != conversation_id:
                    continue

                artifacts = task.get("artifacts", []) or []
                task_name = task.get("id") or "UnnamedTask"
                final_output = ""

                if artifacts:
                    task_name = artifacts[0].get("name") or task_name
                    texts = []
                    for art in artifacts:
                        for part in art.get("parts", []) or []:
                            if part.get("kind") == "text":
                                texts.append(part.get("text", ""))
                            elif part.get("kind") == "file":
                                texts.append("[FILE CONTENT]")
                    final_output = clean_text(" ".join(texts).strip())

                # History: last 5 messages
                hist = task.get("history", []) or []
                last5 = hist[-5:] if len(hist) > 5 else hist
                history_lines = []
                for msg in last5:
                    parts = msg.get("parts", []) or []
                    text_chunks = []
                    for p in parts:
                        if p.get("kind") == "text":
                            text_chunks.append(p.get("text", ""))
                        elif p.get("kind") == "file":
                            text_chunks.append("[FILE CONTENT]")
                    text = clean_text("".join(text_chunks))
                    if not text:
                        continue
                    role = msg.get("role", "agent")
                    actor = "Orchestrator(You)" if role == "user" else "Agent"
                    history_lines.append(f"    - {actor}: {text}")

                tasks_lines.append(
                    "\n".join(
                        [
                            f"- Task: {task_name}",
                            f"  Final Output: {final_output or '(none)'}",
                            "  History:",
                            *(history_lines or ["    - (no recent messages)"]),
                        ]
                    )
                )

            tasks_section = "Recent Tasks:\n" + (
                "\n".join(tasks_lines) if tasks_lines else "  (none)"
            )
            conv_section = "Recent Conversations:\n" + (
                "\n".join(f"  {line}" for line in trimmed_events)
                if trimmed_events
                else "  (none)"
            )
            snapshot = f"{tasks_section}\n\n{conv_section}"

        # Save logs for inspection
        os.makedirs("tasks/logs", exist_ok=True)
        with open("tasks/logs/conversation_log.md", "w", encoding="utf-8") as f:
            f.write(snapshot)
        with open("tasks/logs/conversation_id.txt", "w", encoding="utf-8") as f:
            f.write(conversation_id)

        return snapshot

    except requests.RequestException as e:
        snapshot = (
            f"Recent Tasks:\n  (none)\n\nRecent Conversations:\n  Request error: {e}"
        )
    except ValueError as ve:
        snapshot = (
            f"Recent Tasks:\n  (none)\n\nRecent Conversations:\n  Invalid response format: {ve}"
        )

    # Save error snapshots too
    os.makedirs("tasks/logs", exist_ok=True)
    with open("tasks/logs/conversation_log.md", "w", encoding="utf-8") as f:
        f.write(snapshot)

    return snapshot
