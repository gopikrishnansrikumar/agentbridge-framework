# 🤖 Delegator

The **Delegator** is one of the two **Supervisor agents** in AgentBridge (the other is the Orchestrator).  
It serves as the **A2A Host** and central **agent registry**, responsible for:

- Managing available worker agents and their state.  
- Registering and exposing Agent Cards (`/.well-known/agent.json`) for discovery.  
- Routing tasks and messages between agents.  
- Exposing a REST API (via FastAPI) for conversations, task management, and agent queries.  
- Persisting and updating conversation/task state in memory.  

---

## 📂 Folder Contents
- `agent.py` → main Delegator agent implementation.  
- `remote_agent_connection.py` → handles connections to remote worker agents.  
- `pyproject.toml` → Python project configuration for Delegator.  
- `README.md` → this file.  

---

## 🚀 Running the Delegator

From the project root, activate your virtual environment and run:

```bash
uv run agentbridge 
```

Or directly from within the `app` folder in agentbridge root:

```bash
uv run main.py
```

The Delegator starts a FastAPI server (default port: **12000**).  
⚠️ If port 12000 is busy, the service will automatically shift to **12001**.  

This service also powers the **AgentBridge GUI**.

---

## 🌐 API Endpoints

The Delegator exposes its REST API, documented at:  
👉 **http://localhost:12000/docs** (Swagger UI)  
(or **http://localhost:12001/docs** if 12000 is unavailable)

Available endpoints:

- **Conversations**
  - `POST /conversation/create` → Create a new conversation.  
  - `POST /conversation/list` → List all conversations.  

- **Messages**
  - `POST /message/send` → Send a message.  
  - `POST /message/list` → List messages.  
  - `POST /message/pending` → Get pending messages.  
  - `GET /message/file/{file_id}` → Download an attached file.  

- **Events**
  - `POST /events/get` → Fetch recent events.  

- **Tasks**
  - `POST /task/list` → List tasks.  

- **Agents**
  - `POST /agent/register` → Register a new agent.  
  - `POST /agent/list` → List registered agents.  

- **API Keys**
  - `POST /api_key/update` → Update API key.  

---

## 🔌 A2A Protocol Support

- Delegator implements **Agent-to-Agent (A2A)** communication.  
- Acts as the **Host Agent**.
- Worker agents act as **remotes**, connecting to the Delegator and registering their capabilities.

---

## 🛠 Development Notes

- Uses **Google ADK (Agent Development Kit)** internally.  
- State management lives in `agentbridge/app/state/`.  
- In-memory agent/task management provided by `agentbridge/app/service/server/in_memory_manager.py`.  
- GUI integration lives under `agentbridge/app/` — the Delegator is tightly coupled with the AgentBridge frontend.

---

## ✅ Checklist Before Running

1. Ensure `.env` has valid API keys (`GROQ_API_KEY`, `GOOGLE_API_KEY`).  
2. Start the MCP server (`src/agentbridge/tools/mcp_server.py`) if tools are required.  
3. Launch Delegator → it will host the GUI at **http://localhost:12000** (or **12001**).  
4. Start worker agents (`describer`, `translator_SDF`, etc.) so they register with the Delegator.  
