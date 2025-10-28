# 🤖 Debugger Agent

The **Debugger Worker Agent** validates and debugs robot models by running them inside a **simulation environment (e.g., Gazebo)**.  
It provides structured feedback to detect issues in configuration, physics, or structure.

---

## 📂 Folder Structure

| File | Description |
|------|-------------|
| `agent.py` | Defines the Debugger agent (identity, metadata, registration). |
| `agent_executor.py` | Execution logic for debugging tasks. |
| `__main__.py` | Entrypoint for running the Debugger agent. |
| `pyproject.toml` | Worker-specific dependencies and config. |
| `README.md` | This documentation file. |

---

## 🚀 Running the Debugger

From the project root, activate your virtual environment and run:

```bash
uv run agentbridge -w debugger
```

From **within the agent folder**:

```bash
uv run .
```

This starts the **Debugger Agent** and **can be registered with the Delegator**.  

---

## 🔁 Workflow Integration

1. Orchestrator decides debugging is needed.  
2. Delegator routes the request to the **Debugger Worker Agent**.  
3. Debugger runs simulation checks (via Gazebo or equivalent).  
4. Feedback is returned as structured logs and recommendations.  

---

## 🛠 Responsibilities

- Run robot models inside the simulator.  
- Detect structural/semantic issues (invalid joints, missing links, physics mismatches).  
- Validate URDF/SDF/MJCF correctness during runtime.  
- Provide detailed feedback logs for fixing errors.  
