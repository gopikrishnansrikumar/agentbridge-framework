# 🤖 Describer Agent

The **Describer Agent** generates structured descriptions of robot models in **JSON and natural language**, making them easier to interpret and analyze.

---

## 📂 Folder Structure
| File | Description |
|------|-------------|
| `agent.py` | Defines the Describer agent. |
| `agent_executor.py` | Execution logic for generating descriptions. |
| `__main__.py` | Entrypoint for running the agent. |
| `pyproject.toml` | Dependencies and config. |
| `README.md` | This documentation file. |

---

## 🚀 Running the Describer

From the project root, activate your virtual environment and run:

```bash
uv run agentbridge -w describer
```

From **within the agent folder**:
```bash
uv run .
```
This starts the **Describer Agent** and **can be registered with the Delegator**.  

---

## 🔁 Workflow Integration
1. Orchestrator assigns a "description" task.  
2. Delegator routes it to the **Describer Agent**.  
3. Describer generates JSON + text descriptions.  

---

## 🛠 Responsibilities
- Extract metadata from robot models.  
- Generate JSON descriptions for structure.  
- Provide natural language summaries of models.  
