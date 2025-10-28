import os
import re
import uuid
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

# Load environment variables (API keys, provider, etc.)
load_dotenv()


def _resolve_delegator_base() -> str:
    """Resolve the base URL for the Delegator service from environment.

    Normalizes URL (adds scheme if missing, strips trailing slash).
    Defaults to http://localhost:12000 if not set.
    """
    url = os.getenv("DELEGATOR_URL", "http://localhost:12000").strip()
    if not url:
        url = "http://localhost:12000"
    parsed = urlparse(url)
    if not parsed.scheme:
        url = "http://" + url
    return url.rstrip("/")


DELEGATOR_URL = _resolve_delegator_base()

# Read API keys and model/provider selection from environment
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TASK_PROVIDER = os.getenv("TASKS_PROVIDER")
MODEL_NAME = os.getenv("TASKS_MODEL", "gemini-2.0-flash")  # sensible default

# Few-shot examples to guide LLM when expanding/refining tasks
_FEW_SHOTS = """Examples:

Task input: Say Hi to Delegator
Task Output: Say Hi to Delegator

Task input: List all available agents
Task Output: 1. Say Hi to Delegator. 2. After it responds ask it to list all available agents.

Task input: Greet all available agents
Task Output: 1. Say Hi to Delegator. 2. After it responds ask it to list all available agents. 3. After it responds ask it to greet all available agents.

Task input: convert this mjcf file '/Users/gopikrishnan/VSCode/AgentBridge/data/warehouse.xml' into a valid URDF file
Task Output: 1. Create a step by step plan to convert this mjcf file '/Users/gopikrishnan/VSCode/AgentBridge/data/mjcf/mug.xml' into a valid URDF file. 2. Include any validation or debugging step if available 3. Orchestrate the plan using Delegator. 4. Discuss the plan with the Delegator before proceeding. 5. Wait for response from each step before moving on to the next step in the plan.

Task input: Add a shelf at the center of this SDF world file '/Users/gopikrishnan/VSCode/AgentBridge/data/warehouse.sdf' 
Task Output: 1. Create a step by step plan to add a shelf at the center of this SDF world file '/Users/gopikrishnan/VSCode/AgentBridge/data/warehouse.sdf'. 2. Include any validation or debugging step if available 3. Orchestrate the plan using Delegator. 4. Discuss the plan with the Delegator before proceeding. 5. Wait for response from each step before moving on to the next step in the plan.
"""


def fetch_conversation(conversation_id: str) -> str:
    """Fetch full conversation history for a given conversation_id.

    Uses Delegator JSON-RPC endpoint `events/get`.

    Args:
        conversation_id: Context ID of the conversation.

    Returns:
        Markdown-formatted snapshot of "Recent Conversations".
        Falls back to a log file in case of errors.
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
        return resp.json().get("result", [])

    # Regex patterns to sanitize large content blobs
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
        return s

    try:
        events = make_rpc_call("events/get")
        if not events:
            snapshot = (
                f"Recent Conversations:\n"
                f"  No events returned for conversation {conversation_id}."
            )
        else:
            formatted_events = []
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

            conv_section = "Recent Conversations:\n" + (
                "\n".join(f"  {line}" for line in formatted_events)
                if formatted_events
                else "  (none)"
            )
            snapshot = conv_section

        return snapshot

    except requests.RequestException as e:
        snapshot = f"Recent Conversations:\n  Request error: {e}"
    except ValueError as ve:
        snapshot = f"Recent Conversations:\n  Invalid response format: {ve}"

    # Persist error snapshot for debugging
    with open("tasks/logs/conversation_log.md", "w", encoding="utf-8") as f:
        f.write(snapshot)

    return snapshot


def _generate_response(
    prompt: str, model_name: str, temperature: float = 0.3, max_tokens: int = 2048
) -> str:
    """Send prompt to chosen LLM provider and return response string."""
    if TASK_PROVIDER == "Google":
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            max_output_tokens=max_tokens,
            api_key=GOOGLE_API_KEY,
        )
    elif TASK_PROVIDER == "Groq":
        llm = ChatGroq(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=GROQ_API_KEY,
        )
    else:
        raise ValueError("Unsupported TASK_PROVIDER. Please use 'Google' or 'Groq'.")

    # Simple single-message prompt chain
    prompt_template = ChatPromptTemplate.from_messages([("user", "{input}")])
    chain = prompt_template | llm | StrOutputParser()

    return chain.invoke({"input": prompt}).strip()


def refine_task(
    task_input: str, *, model_name: str = MODEL_NAME, temperature: float = 0.3
) -> str:
    """Turn a short task instruction into a structured numbered plan. Always preserve any file paths mentioned in the Task input as it is while generating."""
    prompt = f"""{_FEW_SHOTS}

Task input: {task_input}
Task Output:"""
    return _generate_response(prompt, model_name, temperature=temperature)


def evaluate_and_replan_with_llm(
    task_executed: str,
    plan_path: str,
    conversation_log_path: str,
    conversation_id_path: str,
    *,
    model_name: str = MODEL_NAME,
    temperature: float = 0.3,
) -> str:
    """Evaluate whether a task succeeded, and if not, create a recovery plan.

    Reads original plan, fetches execution log (Delegator or fallback),
    and asks LLM to decide if the task was completed. If failed, the
    model should propose a corrected step-by-step plan.
    """

    # --- Load original plan ---
    plan_text = "(no plan available)"
    if os.path.exists(plan_path):
        with open(plan_path, "r+", encoding="utf-8") as f:
            plan_text = f.read().strip() or "(empty plan)"
            # Clear plan file after reading
            f.seek(0)
            f.write("")
            f.truncate()
    else:
        print(f"[WARN] Plan file not found at {plan_path}")

    # --- Try Delegator conversation log ---
    conversation_text = None
    try:
        if os.path.exists(conversation_id_path):
            with open(conversation_id_path, "r+", encoding="utf-8") as f:
                conversation_id = f.read().strip()
                if not conversation_id:
                    print("[SKIP] No conversation_id found — skipping evaluation.")
                    return ""

                conversation_text = fetch_conversation(conversation_id)

                # Clear ID file
                f.seek(0)
                f.write("")
                f.truncate()
        else:
            print(f"[WARN] Conversation ID file not found at {conversation_id_path}")
            conversation_text = "(no conversation id available)"

        if (
            not conversation_text
            or "Request error" in conversation_text
            or "Invalid response" in conversation_text
        ):
            raise RuntimeError("Delegator log unavailable or invalid.")

    except Exception as e:
        conversation_text = "(no conversation log available)"
        print(f"Conversarion fetch error: {e}")

    # --- Construct evaluation prompt ---
    prompt = f"""
You are an execution plan evaluator and recovery planner.
Think carefully step by step, using only the provided context.

Your tasks:
1. Decide if the task was successful by inspecting the final output. Minor intermediate missteps are acceptable if the final output is correct.
2. If not successful, identify where it failed.
3. Generate a new numbered plan starting from the next needed step.
4. Make sure to include all worker agents and file paths exactly as given in the original inputs.
5. Re-include failed steps if they need correction/re-execution.
6. Keep the plan concise but clear.

Example output:
❌ Task failed or partially completed (Debugger agent execution failed). 
1. Debug the SDF world file '/Users/gopikrishnan/VSCode/AgentBridge/data/warehouse.sdf'. 
2. Wait for response before continuing.

**Guidelines**:
- Never hallucinate details beyond the given info.
- Do not assume resources unless they are explicitly provided.
- For tasks like "List all agents" or "Greet all agents", completion is valid if *some* agents respond.

Special Case:
- If Original Plan and Task Executed are not available (i.e. both are empty), respond with: "No plan or execution details available retrying with original task input."
- Then send the same task without any modifications.

Task executed:
{task_executed}

Original Plan:
{plan_text}

Execution Log:
{conversation_text}

Your output must start with either:
- "✅ Task was successfully completed."
OR
- "❌ Task failed or partially completed (...reason... with explanation of how you understood it from the Execution Log)" + new plan.
"""

    return _generate_response(
        prompt, model_name, temperature=temperature, max_tokens=2048
    )


def refine_replan_task(
    replan_text: str, *, model_name: str = MODEL_NAME, temperature: float = 0.2
) -> str:
    """Condense a failed evaluation replan into a minimal directive.
    
    Instead of generating a full step-by-step plan, this creates 
    a short single-line instruction like:
    'Correct the SDF file for runtime errors using the Debugger agent.'
    """
    prompt = f"""
The following text is a recovery plan after a task failed:

{replan_text}

Your job:
- Do NOT rewrite a detailed step-by-step plan.
- Reduce it to ONE minimal directive with all worker agents and file paths correctly mentioned.
- Keep it short, actionable, and clear.
- Always preserve file paths exactly as given.
- Always preserve agent names exactly as given.

Example 2:
Input replan:
❌ Task failed or partially completed (Debugger agent failed to run the SDF file in Gazebo).
1. Correct the physics plugin name in the SDF file '/path/to/sample1.sdf'.
2. Rerun the Gazebo simulation with the corrected SDF file.

Output refined task:
Correct the SDF file ('/path/to/sample1.sdf') for runtime errors using the Debugger agent.
"""
    return _generate_response(prompt, model_name, temperature=temperature)
