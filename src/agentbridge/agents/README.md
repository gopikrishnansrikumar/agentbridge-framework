# Agents

The **Agents module** is the heart of **AgentBridge**, containing both **Supervisor agents** and **Worker agents**.  
These agents form a **multi-agent ecosystem** where Supervisors coordinate and Workers execute specialized tasks.

---

## 📂 Folder Structure

### Supervisors
#### [Supervisors Agents README](supervisors/README.md)
| Folder | Description | Links |
|--------|-------------|-------|
| **delegator/** | Agent-to-Agent (A2A) host, manages agent registration, conversations, and routing | [Delegator README](supervisors/delegator/README.md) |
| **orchestrator/** | LangGraph-based planner, generates task plans and coordinates workers | [Orchestrator README](supervisors/orchestrator/README.md) |

---

### Workers
#### [Worker Agents README](workers/README.md) <br> [How to Add a Worker Agent](workers/HOW_TO_ADD_WORKER.md)
| Folder | Description | Links |
|--------|-------------|-------|
| **describer/** | Generates structured descriptions of robot models | [Describer README](workers/describer/README.md) |
| **translator_SDF/** | Converts models into **SDF** format | [Translator_SDF README](workers/translator_SDF/README.md) |
| **translator_URDF/** | Converts models into **URDF** format | [Translator_URDF README](workers/translator_URDF/README.md) |
| **translator_MSF/** | Converts models into **MSF** format | [Translator_MSF README](workers/translator_MSF/README.md) |
| **tester/** | Tests robot models in Gazebo or equivalent simulator | [Tester README](workers/tester/README.md) |
| **debugger/** | Debugs robot models with simulation feedback | [Debugger README](workers/debugger/README.md) |
| **spawner/** | Spawns robot models into the simulation | [Spawner README](workers/spawner/README.md) |
| **spawner_AGV/** | Spawns Automated Guided Vehicles (AGVs) | [Spawner_AGV README](workers/spawner_AGV/README.md) |

---

## 🧩 Agent Hierarchy

| Layer        | Agents | Role |
|--------------|--------|------|
| **Supervisors** | Delegator, Orchestrator | High-level coordination, task planning, routing |
| **Workers** | Describer, Translators, Tester, Debugger, Spawner(s) | Specialized execution (format conversion, testing, debugging, spawning, describing) |

---

## 🔁 Workflow Overview

1. **Orchestrator** → Generates structured plan for a task.  
2. **Delegator** → Manages available agents and routes tasks.  
3. **Workers** → Execute assigned steps and return results.  
4. **App GUI** → Displays conversations, task progress, and results.  

---

## 📖 References

- [Supervisors README](supervisors/README.md)  
- [Workers README](workers/README.md)  
- [How to Add a Worker Agent](workers/HOW_TO_ADD_WORKER.md)  
