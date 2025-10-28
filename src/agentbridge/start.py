"""Start AgentBridge components (app, MCP, orchestrator, dashboard, and
selected worker agents) with one command.

Usage Examples:
  uv run start.py                             # Run app + MCP + orchestrator + dashboard
  uv run start.py --all-workers               # Run all workers in addition to the core components
  uv run start.py -w describer                # Run only the 'describer' worker
  uv run start.py -w describer -w spawner     # Run multiple workers
  uv run start.py --list-workers              # List all detected workers and exit
  uv run start.py --no-app                    # Skip the app
  uv run start.py --no-dashboard              # Skip the dashboard
  uv run start.py --no-mcp --no-orchestrator  # Skip MCP and orchestrator (custom setup)

Optional Flags:
  --hide-access   Suppress noisy HTTP request logs (GET/POST lines)

Controls:
  q + Enter       Graceful shutdown
  Ctrl-C once     Graceful shutdown
  Ctrl-C twice    Immediate hard kill
"""

import argparse
import asyncio
import os
import secrets
import signal
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Root paths and component locations
ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "app"
MCP_CMD = ["uv", "run", "tools/mcp_server.py"]
ORCH_DIR = ROOT / "agents" / "supervisors" / "orchestrator"
ORCH_CMD = ["uv", "run", "server.py"]
WORKERS_ROOT = ROOT / "agents" / "workers"
DASH_DIR = ROOT / "tasks"
DASH_CMD = ["uv", "run", "dashboard.py"]

# ANSI color codes for prefixed process output
COLOR_CODES = [
    "\033[38;5;39m",   # blue
    "\033[38;5;208m",  # orange
    "\033[38;5;70m",   # green
    "\033[38;5;197m",  # red/pink
    "\033[38;5;141m",  # purple
    "\033[38;5;244m",  # gray
    "\033[38;5;214m",  # amber
    "\033[38;5;33m",   # deep blue
]
RESET = "\033[0m"

# Handle platform-specific process group creation
IS_WINDOWS = os.name == "nt"
CREATE_NEW_PROCESS_GROUP = getattr(asyncio.subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
try:
    import subprocess as _subp
    CREATE_NEW_PROCESS_GROUP = getattr(
        _subp, "CREATE_NEW_PROCESS_GROUP", CREATE_NEW_PROCESS_GROUP
    )
except Exception:
    pass

# Shared shutdown token so child processes can detect coordinated termination
SHUTDOWN_TOKEN = os.environ.get("SHUTDOWN_TOKEN") or secrets.token_hex(16)

# Used to hide HTTP request logs when --hide-access is enabled
ACCESS_PATTERNS = (
    ' "GET ',
    ' "POST ',
    ' "PUT ',
    ' "DELETE ',
    ' "PATCH ',
    ' - "GET ',
    ' - "POST ',
    ' - "PUT ',
    ' - "DELETE ',
    ' - "PATCH ',
)
NOISY_PATH_SNIPPETS = (
    "/__ui__",
    "/events/get",
    "/message/pending",
    "/conversation/list",
    "/task/list",
    "/health",
)


def _resolve_frontend_urls() -> tuple[str, str]:
    """Figure out which URLs to print for the frontend (app and dashboard).
    Priority order: environment variables → config.yaml → hardcoded defaults.
    """
    import yaml

    app_url = os.environ.get("DELEGATOR_URL", "http://localhost:12000/")
    dash_url = os.environ.get("TASKS_URL", "http://localhost:14000/")

    # Try to read from config.yaml if available
    try:
        cfg_root = Path(__file__).resolve().parents[2]
        cfg_path = cfg_root / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            if isinstance(cfg, dict):
                d = cfg.get("delegator") or {}
                if isinstance(d, dict) and d.get("url"):
                    app_url = d["url"]
                t = cfg.get("tasks") or {}
                if isinstance(t, dict) and t.get("url"):
                    dash_url = t["url"]
    except Exception:
        pass  # ignore errors and fall back to env/defaults

    # Normalize to include trailing slash for clean output
    if not app_url.endswith("/"):
        app_url += "/"
    if not dash_url.endswith("/"):
        dash_url += "/"

    return app_url, dash_url


def find_workers() -> List[str]:
    """Detect available worker agents under agents/workers/"""
    if not WORKERS_ROOT.exists():
        return []
    workers = []
    for p in sorted(WORKERS_ROOT.iterdir()):
        if p.is_dir() and not p.name.startswith("_"):
            if (
                (p / "pyproject.toml").exists()
                or (p / "__init__.py").exists()
                or (p / "main.py").exists()
            ):
                workers.append(p.name)
    return workers


async def stream_output(
    name: str,
    proc: asyncio.subprocess.Process,
    color: str,
    no_color: bool = False,
    hide_access: bool = False,
    suppressed_counter: Dict[str, int] | None = None,
):
    """Continuously read a subprocess's stdout and print it with a prefixed label.
    Can optionally suppress HTTP access logs to reduce clutter.
    """
    prefix = f"[{name}]".ljust(14)
    suppressed = 0
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors="replace")

            if hide_access and (
                any(p in text for p in ACCESS_PATTERNS)
                or any(s in text for s in NOISY_PATH_SNIPPETS)
            ):
                suppressed += 1
                continue

            if no_color:
                sys.stdout.write(f"{prefix} {text}")
            else:
                sys.stdout.write(f"{color}{prefix}{RESET} {text}")
            sys.stdout.flush()
    except Exception:
        pass
    finally:
        if suppressed_counter is not None and suppressed:
            suppressed_counter[name] = suppressed_counter.get(name, 0) + suppressed


async def spawn(
    name: str,
    cwd: Path,
    cmd: List[str],
    env: dict | None = None,
    no_color: bool = False,
    color: str = "",
    hide_access: bool = False,
    suppressed_counter: Dict[str, int] | None = None,
):
    """Launch a subprocess with its own process group, capture output, 
    and stream logs asynchronously."""
    env = (env or os.environ.copy()).copy()
    env["SHUTDOWN_TOKEN"] = SHUTDOWN_TOKEN
    env.setdefault("PYTHONUNBUFFERED", "1")  # ensures unbuffered logging

    if IS_WINDOWS:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            creationflags=CREATE_NEW_PROCESS_GROUP if CREATE_NEW_PROCESS_GROUP else 0,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            preexec_fn=os.setsid,  # new process group (Unix)
        )
    asyncio.create_task(
        stream_output(
            name,
            proc,
            color,
            no_color=no_color,
            hide_access=hide_access,
            suppressed_counter=suppressed_counter,
        )
    )
    return proc


async def graceful_terminate(procs: List[asyncio.subprocess.Process], force_now=False):
    """Try to shut down all child processes cleanly:
    INT → TERM → KILL, in reverse startup order.
    """

    def _kill_group(proc: asyncio.subprocess.Process, sig):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except ProcessLookupError:
            pass
        except ProcessPermissionError:  # type: ignore
            try:
                proc.send_signal(sig)
            except ProcessLookupError:
                pass

    # If already in "force kill" mode, skip straight to kill
    if force_now:
        for p in reversed(procs):
            if p.returncode is None:
                try:
                    if IS_WINDOWS:
                        p.kill()
                    else:
                        _kill_group(p, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        return

    # Step 1: send interrupt signals
    for p in reversed(procs):
        if p.returncode is not None:
            continue
        try:
            if IS_WINDOWS:
                if hasattr(signal, "CTRL_BREAK_EVENT"):
                    p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                else:
                    p.terminate()
            else:
                _kill_group(p, signal.SIGINT)
        except ProcessLookupError:
            pass

    try:
        await asyncio.wait([asyncio.create_task(p.wait()) for p in procs], timeout=8)
    except Exception:
        pass

    # Step 2: escalate to TERM
    for p in reversed(procs):
        if p.returncode is not None:
            continue
        try:
            if IS_WINDOWS:
                p.terminate()
            else:
                _kill_group(p, signal.SIGTERM)
        except ProcessLookupError:
            pass

    try:
        await asyncio.wait([asyncio.create_task(p.wait()) for p in procs], timeout=6)
    except Exception:
        pass

    # Step 3: force kill any survivors
    for p in reversed(procs):
        if p.returncode is not None:
            continue
        try:
            if IS_WINDOWS:
                p.kill()
            else:
                _kill_group(p, signal.SIGKILL)
        except ProcessLookupError:
            pass


def build_plan(args) -> List[Tuple[str, Path, List[str]]]:
    """Build an execution plan: list of (name, cwd, command) tuples 
    for the components that should be launched based on CLI args.
    """
    plan: List[Tuple[str, Path, List[str]]] = []

    if args.app:
        plan.append(("app", APP_DIR, ["uv", "run", "main.py"]))
    if args.mcp:
        plan.append(("mcp", ROOT, MCP_CMD))
    if args.orchestrator:
        plan.append(("orchestrator", ORCH_DIR, ORCH_CMD))
    if args.dashboard:
        plan.append(("dashboard", DASH_DIR, DASH_CMD))

    workers_available = find_workers()
    if args.list_workers:
        print("Detected workers:", ", ".join(workers_available) or "(none)")
        sys.exit(0)

    selected = []
    if args.all_workers:
        selected = workers_available
    elif args.workers:
        unknown = [w for w in args.workers if w not in workers_available]
        if unknown:
            print(f"Unknown worker(s): {', '.join(unknown)}")
            print("Available:", ", ".join(workers_available) or "(none)")
            sys.exit(2)
        selected = args.workers

    for w in selected:
        plan.append((f"worker-{w}", WORKERS_ROOT / w, ["uv", "run", "."]))

    if not plan:
        print("Nothing to run. Use --help for options.")
        sys.exit(1)

    return plan


async def wait_for_quit_key(stop_event: asyncio.Event):
    """Wait for the user to type 'q' or 'quit'/'exit' and then set stop_event."""
    loop = asyncio.get_event_loop()

    def _readline():
        return sys.stdin.readline()

    while not stop_event.is_set():
        line = await loop.run_in_executor(None, _readline)
        if not line:
            break
        if line.strip().lower() in {"q", "quit", "exit"}:
            stop_event.set()
            break


def setup_env_files():
    """Rebuild .env files and saved_agents.json from config.yaml and base .env.
    This ensures consistent environment variables across app, tasks, and all agents.
    """
    import json
    from pathlib import Path
    import yaml

    project_root = Path(__file__).resolve().parents[2]
    agentbridge_root = Path(__file__).resolve().parent

    env_file = project_root / ".env"
    config_yaml = project_root / "config.yaml"
    app_dir = agentbridge_root / "app"
    tasks_dir = agentbridge_root / "tasks"
    supervisors_dir = agentbridge_root / "agents" / "supervisors"
    workers_dir = agentbridge_root / "agents" / "workers"
    saved_agents_json = app_dir / "saved_agents.json"

    def load_env_keys():
        if not env_file.exists() or env_file.stat().st_size == 0:
            print(
                f"\033[38;5;197m[system]{RESET} ❌ .env file missing or empty at {env_file}"
            )
            return {}
        with open(env_file, "r") as f:
            lines = f.readlines()
        env = {}
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"')
        return env

    def load_config():
        if not config_yaml.exists():
            print(
                f"\033[38;5;197m[system]{RESET} ❌ config.yaml not found at {config_yaml}"
            )
            return {}
        with open(config_yaml, "r") as f:
            return yaml.safe_load(f)

    def build_agent_configs(agent_data: dict) -> str:
        lines = ["\n# Agent Configs"]
        for name, info in agent_data.items():
            lines.append(f'{name.upper()}_URL="{info["url"]}"')
            lines.append(f'{name.upper()}_MODEL="{info["model"]}"')
            lines.append(f'{name.upper()}_PROVIDER="{info["provider"]}"')
        return "\n".join(lines)

    def build_system_config(config: dict) -> str:
        lines = []
        if "mcp" in config:
            lines.append("\n# MCP Config")
            lines.append(f'MCP_URL="{config["mcp"].get("url", "")}"')
            lines.append(f'MCP_TRANSPORT="{config["mcp"].get("transport", "")}"')
        if "tasks" in config:
            lines.append("\n# Task Dashboard")
            lines.append(f'TASKS_URL="{config["tasks"].get("url", "")}"')
        return "\n".join(lines)

    def write_env_file(path: Path, content: str):
        with open(path / ".env", "w") as f:
            f.write(content)

    def get_agent_dirs(base: Path):
        return [d for d in base.iterdir() if d.is_dir() and not d.name.startswith("__")]

    # === Setup begins ===
    keys = load_env_keys()
    if not keys:
        return
    config = load_config()
    if not config:
        return

    agent_data = {
        k: v
        for k, v in config.items()
        if isinstance(v, dict) and all(x in v for x in ["url", "model", "provider"])
    }
    agent_config_block = build_agent_configs(agent_data)
    system_config_block = build_system_config(config)

    # Write .env for tasks
    task_env = f"""#groqcloud
GROQ_API_KEY="{keys.get('GROQ_API_KEY', '')}"

#Google
GOOGLE_API_KEY="{keys.get('GOOGLE_API_KEY', '')}"

#OpenAI
OPENAI_API_KEY="{keys.get('OPENAI_API_KEY', '')}"

#langchain
LANGSMITH_API_KEY="{keys.get('LANGSMITH_API_KEY', '')}"
LANGCHAIN_PROJECT=task_manager
LANGCHAIN_TRACING_V2=true

{agent_config_block}
{system_config_block}
"""
    write_env_file(tasks_dir, task_env)
    print(f"\033[38;5;82m[system]{RESET} ✅ Wrote .env in tasks")

    # Write .env for app
    app_env = f"""#groqcloud
GROQ_API_KEY="{keys.get('GROQ_API_KEY', '')}"

#Google
GOOGLE_API_KEY="{keys.get('GOOGLE_API_KEY', '')}"

#OpenAI
OPENAI_API_KEY="{keys.get('OPENAI_API_KEY', '')}"

#langchain
LANGSMITH_API_KEY="{keys.get('LANGSMITH_API_KEY', '')}"
LANGCHAIN_PROJECT=App
LANGCHAIN_TRACING_V2=true

{agent_config_block}
{system_config_block}
"""
    write_env_file(app_dir, app_env)
    print(f"\033[38;5;82m[system]{RESET} ✅ Wrote .env in app")

    # Write .env for each agent (supervisors + workers)
    agent_dirs = get_agent_dirs(supervisors_dir) + get_agent_dirs(workers_dir)
    for agent_dir in agent_dirs:
        name = agent_dir.name
        env_content = f"""#groqcloud
GROQ_API_KEY="{keys.get('GROQ_API_KEY', '')}"

#Google
GOOGLE_API_KEY="{keys.get('GOOGLE_API_KEY', '')}"

#OpenAI
OPENAI_API_KEY="{keys.get('OPENAI_API_KEY', '')}"

#langchain
LANGSMITH_API_KEY="{keys.get('LANGSMITH_API_KEY', '')}"
LANGCHAIN_PROJECT={name}
LANGCHAIN_TRACING_V2=true

{agent_config_block}
{system_config_block}
"""
        write_env_file(agent_dir, env_content)
        print(f"\033[38;5;82m[system]{RESET} ✅ Wrote .env for agent: {name}")

    # Update saved_agents.json (used by UI to show available workers)
    worker_agents = {
        k: v
        for k, v in agent_data.items()
        if k not in {"orchestrator", "delegator", "tasks"}
    }
    saved_agents = {
        "agents": [
            {
                "name": k.replace("_", " ")
                .title()
                .replace("Sdf", "(SDF)")
                .replace("Urdf", "(URDF)")
                .replace("Agv", "(AGV)"),
                "address": v["url"].replace("http://", ""),
            }
            for k, v in worker_agents.items()
        ]
    }
    with open(saved_agents_json, "w") as f:
        json.dump(saved_agents, f, indent=2)
    print(f"\033[38;5;82m[system]{RESET} ✅ Updated saved_agents.json")


async def main():
    parser = argparse.ArgumentParser(
        description="Run app + MCP + orchestrator + dashboard + selected workers."
    )
    parser.add_argument("--no-app", dest="app", action="store_false", help="Do not run the app.")
    parser.add_argument("--no-mcp", dest="mcp", action="store_false", help="Do not run MCP.")
    parser.add_argument(
        "--no-orchestrator", dest="orchestrator", action="store_false", help="Do not run the orchestrator."
    )
    parser.add_argument("--no-dashboard", dest="dashboard", action="store_false", help="Do not run the dashboard.")
    parser.add_argument("--all-workers", action="store_true", help="Run all detected workers.")
    parser.add_argument(
        "-w", "--worker", dest="workers", action="append", help="Run a specific worker (can be repeated)."
    )
    parser.add_argument("--list-workers", action="store_true", help="List detected workers and exit.")
    parser.add_argument("--no-color", action="store_true", help="Disable colored prefixes.")
    parser.add_argument(
        "--hide-access", action="store_true", help="Hide noisy HTTP access logs (GET/POST lines)."
    )
    parser.add_argument("--grace-int", type=float, default=8.0, help="Seconds to wait after INT before TERM.")
    parser.add_argument("--grace-term", type=float, default=6.0, help="Seconds to wait after TERM before KILL.")
    parser.set_defaults(app=True, mcp=True, orchestrator=True, dashboard=True)

    args = parser.parse_args()
    setup_env_files()
    plan = build_plan(args)

    print("Starting:")
    for name, cwd, cmd in plan:
        print(f"  {name:14}  (cwd={cwd.relative_to(ROOT)!s})  $ {' '.join(cmd)}")

    print("\nPress 'q' + Enter for graceful shutdown.\n")

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()
    force_kill_event = asyncio.Event()

    # Signal handling: first interrupt triggers graceful stop,
    # second interrupt escalates to immediate force kill
    def _handle_first_stop():
        if not stop_event.is_set():
            stop_event.set()

    def _handle_force_kill():
        if stop_event.is_set() and not force_kill_event.is_set():
            force_kill_event.set()
        else:
            _handle_first_stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_first_stop)
        except NotImplementedError:
            pass
    try:
        loop.add_signal_handler(signal.SIGINT, _handle_force_kill)
    except Exception:
        pass

    suppressed_counter: Dict[str, int] = {}
    procs: List[asyncio.subprocess.Process] = []
    try:
        # Start all processes in the plan
        for i, (name, cwd, cmd) in enumerate(plan):
            color = COLOR_CODES[i % len(COLOR_CODES)]
            p = await spawn(
                name,
                cwd,
                cmd,
                no_color=args.no_color,
                color=color,
                hide_access=args.hide_access,
                suppressed_counter=suppressed_counter,
            )
            procs.append(p)

        # Print friendly URLs for app and dashboard
        app_url, dash_url = _resolve_frontend_urls()
        print()
        if any(n == "app" for n, _, _ in plan):
            print(f"\033[38;5;82m[system]{RESET} AgentBridge UI (delegator):  {app_url}")
        if any(n == "dashboard" for n, _, _ in plan):
            print(f"\033[38;5;214m[system]{RESET} Task Dashboard:          {dash_url}")
        print()

        wait_tasks = [asyncio.create_task(p.wait()) for p in procs]
        quit_task = asyncio.create_task(wait_for_quit_key(stop_event))
        stop_task = asyncio.create_task(stop_event.wait())

        done, pending = await asyncio.wait(
            wait_tasks + [stop_task, quit_task], return_when=asyncio.FIRST_COMPLETED
        )
        if stop_event.is_set():
            print("\nReceived stop request. Shutting down…")
        else:
            rc = None
            for d in done:
                try:
                    rc = d.result()
                except Exception:
                    rc = 1
                break
            print(f"\nA process exited (code {rc}). Shutting down the rest…")

        if force_kill_event.is_set():
            await graceful_terminate(procs, force_now=True)
        else:
            await graceful_terminate(procs)

    finally:
        await graceful_terminate(procs, force_now=True)
        if suppressed_counter:
            print()
            for n, cnt in suppressed_counter.items():
                if cnt:
                    print(
                        f"\033[38;5;244m[system]{RESET} suppressed {cnt} access log line(s) from {n}"
                    )


def cli_entry():
    """Entry point for CLI (used when installed as a package)."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
