# 🤖 Worker Agents

The **Worker Agents** are specialized components in **AgentBridge** that perform focused tasks delegated by the **Orchestrator** (via the Delegator).  
Each worker has a **consistent architecture** (agent definition, executor, and entrypoint), and may expose unique functionality depending on its specialization.

---

## 📂 Folder Structure

Each worker lives in its own subfolder:

Common structure inside each worker folder:
- `agent.py` → Defines the worker agent.  
- `agent_executor.py` → Execution logic for running assigned tasks.  
- `__main__.py` → Entrypoint for running the worker directly.  
- `pyproject.toml` → Worker-specific project config.  
- `README.md` → Documentation for that specific worker.  
- `log.txt` (optional) → Local logs of operations.  

---

## 🚀 Running a Worker


From inside the worker folder (e.g., `describer/`):

```bash
uv run .
```

This will start the worker agent and can be registered with the **Delegator**.  

---

## 🔁 Workflow Integration

1. **Orchestrator** creates a plan and identifies required worker agents.  
2. **Delegator** routes the task to the correct worker.  
3. **Worker agent** executes its specialized function (e.g., convert, test, debug).  
4. Results are sent back via Delegator → Orchestrator → GUI.  

---

## 🧩 Example Workers

| Worker       | Responsibility |
|--------------|----------------|
| **Describer** | Generates structured descriptions of robot models (JSON + text). |
| **Translator_SDF** | Converts robot models into SDF format. |
| **Translator_URDF** | Converts robot models into URDF format. |
| **Translator_MSF** | Converts robot models into MSF format. |
| **Tester** | Tests robot models in Gazebo or equivalent simulator. |
| **Debugger** | Debugs simulation issues and validates robot model behavior. |
| **Spawner** | Spawns robot models into the simulation environment. |
| **Spawner_AGV** | Spawns Automated Guided Vehicle robots. |

---

## ➕ Adding New Worker Agents

AgentBridge is **extensible** — developers can create new worker agents for additional tasks.  

📖 See [How to Add a Worker Agent](HOW_TO_ADD_WORKER.md) for detailed steps.  

---

## ✅ Checklist Before Running

1. Ensure Delegator is running.  
2. Ensure Orchestrator is running.  
5. Verify in the App GUI (`Agents` tab) that the worker is registered.  


