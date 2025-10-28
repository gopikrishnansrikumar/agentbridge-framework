import heapq
import itertools
import json
import os
import random
import signal
import string
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from llm_eval import evaluate_and_replan_with_llm, refine_task, refine_replan_task

# -------------------- Configuration --------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TASK_FILE = Path("task_lists/task_list.json")
COMPLETED_FILE = Path("task_lists/completed_tasks.json")
RUNNING_FILE = Path("task_lists/running_task.json")

PLAN_FILE = (
    Path(__file__).parent.parent / "agents/supervisors/orchestrator/tasks/logs/plan.md"
)
LOG_FILE = (
    Path(__file__).parent.parent
    / "agents/supervisors/orchestrator/tasks/logs/conversation_log.md"
)
CONVERSATION_ID_FILE = (
    Path(__file__).parent.parent
    / "agents/supervisors/orchestrator/tasks/logs/conversation_id.txt"
)


def _orch_base() -> str:
    base = (os.getenv("ORCHESTRATOR_URL") or "http://localhost:10000").strip()
    if "://" not in base:
        base = "http://" + base
    return base.rstrip("/")


POLL_INTERVAL = int(os.getenv("TASKS_POLL_INTERVAL", "2"))
MAX_ATTEMPTS = int(os.getenv("TASKS_MAX_ATTEMPTS", "3"))
COOL_OFF_INTERVAL = int(os.getenv("TASKS_COOL_OFF_INTERVAL", "30")) 
PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

ORCH_HEALTH_URL = _orch_base() + "/health"


# -------------------- Utilities ------------------------
def load_tasks():
    try:
        with TASK_FILE.open("r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_tasks(task_list):
    with TASK_FILE.open("w") as f:
        json.dump(task_list, f, indent=4)


def append_completed_task(task):
    completed = []
    if COMPLETED_FILE.exists():
        try:
            completed = json.loads(COMPLETED_FILE.read_text())
        except json.JSONDecodeError:
            pass
    completed.append(task)
    with COMPLETED_FILE.open("w") as f:
        json.dump(completed, f, indent=4)


def set_running_task(task):
    with RUNNING_FILE.open("w") as f:
        json.dump(task, f, indent=4)


def clear_running_task():
    RUNNING_FILE.unlink(missing_ok=True)


def check_orchestrator_health():
    try:
        r = requests.get(ORCH_HEALTH_URL, timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False


def get_priority(task):
    urgency = (task.get("payload", {}) or {}).get("urgency", "medium")
    return PRIORITY_ORDER.get(urgency.lower(), PRIORITY_ORDER["medium"])


def execute_task_with_orchestrator(task):
    tid = task.get("task_id", "?")
    payload = task.get("payload", {})
    orch_url = _orch_base() + "/run"
    task_body = {
        "task": payload.get("task"),
        "use_async": payload.get("use_async", True),
    }

    print(f"[DETAILS] {task_body}")
    print(f"\n[ORCHESTRATOR] Sending task {tid} to orchestrator… ({orch_url})")

    try:
        response = requests.post(orch_url, json=task_body, timeout=600)
        if response.status_code == 200:
            data = response.json()
            status = (data.get("status") or "").lower()
            print(f"[RESPONSE] Task {tid} response: {data}")
            return status == "completed"
        else:
            print(f"[FAILURE] Orchestrator returned {response.status_code}: {response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to send task {tid}: {e}")
        return False


# -------------------- Main Loop ------------------------
_stop = False


def _handle_stop(_sig, _frame):
    global _stop
    _stop = True
    print("\n[SHUTDOWN] Stop signal received. Finishing current cycle...")


def generate_task_id(existing_ids=None):
    existing_ids = existing_ids or set()
    while True:
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        tid = f"Task-{suffix}"
        if tid not in existing_ids:
            return tid


def main():
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    seq = itertools.count()
    seen_ids = set()
    task_queue = []
    idle_state = False

    print("👀 Watching for tasks in", TASK_FILE)
    try:
        while not _stop:
            tasks = load_tasks()

            all_existing_ids = {t.get("task_id") for t in tasks if t.get("task_id")}
            changed = False
            for t in tasks:
                if not t.get("task_id"):
                    t["task_id"] = generate_task_id(all_existing_ids)
                    all_existing_ids.add(t["task_id"])
                    changed = True
            if changed:
                save_tasks(tasks)

            for t in tasks:
                tid = t.get("task_id")
                if tid and tid not in seen_ids:
                    prio = get_priority(t)
                    heapq.heappush(task_queue, (prio, next(seq), tid, t))
                    seen_ids.add(tid)
                    print(f"[QUEUE] Added {tid} with priority {prio}")

            if task_queue:
                if idle_state:
                    print("[RESUME] Tasks available again.")
                idle_state = False

                if check_orchestrator_health():
                    prio, _order, _tid, task = heapq.heappop(task_queue)

                    task.setdefault("attempts", 0)
                    task_id = task.get("task_id")
                    payload = task.get("payload", {})
                    task_text = payload.get("task", "")

                    started_epoch = time.time()
                    started_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started_epoch))

                    # --- Initial refinement (only once) ---
                    if not payload.get("refined", False):
                        print(f"[REFINE] Refining task {task_id} with LLM...")
                        refined = refine_task(task_text).strip()
                        if not refined:
                            print(f"[LLM ERROR] Refined task is empty — retrying later.")
                            task["attempts"] += 1
                            if task["attempts"] < MAX_ATTEMPTS:
                                heapq.heappush(task_queue, (prio, next(seq), task_id, task))
                            else:
                                task["status"] = "Failed (empty refinement)"
                                task["started_at"] = started_at_iso
                                task["duration_seconds"] = round(time.time() - started_epoch, 3)
                                append_completed_task(task)
                                updated_tasks = [x for x in load_tasks() if x.get("task_id") != task_id]
                                save_tasks(updated_tasks)
                                seen_ids.discard(task_id)
                            continue

                        if "original_task" not in task["payload"]:
                            task["payload"]["original_task"] = task_text
                        task["payload"]["refined_task"] = refined
                        task["payload"]["task"] = refined
                        task["payload"]["refined"] = True

                    # --- Execution & Retry Loop ---
                    success = False
                    while task["attempts"] < MAX_ATTEMPTS and not success:
                        # Execute
                        set_running_task(task)
                        execute_task_with_orchestrator(task)
                        clear_running_task()

                        # Evaluate
                        print(f"[EVAL] Evaluating results of task {task_id} with LLM...")
                        eval_result = evaluate_and_replan_with_llm(
                            task_executed=task["payload"]["task"],
                            plan_path=str(PLAN_FILE),
                            conversation_log_path=str(LOG_FILE),
                            conversation_id_path=str(CONVERSATION_ID_FILE),
                        ).strip()

                        print(f"[LLM] Evaluation Result: {eval_result}")

                        if not eval_result:
                            eval_result = "❌ No progress detected."

                        attempt_info = {
                            "try": task["attempts"] + 1,
                            "refined_task": task["payload"].get("refined_task"),
                            "evaluation_result": eval_result,
                        }

                        if eval_result.startswith("✅"):
                            success = True
                            task["status"] = "Success"
                            task["started_at"] = started_at_iso
                            task["duration_seconds"] = round(time.time() - started_epoch, 3)
                            append_completed_task(task)
                            updated_tasks = [x for x in load_tasks() if x.get("task_id") != task_id]
                            save_tasks(updated_tasks)
                            seen_ids.discard(task_id)
                            print(f"[✅ SUCCESS] Task {task_id} completed.")
                        else:
                            # Failed → replan + refine replan
                            attempt_info["replanned_task"] = eval_result
                            print(f"[⚙️ REFINING REPLAN] Refining failed plan for {task_id}...")
                            refined_replan = refine_replan_task(eval_result).strip()
                            if refined_replan:
                                task["payload"]["task"] = refined_replan
                                attempt_info["refined_replan_task"] = refined_replan
                                print(f"[REFINED TASK] {refined_replan}")
                            else:
                                task["payload"]["task"] = eval_result

                            task["attempts"] += 1
                            if task["attempts"] >= MAX_ATTEMPTS:
                                task["status"] = "Failed"
                                task["started_at"] = started_at_iso
                                task["duration_seconds"] = round(time.time() - started_epoch, 3)
                                append_completed_task(task)
                                updated_tasks = [x for x in load_tasks() if x.get("task_id") != task_id]
                                save_tasks(updated_tasks)
                                seen_ids.discard(task_id)
                                print(f"[❌ FAILED] Task {task_id} exhausted {MAX_ATTEMPTS} attempts.")

                        task.setdefault("attempts_info", []).append(attempt_info)

                        print(f"[COOL-OFF] Sleeping for {COOL_OFF_INTERVAL} seconds before next task...")
                        time.sleep(COOL_OFF_INTERVAL)

                else:
                    print("[WAIT] Orchestrator not ready.")
            else:
                if not idle_state:
                    print("[IDLE] No tasks available.")
                    idle_state = True

            for _ in range(POLL_INTERVAL * 10):
                if _stop:
                    break
                time.sleep(0.1)

    finally:
        clear_running_task()
        print("👋 Shutting down watcher gracefully.")


if __name__ == "__main__":
    if not TASK_FILE.exists():
        save_tasks([])
    main()
