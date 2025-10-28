# 🛠️ Tools (MCP Server & Utilities)

The **Tools module** provides the **Model Context Protocol (MCP) server** and supporting utilities used by worker agents in AgentBridge.  
These tools expose file I/O, validation, debugging, and spawning functions that agents can call at runtime.  

Key responsibilities:
- Run the MCP server over **Server-Sent Events (SSE)**.  
- Expose APIs for reading, writing, and updating robot description files (MJCF, SDF, URDF).  
- Validate robot models and debug them in simulation.  
- Retrieve few-shot examples from pre-loaded vector databases (RAG).  
- Provide machine feedback and spawner scripts for testing.  
- Host unit tests to ensure consistent format handling.  

---

## 📂 Folder Structure

- **mcp_server.py** → Main FastMCP server implementation.  
  - Provides endpoints for agents to discover and invoke tools dynamically.  
- **utils/** → Supporting utilities:  
  - `agent_tools.py` → File readers/writers, validation, and debugging functions.  
  - `machine_feedback.py` → Interprets simulator responses and passes them to agents.  
  - `spawner_scripts.py` → Scripts to spawn/test models in Gazebo.  
  - `unit_tests_MJCF.py` → Unit tests for MJCF parsing/validation.  
  - `unit_tests_SDF.py` → Unit tests for SDF parsing/validation.  
  - `unit_tests_URDF.py` → Unit tests for URDF parsing/validation.  

---

## 🚀 Running the MCP Server

From the project root:

```bash
uv run agentbridge
```

Or from inside the folder:

```bash
uv run mcp_server.py
```

The MCP server will be available at:  
👉 **http://localhost:8000/sse**  

⚠️ If port **8000** is busy, it may shift to **8001** automatically.  

Worker agents will detect the MCP server and can access the tools listed.  

---

## 🔌 Tools Exposed via MCP

| Category                                 | Tool Name                         | Description                        |
| ---------------------------------------- | --------------------------------- | ---------------------------------- |
| **File I/O**                             | `read_mjcf_file`                  | Read MJCF model file               |
|                                          | `read_sdf_file`                   | Read SDF model file                |
|                                          | `read_urdf_file`                  | Read URDF model file               |
|                                          | `save_mjcf_file`                  | Save MJCF model file               |
|                                          | `save_sdf_file`                   | Save SDF model file                |
|                                          | `save_urdf_file`                  | Save URDF model file               |
|                                          | `update_mjcf_file`                | Update existing MJCF model file    |
|                                          | `update_sdf_file`                 | Update existing SDF model file     |
|                                          | `update_urdf_file`                | Update existing URDF model file    |
| **Validation & Debugging**               | `validate_sdf_file`               | Validate SDF model format          |
|                                          | `validate_urdf_file`              | Validate URDF model format         |
|                                          | `debug_robot_file_with_gazebo`    | Run simulation in Gazebo and debug |
| **RAG (Retrieval-Augmented Generation)** | `retrieve_few_shot_examples_sdf`  | Fetch few-shot examples for SDF    |
|                                          | `retrieve_few_shot_examples_urdf` | Fetch few-shot examples for URDF   |

---

## 🛠 Development Notes

- Tools are dynamically discovered by worker agents via MCP.  
- Unit tests for each file type can be run individually:  

```bash
uv run utils/unit_tests_MJCF.py
uv run utils/unit_tests_SDF.py
uv run utils/unit_tests_URDF.py
```  

- Machine feedback is parsed from Gazebo and provided back to debugging agents.  
- The **spawner scripts** automate launching robot models for validation in simulation.  

---

## ✅ Checklist Before Running

1. Ensure `.env` has required API keys.  
2. Run MCP server (`uv run mcp_server.py`).  
3. Start worker agents — they will auto-discover MCP tools.  
4. Verify in the GUI (`Tools` tab) that MCP tools are registered.  

---

## 📖 References

- [Prototype Description Document](../../../assets/SysArch.png)  
- [Delegator README](../agents/supervisors/delegator/README.md)  
- [Orchestrator README](../agents/supervisors/orchestrator/README.md)  
