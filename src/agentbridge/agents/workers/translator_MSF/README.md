# 🤖 Translator Agent (MSF)

The **Translator MSF Agent** converts robot models into **Mock Simulation Format (MSF)**, an experimental vendor-like format.  

---

## 📂 Folder Structure
| File | Description |
|------|-------------|
| `agent.py` | Defines the Translator MSF agent. |
| `agent_executor.py` | Handles conversion to MSF. |
| `__main__.py` | Entrypoint for running the agent. |
| `pyproject.toml` | Dependencies and config. |
| `README.md` | This documentation file. |

---

## 🚀 Running the Translator MSF

From the project root, activate your virtual environment and run:

```bash
uv run agentbridge -w translator_MSF
```

From **within the agent folder**:
```bash
uv run .
```
This starts the **Translator MSF Agent** and **can be registered with the Delegator**.  

---

## 🔁 Workflow Integration
1. Orchestrator assigns an MSF conversion task.  
2. Delegator routes it to the **Translator MSF Agent**.  
3. Translator converts input into MSF.  

---

## 🛠 Responsibilities
- Convert robot models to MSF.  
- Use RAG-based helpers to resolve ambiguities.  
- Provide structured MSF outputs.  
