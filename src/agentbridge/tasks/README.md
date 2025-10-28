# 📋 Tasks (Task Orchestration & Monitoring)

The **Tasks module** manages orchestration-related utilities for **tracking, evaluating, and monitoring tasks** in AgentBridge.  
It supports the Orchestrator and Delegator by keeping structured logs, dashboards, and task list states.  

Key responsibilities:
- Track and monitor tasks created by the Orchestrator.  
- Provide a dashboard (Gradio) for task visualization.  
- Run automated LLM evaluations of outputs.  
- Watch task lifecycle and update status in real time.  
- Persist completed and pending tasks in JSON logs.  

---

## 📂 Folder Structure

- **dashboard.py** → Renders a task dashboard to monitor live task execution.  
- **llm_eval.py** → Runs automated evaluations on outputs using LLMs.  
- **watch_tasks.py** → Watches tasks and updates progress in logs.  
- **task_lists/** → JSON files tracking task states:  
  - `task_list.json` → Active/pending tasks.  
  - `completed_tasks.json` → Successfully completed tasks.  
- **logs/** → Runtime logs:  
  - `watcher.log` → Logs from task watcher.  
- **__pycache__/** → Compiled Python cache.  

---

## 🚀 Running Task Utilities

From the project root:

```bash
uv run agentbridge
```

Or directly from within the folder:

```bash
uv run dashboard.py
```

The **Task Dashboard** is available at:  
👉 **http://localhost:14000**  
⚠️ If port **14000** is busy, it will shift to **14001**.  

---

## 🔁 Workflow Integration

1. **Orchestrator** creates a new plan → tasks are recorded in `task_list.json`.  
2. **Task watcher** monitors progress → updates logs and JSON state files.  
3. **Dashboard** provides real-time UI for visualization.  
4. **LLM evaluator** validates or scores outputs where configured.  
5. **Completed tasks** are moved into `completed_tasks.json`.  

---

## ✅ Checklist Before Running

1. Ensure Orchestrator is running.  
2. Ensure Delegator and workers are active to process tasks.  
3. Start the **Task Dashboard** to monitor execution.   

