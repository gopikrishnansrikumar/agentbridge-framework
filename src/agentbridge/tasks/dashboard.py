from __future__ import annotations

import json
import os
import sys
import time
import uuid
import signal
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests
import random
import string

from dotenv import load_dotenv
from urllib.parse import urlparse

os.environ["GRADIO_TEMP_DIR"] = str(Path.home() / ".cache" / "gradio")
os.environ.setdefault("TMPDIR", str(Path.home() / ".cache" / "tmp"))
Path(os.environ["GRADIO_TEMP_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["TMPDIR"]).mkdir(parents=True, exist_ok=True)

import gradio as gr

def _orchestrator_health_url() -> str:
    base = (os.getenv("ORCHESTRATOR_URL") or "http://localhost:10000").strip()
    if "://" not in base:
        base = "http://" + base
    return base.rstrip("/") + "/health"

def generate_task_id(existing_ids=None) -> str:
    """Generate a unique Task ID like Task-ab12 (4 random lowercase letters/numbers)."""
    existing_ids = existing_ids or set()
    while True:
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        tid = f"Task-{suffix}"
        if tid not in existing_ids:
            return tid

def _tasks_bind() -> tuple[str, int]:
    # Explicit overrides win
    host_env = os.getenv("TASKS_HOST")
    port_env = os.getenv("TASKS_PORT")
    if host_env or port_env:
        return (host_env or "localhost", int(port_env or "14000"))
    # Else derive from TASKS_URL
    url = (os.getenv("TASKS_URL") or "http://localhost:14000").strip()
    if "://" not in url:
        url = "http://" + url
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = int(parsed.port or 14000)
    return host, port

def workers_available(timeout: float = 5) -> tuple[int, list[str], bool]:
    """
    Query the agent/list endpoint and return (count, names, delegator_status).
    """
    base = (os.getenv("DELEGATOR_URL") or "http://localhost:12000").strip()
    if "://" not in base:
        base = "http://" + base
    url = base.rstrip("/") + "/agent/list"
    try:
        r = requests.post(
            url,
            headers={"accept": "application/json", "Content-Type": "application/json"},
            json={},
            timeout=timeout,
        )
        if r.status_code == 200:
            data = r.json()
            result = data.get("result") or []
            if isinstance(result, list):
                names = [agent.get("name", "Unknown") for agent in result]
                return len(result), names, True
        return 0, [], False
    except Exception as e:
        print(f"[workers_available] Exception: {e}")
        return 0, [], False


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
WATCHER_SCRIPT = BASE_DIR / "watch_tasks.py"
TASK_FILE = BASE_DIR / "task_lists" / ("task_list.json" if (BASE_DIR / "task_list.json").exists() or not (BASE_DIR / "tasks_list.json").exists() else "tasks_list.json")
COMPLETED_FILE = BASE_DIR / "task_lists" / "completed_tasks.json"
LOG_FILE = BASE_DIR / "logs/watcher.log"
PID_FILE = BASE_DIR / "logs/watcher.pid"
RUNNING_FILE = BASE_DIR / "task_lists" / "running_task.json"
ORCH_HEALTH_URL = _orchestrator_health_url()
PRIORITIES = ["urgent", "high", "medium", "low"]

def load_tasks() -> List[Dict[str, Any]]:
    if not TASK_FILE.exists():
        return []
    try:
        return json.loads(TASK_FILE.read_text())
    except json.JSONDecodeError:
        return []

def save_tasks(tasks: List[Dict[str, Any]]) -> None:
    TASK_FILE.write_text(json.dumps(tasks, indent=4))

def add_task(kind: str, urgency: str, payload_extra: Dict[str, Any]) -> Dict[str, Any]:
    tasks = load_tasks()
    existing_ids = {t.get("task_id") for t in tasks if t.get("task_id")}
    task_id = generate_task_id(existing_ids)
    task = {
        "task_id": task_id,
        "kind": kind or "generic_task",
        "payload": {"urgency": (urgency or "medium").lower(), **(payload_extra or {})},
    }
    tasks.append(task)
    save_tasks(tasks)
    return task

def remove_tasks(task_ids: List[str]) -> int:
    if not task_ids:
        return 0
    sids = set(map(str, task_ids))
    tasks = load_tasks()
    before = len(tasks)
    tasks = [t for t in tasks if str(t.get("task_id")) not in sids]
    save_tasks(tasks)
    return before - len(tasks)

def get_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None

def set_pid(pid: int) -> None:
    PID_FILE.write_text(str(pid))

def clear_pid() -> None:
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

def is_process_running(pid: int | None) -> bool:
    """
    Return True only if the PID is alive *and* it's our watch_tasks.py process.
    If the PID is alive but not our watcher, clear the PID file and return False.
    """
    if not pid:
        return False

    # Step 1: is the PID alive?
    try:
        if platform.system() == "Windows":
            out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}"])
            alive = str(pid) in out.decode(errors="ignore")
        else:
            os.kill(pid, 0)
            alive = True
    except (ProcessLookupError, OSError, subprocess.CalledProcessError):
        alive = False
    except PermissionError:
        # Process exists but we may not have permission; continue to verify cmdline
        alive = True

    if not alive:
        return False

    # Step 2: verify the command line belongs to our watcher
    try:
        cmd = ""
        if platform.system() == "Windows":
            # Use WMIC (works widely) to fetch the command line
            cmd = subprocess.check_output(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine", "/value"],
                stderr=subprocess.DEVNULL
            ).decode(errors="ignore").lower()
        else:
            # ps shows the full command line
            cmd = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "command="],
                stderr=subprocess.DEVNULL
            ).decode(errors="ignore").lower()

        watcher_name = str(WATCHER_SCRIPT.name).lower()
        if ("watch_tasks.py" in cmd) or (watcher_name in cmd):
            return True

        # PID is alive but not our watcher -> clear the stale pid file
        clear_pid()
        return False
    except Exception:
        # If we cannot verify, be conservative: don't claim it's running.
        clear_pid()
        return False


def orchestrator_healthy(timeout: float = 5) -> bool:
    try:
        r = requests.get(ORCH_HEALTH_URL, timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False

def start_watcher() -> Tuple[str, str]:
    if not WATCHER_SCRIPT.exists():
        return ("error", f"executor script not found: {WATCHER_SCRIPT}")
    existing = get_pid()
    if existing and is_process_running(existing):
        return ("info", f"Executor already running (PID {existing})")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_fp = open(LOG_FILE, "a", buffering=1)
    creationflags = 0
    if platform.system() == "Windows":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            [sys.executable, str(WATCHER_SCRIPT)],
            cwd=str(BASE_DIR),
            stdout=log_fp,
            stderr=log_fp,
            stdin=subprocess.DEVNULL,
            close_fds=platform.system() != "Windows",
            creationflags=creationflags,
        )
        set_pid(proc.pid)
        return ("success", f"Executor started (PID {proc.pid})")
    except Exception as e:
        return ("error", f"Failed to start executor: {e}")

def stop_watcher() -> Tuple[str, str]:
    pid = get_pid()
    if not pid:
        clear_pid()
        return ("info", "Executor not running")

    # Try to stop the process
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as e:
        # Even if signaling fails, clear the pid so the UI won't show a reused/random PID
        clear_pid()
        return ("error", f"Failed to stop executor: {e}")

    # IMPORTANT: clear PID immediately to avoid showing a reused PID as "Running"
    clear_pid()

    # Best-effort: tiny wait then report
    time.sleep(0.2)
    return ("warning", f"Stop signal sent to PID {pid}")


def tail_log(n_lines: int = 300) -> str:
    if not LOG_FILE.exists():
        return "(no logs yet)"
    try:
        with open(LOG_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 4096
            data = b""
            while len(data.splitlines()) <= n_lines and f.tell() > 0:
                seek = max(f.tell() - block, 0)
                f.seek(seek)
                chunk = f.read(size - seek)
                data = chunk + data
                f.seek(seek)
                if seek == 0:
                    break
            lines = data.decode(errors="ignore").splitlines()[-n_lines:]
            return "\n".join(lines)
    except Exception as e:
        return f"(error reading log: {e})"

def tasks_dataframe() -> pd.DataFrame:
    tasks = load_tasks()
    if not tasks:
        return pd.DataFrame(columns=["task_id", "type", "urgency", "task_description"])
    rows = []
    for t in tasks:
        payload = t.get("payload", {}) or {}
        rows.append({
            "task_id": t.get("task_id"),
            "urgency": (payload.get("urgency") or "").lower(),
            "task_description": payload.get("task", ""),  # keep full string
        })
    df = pd.DataFrame(rows)
    # Force dataframe style for wrapping
    return df.style.set_properties(**{'white-space': 'pre-wrap','word-wrap': 'break-word','text-align': 'left'}) # type: ignore


from datetime import datetime

def format_time(ts: str) -> str:
    """Format ISO timestamp into human-friendly string."""
    if not ts:
        return ""
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
        # Example: Sep 24, 2025 · 20:43 UTC
        return dt.strftime("%b %d, %Y · %H:%M UTC")
    except Exception:
        return ts  # fallback: keep raw if parsing fails

def completed_tasks_dataframe() -> pd.DataFrame:
    if not COMPLETED_FILE.exists():
        return pd.DataFrame(columns=[
            "task_id", "type", "urgency", "started_at", "duration_seconds", "task_description"
        ])
    try:
        data = json.loads(COMPLETED_FILE.read_text())
    except json.JSONDecodeError:
        return pd.DataFrame(columns=[
            "task_id", "type", "urgency", "started_at", "duration_seconds", "task_description"
        ])

    rows = []
    for t in data:
        payload = t.get("payload", {}) or {}
        rows.append({
            "task_id": t.get("task_id"),
            # "type": t.get("kind"),
            "urgency": (payload.get("urgency") or "").lower(),
            "started_at": format_time(t.get("started_at", "")),
            "duration_seconds": round(float(t.get("duration_seconds", 0)), 2),
            "task_description": payload.get("original_task", ""),
        })

    try:
        rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    except Exception:
        pass

    df = pd.DataFrame(rows)
    return df.style.set_properties(**{'white-space': 'pre-wrap', 'word-wrap': 'break-word', 'text-align': 'left'})  # type: ignore


# -----------------------------
# UI helpers (cards)
# -----------------------------
def badge(text: str, tone: str) -> str:
    return f"<span class='tm-badge tm-badge-{tone}'>{text}</span>"

def build_status_card_html(override_running: bool | None = None) -> str:
    pid = get_pid()
    actual_running = is_process_running(pid)
    running = actual_running if override_running is None else bool(override_running)
    health = orchestrator_healthy()
    tasks = load_tasks()
    workers_count, worker_names, delegator_up = workers_available()

    exec_html = badge(f"Running · PID {pid}", "success") if running and pid else badge("Stopped", "danger")
    orch_html = badge("Healthy", "success") if health else badge("Unreachable", "danger")
    deleg_html = badge("Healthy", "success") if delegator_up else badge("Unreachable", "danger")
    task_file = f"<code>{TASK_FILE.name}</code>"
    task_count = f"{len(tasks)}"
    workers_html = badge(str(workers_count), "info" if workers_count > 0 else "danger")

    # Badge list for workers
    workers_list_html = ""
    if worker_names:
        items = "".join(f"<span class='tm-badge tm-badge-muted'>{name}</span>" for name in worker_names)
        workers_list_html = f"<div class='tm-worker-list'>{items}</div>"

    return f"""
    <div class="tm-card">
      <div class="tm-card-title">System Status</div>

      <!-- First row -->
      <div class="tm-grid-3">
        <div class="tm-item">
          <div class="tm-label">Orchestrator</div>
          <div class="tm-value">{orch_html}</div>
        </div>
        <div class="tm-item">
          <div class="tm-label">Delegator</div>
          <div class="tm-value">{deleg_html}</div>
        </div>
        <div class="tm-item">
          <div class="tm-label">Workers available</div>
          <div class="tm-value">{workers_html}</div>
        </div>
      </div>

      <!-- Second row -->
      <div class="tm-grid-3">
        <div class="tm-item">
          <div class="tm-label">Executor</div>
          <div class="tm-value">{exec_html}</div>
        </div>
        <div class="tm-item">
          <div class="tm-label">Tasks in file</div>
          <div class="tm-value">{task_count}</div>
        </div>
        <div class="tm-item">
          <div class="tm-label">Task file</div>
          <div class="tm-value">{task_file}</div>
        </div>
      </div>
    </div>
    """




def get_running_task_html() -> str:
    if not RUNNING_FILE.exists():
        return """
        <div class="tm-card">
          <div class="tm-card-title">Current Running Task</div>
          <div class="tm-empty">Waiting for tasks...</div>
        </div>
        """
    try:
        task = json.loads(RUNNING_FILE.read_text())
        task_id = task.get("task_id", "N/A")
        kind = task.get("kind", "N/A")
        payload = task.get("payload", {}) or {}
        urgency = (payload.get("urgency") or "N/A").lower()

        # Main task (always big font)
        original_task = payload.get("original_task", payload.get("task", ""))

        # Show replanned task if one exists, otherwise refined
        attempts_info = task.get("attempts_info", [])
        replanned_task = ""
        if attempts_info:
            # get last attempt's replanned task if available
            last_attempt = attempts_info[-1]
            replanned_task = last_attempt.get("replanned_task", "")

        refined_or_replanned = replanned_task or payload.get("refined_task", "")

        urgency_chip = badge(urgency.capitalize(), {
            "urgent": "danger",
            "high": "warn",
            "medium": "info",
            "low": "muted"
        }.get(urgency, "muted"))

        # Build retry info (older replans as history)
        retries_html = ""
        if attempts_info:
            parts = []
            for attempt in attempts_info[:-1]:  # show only previous replans in history
                try_num = attempt.get("try", "?")
                replanned = attempt.get("replanned_task", "")
                if replanned:
                    parts.append(
                        f"<div class='tm-retry'><b>Attempt {try_num} (Replan):</b><br>{replanned}</div>"
                    )
            if parts:
                retries_html = "<div class='tm-retries'>" + "".join(parts) + "</div>"

        return f"""
        <div class="tm-card">
          <div class="tm-card-title">Current Running Task</div>
          <div class="tm-kv">
            <div><span>Kind</span><code>{kind}</code></div>
            <div><span>Task ID</span><code>{task_id}</code></div>
            <div><span>Urgency</span>{urgency_chip}</div>
          </div>
          <div class="tm-task-original">{original_task}</div>
          {"<div class='tm-task-refined'>" + refined_or_replanned + "</div>" if refined_or_replanned else ""}
          {retries_html}
        </div>
        """
    except Exception:
        return """
        <div class="tm-card">
          <div class="tm-card-title">Current Running Task</div>
          <div class="tm-empty">Waiting for tasks...</div>
        </div>
        """

def status_snapshot() -> Tuple[str, str, List[str]]:
    status_card_html = build_status_card_html()
    log_text = tail_log()
    tasks = load_tasks()
    ids = [t.get("task_id") for t in tasks if t.get("task_id")]
    return status_card_html, log_text, ids

# -----------------------------
# Gradio App
# -----------------------------
with gr.Blocks(
    title="Task Manager Dashboard",
    css=r"""
/* Make full-width */
.gradio-container {
  max-width: 100% !important;
  width: 100% !important;
  padding: 0 20px;
  margin: 0 auto;
}

/* Original task: big bold */
.tm-task-original {
  font-size: 1.35rem;
  font-weight: 800;
  line-height: 1.6;
  margin-top: 10px;
  margin-bottom: 6px;
  color: #f8fafc;
}

/* Refined task: smaller and muted */
.tm-task-refined {
  font-size: 1.05rem;
  font-weight: 500;
  line-height: 1.45;
  margin-bottom: 10px;
  color: #cbd5e1;
}

/* Retry attempts */
.tm-retries {
  border-top: 1px dashed rgba(255,255,255,.15);
  margin-top: 10px;
  padding-top: 8px;
}
.tm-retry {
  font-size: 0.95rem;
  margin-bottom: 6px;
  color: #fbbf24; /* amber/yellow to stand out */
}
.tm-retry b {
  color: #fcd34d;
}

/* ----- Layout polish ----- */
#main-title h1 {
  font-size: 2.35rem !important;
  font-weight: 900;
  letter-spacing: .2px;
  margin-bottom: .25rem;
  background: linear-gradient(90deg, #ffffff 0%, #b9cdfa 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}

/* Sticky toolbar */
#tm-toolbar {
  position: sticky; top: 0; z-index: 10;
  backdrop-filter: blur(6px);
  background: rgba(20,20,28,.55);
  border: 1px solid rgba(255,255,255,.06);
  border-radius: 14px;
  padding: 10px;
  box-shadow: 0 6px 24px rgba(0,0,0,.35);
}

/* Buttons */
#tm-toolbar .gr-button {
  border-radius: 12px !important;
  font-weight: 700 !important;
  padding: 10px 14px !important;
  border: 1px solid rgba(255,255,255,.08) !important;
  transition: transform .06s ease, box-shadow .12s ease;
}
#tm-toolbar .gr-button:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(0,0,0,.25); }

/* Cards */
.tm-card {
  border: 1px solid rgba(255,255,255,0.08);
  background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.03));
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 6px 24px rgba(0,0,0,0.35);
}
.tm-card + .tm-card { margin-top: 12px; }
.tm-card-title {
  font-size: 1.05rem;
  font-weight: 800;
  letter-spacing: .2px;
  margin-bottom: 12px;
  opacity: .95;
}

/* Grid */
.tm-grid-4 {
  display: grid; gap: 12px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
@media (max-width: 1100px) { .tm-grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px)  { .tm-grid-4 { grid-template-columns: 1fr; } }

.tm-item {
  border: 1px dashed rgba(255,255,255,0.09);
  border-radius: 12px;
  padding: 12px;
}
.tm-label { font-size: .8rem; opacity: .7; margin-bottom: 2px; }
.tm-value { font-size: 1rem; font-weight: 800; }

/* Badges */
.tm-badge {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: .78rem; font-weight: 800; letter-spacing: .2px;
  padding: 6px 10px; border-radius: 999px;
  border: 1px solid transparent;
}
.tm-badge-success { background: rgba(34,197,94,.15); border-color: rgba(34,197,94,.25); color: #86efac; }
.tm-badge-danger  { background: rgba(244,63,94,.15); border-color: rgba(244,63,94,.25); color: #fda4af; }
.tm-badge-warn    { background: rgba(234,179,8,.18); border-color: rgba(234,179,8,.28); color: #fde68a; }
.tm-badge-info    { background: rgba(59,130,246,.18); border-color: rgba(59,130,246,.28); color: #bfdbfe; }
.tm-badge-muted   { background: rgba(148,163,184,.16); border-color: rgba(148,163,184,.28); color: #e2e8f0; }

/* Key/Value strip */
.tm-kv {
  display: grid; gap: 10px; margin-bottom: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.tm-kv > div {
  display: flex; align-items: center; justify-content: space-between;
  border: 1px dashed rgba(255,255,255,.09); border-radius: 10px; padding: 8px 10px;
}
.tm-kv span { opacity: .7; font-size: .82rem; }

/* Task description emphasis */
.tm-task-desc {
  font-size: 1.18rem; font-weight: 700; line-height: 1.55;
  padding: 14px 14px; border-radius: 12px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
}

/* Subsection headings */
.gr-markdown h3 {
  font-size: 1.02rem; letter-spacing: .2px; font-weight: 800;
  margin: 14px 0 8px 0;
}

/* Tables */
div[data-testid="dataframe"] table {
  border-radius: 12px; overflow: hidden; font-size: .9rem;
}
div[data-testid="dataframe"] thead th {
  background: rgba(255,255,255,.06) !important;
  font-weight: 800 !important;
}
div[data-testid="dataframe"] tbody tr:hover td {
  background: rgba(255,255,255,.03) !important;
}

/* Inputs */
textarea, input, select {
  border-radius: 12px !important;
}

/* Logs box */
#logs-box textarea {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace !important;
  line-height: 1.35 !important;
  border-radius: 14px !important;
  border: 1px solid rgba(255,255,255,.08) !important;
  background: rgba(0,0,0,.35) !important;
}

.tm-grid-3 {
  display: grid; 
  gap: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
@media (max-width: 900px) { .tm-grid-3 { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .tm-grid-3 { grid-template-columns: 1fr; } }

.tm-worker-list {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}


"""
) as demo:
    gr.Markdown(
        """
        # Task Manager Dashboard  
        <span style="font-size:0.9rem; opacity:0.7;">
        Easily Manage Tasks for <b>AgentBridge</b>
        </span>
        """,
        elem_id="main-title"
    )

    with gr.Row(elem_id="tm-toolbar"):
        start_btn = gr.Button("Start execution")
        stop_btn = gr.Button("Stop execution")
        clear_log_btn = gr.Button("Clear log")
        refresh_btn = gr.Button("Refresh now")

    # Cards
    status_card = gr.HTML("<div class='tm-card'>Loading status…</div>")
    running_card = gr.HTML("<div class='tm-card'>Loading running task…</div>")

    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("### Current Tasks")
            task_table = gr.Dataframe(
                headers=["Task ID", "Priority", "Task Description"],
                interactive=False,
                wrap=True,      
            )
            ids_multi = gr.CheckboxGroup(choices=[], label="Select tasks to delete by ID")
            delete_btn = gr.Button("Delete selected")
        with gr.Column(scale=1):
            gr.Markdown("### Add Task")
            kind_in = gr.Dropdown(["task", "error_message"], value="task", label="Kind")
            urgency_in = gr.Dropdown(PRIORITIES, value="medium", label="Urgency")
            description_in = gr.Textbox(label="Task Description", placeholder="Describe the task to enqueue…")
            add_btn = gr.Button("Add to task file")

    with gr.Row():
        with gr.Column():
            gr.Markdown("### Completed Tasks")
            completed_table = gr.Dataframe(
                headers=["task_id", "type", "urgency", "started_at", "duration_seconds", "task_description"],
                interactive=False,
                wrap=True,
            )

    gr.Markdown("### Execution Logs")
    log_box = gr.Textbox(value="", lines=16, max_lines=30, interactive=False, label="Logs", elem_id="logs-box")

    # -----------------------------
    # Event handlers
    # -----------------------------
    def refresh_all():
        status_html, log_text, ids = status_snapshot()
        df = tasks_dataframe()
        df_completed = completed_tasks_dataframe()
        running_task_html = get_running_task_html()
        return status_html, running_task_html, log_text, df, gr.update(choices=ids), df_completed

    def on_start():
        _level, msg = start_watcher()
        return (msg,) + refresh_all()

    def on_stop():
        # Stop process and show "Stopped" in UI immediately (optimistic UI)
        _level, msg = stop_watcher()
        forced_status_html = build_status_card_html(override_running=False)
        # Get latest for the rest of the widgets
        _status_html, running_task_html, log_text, df, ids_update, df_completed = refresh_all()
        return msg, forced_status_html, running_task_html, log_text, df, ids_update, df_completed

    def on_clear_log():
        try:
            if LOG_FILE.exists():
                # Open in write mode and truncate to zero length
                LOG_FILE.write_text("")
            note = "Log cleared (file emptied, not deleted)"
        except Exception as e:
            note = f"Failed to clear log: {e}"
        return (note,) + refresh_all()

    def on_refresh():
        return refresh_all()

    def on_add(kind: str, urgency: str, description: str):
        payload = {
            "task": (description or "").strip(),
            "urgency": (urgency or "medium").lower()
        }
        add_task(kind, urgency, payload)
        status_html, running_task_html, log_text, df, ids_update, df_completed = refresh_all()
        return status_html, running_task_html, log_text, df, ids_update, df_completed, "Task added"

    def on_delete(ids: List[str] | None):
        n = remove_tasks(ids or [])
        status_html, running_task_html, log_text, df, ids_update, df_completed = refresh_all()
        return f"Deleted {n} task(s)", status_html, running_task_html, log_text, df, ids_update, df_completed

    # Action outputs
    start_out = gr.Textbox(label="Action result", interactive=False)
    stop_out = gr.Textbox(interactive=False, visible=False)
    clear_out = gr.Textbox(interactive=False, visible=False)
    delete_out = gr.Textbox(label="Action result", interactive=False)
    add_out = gr.Textbox(label="Add result", interactive=False)

    # Wire events
    start_btn.click(on_start, outputs=[start_out, status_card, running_card, log_box, task_table, ids_multi, completed_table])
    stop_btn.click(on_stop, outputs=[stop_out, status_card, running_card, log_box, task_table, ids_multi, completed_table])
    clear_log_btn.click(on_clear_log, outputs=[clear_out, status_card, running_card, log_box, task_table, ids_multi, completed_table])
    refresh_btn.click(on_refresh, outputs=[status_card, running_card, log_box, task_table, ids_multi, completed_table])
    add_btn.click(on_add, inputs=[kind_in, urgency_in, description_in],
                  outputs=[status_card, running_card, log_box, task_table, ids_multi, completed_table, add_out])
    delete_btn.click(on_delete, inputs=[ids_multi],
                     outputs=[delete_out, status_card, running_card, log_box, task_table, ids_multi, completed_table])

    # Initial + timer refresh
    demo.load(on_refresh, outputs=[status_card, running_card, log_box, task_table, ids_multi, completed_table])
    gr.Timer(2.0).tick(on_refresh, outputs=[status_card, running_card, log_box, task_table, ids_multi, completed_table])

if __name__ == "__main__":
    if not TASK_FILE.exists():
        save_tasks([])
    demo.queue()    
    host, port = _tasks_bind()
    demo.launch(server_name=host, server_port=port)
