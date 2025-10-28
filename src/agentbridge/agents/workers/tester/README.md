# 🤖 Tester Agent

The **Tester Agent** validates robot models by executing them in a **simulation environment (Gazebo or equivalent)** to ensure correctness and functionality.

---

## 📂 Folder Structure
| File | Description |
|------|-------------|
| `agent.py` | Defines the Tester agent. |
| `agent_executor.py` | Execution logic for simulation-based testing. |
| `__main__.py` | Entrypoint for running the agent. |
| `pyproject.toml` | Dependencies and config. |
| `README.md` | This documentation file. |

---

## 🚀 Running the Tester

From the project root, activate your virtual environment and run:

```bash
uv run agentbridge -w tester
```

From **within the agent folder**:
```bash
uv run .
```
This starts the **Tester Agent** and **can be registered with the Delegator**.  

---

## 🔁 Workflow Integration
1. Orchestrator decides a model needs testing.  
2. Delegator sends task to **Tester Agent**.  
3. Tester runs simulations and records outcomes.  

---

## 🛠 Responsibilities
- Run robot models in simulation.  
- Detect runtime issues (physics errors, spawn failures).  
- Return pass/fail test results with logs.  
