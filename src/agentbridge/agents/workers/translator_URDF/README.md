# 🤖 Translator Agent (URDF)

The **Translator URDF Agent** converts robot models into **URDF format**, ensuring compatibility with ROS-based simulation environments.

---

## 📂 Folder Structure
| File | Description |
|------|-------------|
| `agent.py` | Defines the Translator URDF agent. |
| `agent_executor.py` | Handles conversion to URDF. |
| `__main__.py` | Entrypoint for running the agent. |
| `pyproject.toml` | Dependencies and config. |
| `README.md` | This documentation file. |

---

## 🚀 Running the Translator URDF

From the project root, activate your virtual environment and run:

```bash
uv run agentbridge -w translator_URDF
```

From **within the agent folder**:
```bash
uv run .
```
This starts the **Translator URDF Agent** and **can be registered with the Delegator**.  

---

## 🔁 Workflow Integration
1. Orchestrator identifies need for URDF conversion.  
2. Delegator routes the task to the **Translator URDF Agent**.  
3. Translator converts the input into URDF.  

---

## 🛠 Responsibilities
- Convert models into URDF format.  
- Validate URDF for ROS compatibility.  
- Return usable URDF files for simulation.  
