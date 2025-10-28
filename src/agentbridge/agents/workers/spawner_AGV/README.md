# 🤖 Spawner AGV Agent

The **Spawner AGV Agent** specializes in spawning **Automated Guided Vehicles (AGVs)**, such as Tugbot robots, into the simulation environment.

---

## 📂 Folder Structure
| File | Description |
|------|-------------|
| `agent.py` | Defines the Spawner AGV agent. |
| `agent_executor.py` | Execution logic for spawning AGVs. |
| `__main__.py` | Entrypoint for running the agent. |
| `pyproject.toml` | Dependencies and config. |
| `README.md` | This documentation file. |

---

## 🚀 Running the Spawner AGV

From the project root, activate your virtual environment and run:

```bash
uv run agentbridge -w spawner_AGV
```

From **within the agent folder**:
```bash
uv run .
```
This starts the **Spawner AGV Agent** and **can be registered with the Delegator**.  

---

## 🔁 Workflow Integration
1. Orchestrator requires an AGV model.  
2. Delegator routes the request to the **Spawner AGV Agent**.  
3. Spawner loads the AGV into the target simulator.  

---

## 🛠 Responsibilities
- Spawn AGVs with plugins.  
- Handle specific AGV configurations.  
