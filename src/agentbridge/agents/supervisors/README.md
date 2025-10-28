# 🤖 Supervisors (Delegator & Orchestrator)

The **Supervisors module** contains the two central agents that oversee all other agents in **AgentBridge**:

- **Delegator** → Acts as the **Agent-to-Agent (A2A) host**, managing agent registration, state, and routing. It powers the web GUI and exposes APIs for conversations, tasks, and agent management.  
- **Orchestrator** → A **LangGraph-based planner** that takes high-level user goals, generates structured step-by-step plans, and coordinates worker agents to execute them.

Together, they form the **control layer** of AgentBridge.

---

## 🌐 API Access

- **Delegator**:  
  - GUI/API: **http://localhost:12000**  
  - Swagger: **http://localhost:12000/docs**  
  - (May shift to **12001** if 12000 is busy)  

- **Orchestrator**:  
  - API: **http://localhost:10000**  
  - Swagger: **http://localhost:10000/docs**  
  - (May shift to **10001** if 10000 is busy)  

---

## 📝 Responsibilities

| Supervisor   | Responsibilities |
|--------------|------------------|
| **Delegator** | - Maintain registry of worker agents<br>- Expose REST APIs for conversations, messages, tasks<br>- Manage A2A Agent Cards<br>- Route tasks/messages to correct worker<br>- Power the GUI |
| **Orchestrator** | - Parse high-level tasks into step-by-step plans<br>- Coordinate task execution with Delegator<br>- Monitor progress and retry failed steps<br>- Log plans and conversations |

---

## 📖 References

- [Delegator README](delegator/README.md)  
- [Orchestrator README](orchestrator/README.md)  
- [Prototype Description Document](../../../../../assets/SysArch.png)  
