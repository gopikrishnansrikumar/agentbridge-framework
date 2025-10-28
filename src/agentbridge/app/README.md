
# 🖥️ App (AgentBridge GUI & Service Layer)

The **App module** provides the **web-based GUI, API server, and service layer** for AgentBridge.  
It is tightly integrated with the **Delegator** supervisor and allows users to visualize, manage, and interact with agents, conversations, and tasks.  

Key features:
- Web GUI for managing agents, tasks, and conversations.  
- FastAPI service endpoints for agent registration, state management, and task execution.  
- Persistent in-memory and file-based state tracking.  

---

## 📂 Folder Structure

- **components/** → UI components  
  - e.g., `agent_list.py`, `conversation.py`, `chat_bubble.py`, `tools_list.py`  

- **pages/** → Full page views  
  - `home.py`, `agent_list.py`, `conversation.py`, `task_list.py`, `tools.py`  

- **service/** → Backend service layer  
  - `server/` → FastAPI server with ADK Host Manager  
  - `client/` → lightweight client for interacting with the server  
  - `types.py` → shared service types  

- **state/** → State management  
  - `agent_state.py`, `tools_state.py`, `host_agent_service.py`  

- **utils/** → Helper utilities  
  - `agent_card.py` (handles A2A Agent Card definitions)  

- **static/** → Assets (CSS, images, architecture diagrams)  

- **styles/** → Theming and CSS-in-Python  

- **tests/** → Unit tests for backend modules (`test_adk_host_manager.py`)  

- **main.py** → App entrypoint.  
- **saved_agents.json** → Persistent agent registry snapshot.  
- **pyproject.toml** → Local project config.  

---

## 🚀 Running the App

From the project root:

```bash
uv run agentbridge
```

Or directly:

```bash
uv run main.py
```

The GUI will be available at:  
👉 **http://localhost:12000** (or **http://localhost:12001** if the default port is busy).  

---

## 🌐 Features in the GUI

- **Agent List** → View available/registered agents.  
- **Conversation Manager** → Start and view conversations with agents.  
- **Task Dashboard** → Monitor tasks created by the Orchestrator.  
- **Tools Tab** → Shows registered MCP tools available to workers.  
- **Event Viewer** → Stream execution updates.  

---

## 🔌 Backend Integration

- **Delegator coupling**: The app integrates with the Delegator to expose agent endpoints.  
- **A2A Agent Cards**: Accessible via the Delegator endpoints
- **Service State**: Maintains in-memory and persisted states of tasks, conversations, and tools.  

---

## ✅ Checklist Before Running

1. Ensure `.env` has required API keys (`GROQ_API_KEY`, `GOOGLE_API_KEY`).  
2. Run the App (`uv run agentbridge`).  
4. Access the GUI at **http://localhost:12000** (or fallback **12001**).  

---

## 📖 References

- [Delegator README](../agents/supervisors/delegator/README.md)  
