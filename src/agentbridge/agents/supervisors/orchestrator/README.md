# 🤖 Orchestrator

The **Orchestrator** is one of the two **Supervisor agents** in AgentBridge (the other is the Delegator).  
It is the **LangGraph-based planner and controller** responsible for breaking down high-level user tasks into structured plans and coordinating worker agents to execute them.  

Key responsibilities:

- Parse high-level goals into ordered **plans** (numbered steps).  
- Delegate sub-tasks to worker agents via the Delegator.  
- Monitor execution progress and retry failed steps (up to 3 times).  
- Log plans and conversations for traceability.  

---

## 📂 Folder Contents
- `agent_builder.py` → constructs the Orchestrator agent using LangGraph.  
- `runners.py` → task runners and utilities.  
- `server.py` → FastAPI server for the Orchestrator API.  
- `settings.py` → configuration.  
- `tools.py` → tool bindings for orchestration.  
- `tasks/logs/` → generated logs:  
  - `plan.md` → latest orchestration plan.  
  - `conversation_log.md` → conversation logs.  
  - `conversation_id.txt` → current conversation ID.  

---

## 🚀 Running the Orchestrator

From the project root:

```bash
uv run agentbridge 
```

Or directly:

```bash
uv run main.py     # CLI mode

uv run server.py   # Server mode 
```

For `server mode` the Orchestrator starts at **http://localhost:10000**.  
⚠️ If port **10000** is busy, it may shift automatically to **10001**.  

---

## 🌐 API Endpoints

The Orchestrator exposes its REST API at:  
👉 **http://localhost:10000/docs** (Swagger UI)  
(or **http://localhost:10001/docs** if port is shifted)

Available endpoints:

- **Health**
  - `GET /health` → Check if the Orchestrator is running.  

- **Run Task**
  - `POST /run` → Start a new orchestration run.  

---

## 🔁 Orchestration Workflow

1. **Receive task** → User sends a high-level request via `/run`.  
2. **Plan generation** → Orchestrator produces a step-by-step plan.  
3. **Delegation** → Each step is routed through the Delegator to the appropriate worker.  
4. **Monitoring** → Execution progress is tracked and retried if needed.  
5. **Logging** → Plans and conversations are stored under `tasks/logs/`.  

---

## 🛠 Development Notes

- Uses **LangGraph** with ReAct planning.  
- Integrates tightly with the Delegator for agent routing.  
- Supports optional tracing with **LangSmith** if `LANGSMITH_API_KEY` is configured.  

---

## ✅ Checklist Before Running

1. Ensure `.env` contains API keys (`GOOGLE_API_KEY`).  
2. Start the Delegator first 
3. Launch the Orchestrator → it will serve on **http://localhost:10000** (or **10001**).  
4. Worker agents should be running and registered with the Delegator.  

