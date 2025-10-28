# 🤖 Prechecker Agent

The **Prechecker Agent** validates input robot models (MJCF, SDF, URDF) before further processing.  
It checks for missing fields, malformed joints, and other critical issues early in the pipeline.  

---

## 📂 Folder Structure
| File | Description |
|------|-------------|
| `agent.py` | Defines the Prechecker agent. |
| `agent_executor.py` | Execution logic for pre-validation. |
| `__main__.py` | Entrypoint for running the agent. |
| `pyproject.toml` | Dependencies and config. |
| `README.md` | This documentation file. |

---

## 🚀 Running the Prechecker

From the project root, activate your virtual environment and run:

```bash
uv run agentbridge -w prechecker
```

From **within the agent folder**:
```bash
uv run .
```
This starts the **Prechecker Agent** and **can be registered with the Delegator**.  

---

## 🔁 Workflow Integration
1. Orchestrator assigns a pre-validation task.  
2. Delegator routes it to the **Prechecker Agent**.  
3. Prechecker runs static checks before passing the model forward.  

---

## 🛠 Responsibilities
- Catch malformed or incomplete MJCF/SDF/URDF files.  
- Prevent propagation of errors downstream.  
- Return structured logs on detected issues.  
