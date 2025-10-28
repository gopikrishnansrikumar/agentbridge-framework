# 🤖 Translator Agent (SDF)

The **Translator SDF Agent** converts robot models into **SDF format** for simulation and validation.

---

## 📂 Folder Structure
| File | Description |
|------|-------------|
| `agent.py` | Defines the Translator SDF agent. |
| `agent_executor.py` | Handles conversion to SDF. |
| `__main__.py` | Entrypoint for running the agent. |
| `pyproject.toml` | Dependencies and config. |
| `README.md` | This documentation file. |

---

## 🚀 Running the Translator SDF

From the project root, activate your virtual environment and run:

```bash
uv run agentbridge -w translator_SDF
```

From **within the agent folder**:
```bash
uv run .
```
This starts the **Translator SDF Agent** and **can be registered with the Delegator**.  

---

## 🔁 Workflow Integration
1. Orchestrator identifies format conversion step.  
2. Delegator routes the task to the **Translator SDF Agent**.  
3. Translator produces SDF output ready for simulation.  

---

## 🛠 Responsibilities
- Convert models into valid SDF.  
- Ensure Gazebo compatibility.  
- Provide feedback on malformed inputs.  
