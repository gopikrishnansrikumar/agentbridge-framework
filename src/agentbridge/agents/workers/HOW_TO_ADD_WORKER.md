# 🔧 How to Add a Worker Agent

This guide explains how to **create and integrate a new worker agent** into **AgentBridge**.  

Worker agents handle specific tasks (e.g., describing, translating, validating) and run as standalone services that communicate with the **Delegator** and **Orchestrator**.

---

## 🛠 Steps to Add a Worker Agent

### 1. Create a new folder
Under `src/agentbridge/agents/workers/`, create a folder for your worker, e.g.:

```
src/agentbridge/agents/workers/validator/
```

---

### 2. Use the Worker Agent Template
We provide a ready-made template folder at:

```
src/agentbridge/data/templates/WorkerAgentTemplate/
```

Copy the entire template into your new worker folder:

```bash
cp -r src/agentbridge/data/templates/WorkerAgentTemplate src/agentbridge/agents/workers/<your_worker_name>
```

This will give you the following structure:

```
src/agentbridge/agents/workers/<your_worker_name>/
├── agent.py
├── agent_executor.py
├── __init__.py
├── __main__.py
├── pyproject.toml
└── README.md
```

---

### 3. Define Agent Logic
Edit `agent.py`:
- Set the **SYSTEM_INSTRUCTION** to describe your agent’s role.
- Find and replace `MyAgent` & `MYAGENT` in the script with your specific agent name.

---

### 4. Implement Execution Flow
Edit `agent_executor.py`:
- Find and replace `MyAgent` & `MYAGENT` in the script with your specific agent name.

---

### 5. Add Entrypoint
In `__main__.py`:
- Update `AgentSkill`, `AgentCard` with proper metadata & examples.
- Find and replace `MyAgent` & `MYAGENT` in the script with your specific agent name.

---

### 6. Register the Worker in `pyproject.toml`
In the **agents `pyproject.toml`** (`src/agentbridge/agents/pyproject.toml`), add your new worker to the `[tool.uv.workspace].members` list:

```toml
[tool.uv.workspace]
members = [
    "workers/describer",
    "workers/translator_SDF",
    "workers/translator_URDF",
    "workers/translator_MSF",
    "workers/tester",
    "workers/debugger",
    "workers/spawner",
    "workers/spawner_AGV",
    "workers/prechecker",
    "workers/<your_worker_name>"          # 👈 add your worker here
]
```

---

### 7. Add Worker to `config.yaml`
In the root `config.yaml`, register your new worker under the **Agent Addresses and Models** section:

```yaml
<your_worker_name>:
  url: "http://localhost:10050"
  model: "gemini-2.5-pro"
  provider: "Google"
```

> ⚠️ Choose a unique port (e.g., `10050`) that is not already used by another worker.

---

### 8. Run and Test
Start the worker:

```bash
cd src/agentbridge/agents/workers/<your_worker_name>
uv run .
```

It will:
- Start a server on the configured host/port.
- Register automatically with the Delegator.
- Be visible in the App GUI under **Remote Agents**.

Test workflow:
1. Start the AgentBridge.  
2. Add your worker.  
3. Assign it a task via the Orchestrator or GUI.  
4. Confirm it processes inputs and returns a valid result.  

---

## ✅ Example

If you add a **Validator Agent**:
- Create folder: `src/agentbridge/agents/workers/validator`  
- Copy templates inside.  
- Update `pyproject.toml` → add `"workers/validator"`  
- Update `config.yaml`:  

```yaml
validator:
  url: "http://localhost:10050"
  model: "gemini-2.5-pro"
  provider: "Google"
```

Run:

```bash
cd src/agentbridge/agents/workers/validator
uv run .
```

You should see it register and appear in the GUI.

---

## 📖 References
- [Workers README](README.md)  
- [Delegator README](../../supervisors/delegator/README.md)  
- [Orchestrator README](../../supervisors/orchestrator/README.md)  

---

👉 This README now gives a **full cookbook**: scaffold → edit → register → configure → run → test.
