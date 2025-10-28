import os
import streamlit as st
import yaml
from ruamel.yaml import YAML
import subprocess
import signal
import time
import psutil
from urllib.parse import urlparse
import pandas as pd

# =============================================================================
# YAML SETTINGS
# =============================================================================
yaml_ruamel = YAML()
yaml_ruamel.preserve_quotes = True  # preserve double quotes
yaml_ruamel.indent(mapping=2, sequence=4, offset=2)

# =============================================================================
# CONFIG
# =============================================================================
DATA_ROOT = "src/agentbridge/data"
CONFIG_PATH = "config.yaml"

st.set_page_config(layout="wide")

# Expected directory structure for data verification
EXPECTED_STRUCTURE = {
    "description": None,
    "models": None,
    "RAG_MSF": {
        "chroma_gazebo_db": {
            "chroma.sqlite3": None,
            "d1da2c14-f673-4f6d-90b6-d7a2fcfb036f": {
                "data_level0.bin": None,
                "header.bin": None,
                "length.bin": None,
                "link_lists.bin": None,
            }
        },
        "chroma.sqlite3": None,
    },
    "RAG_SDF": {
        "chroma_gazebo_db": {
            "chroma.sqlite3": None,
            "aaeed9e1-855d-40b6-b16b-9cc185779e8e": {
                "data_level0.bin": None,
                "header.bin": None,
                "length.bin": None,
                "link_lists.bin": None,
            }
        },
        "chroma.sqlite3": None,
    },
    "RAG_URDF": {
        "chroma_gazebo_db": {
            "chroma.sqlite3": None,
            "0586e230-5bfe-45ff-889f-a0c297ed0961": {
                "data_level0.bin": None,
                "header.bin": None,
                "length.bin": None,
                "link_lists.bin": None,
            }
        },
        "chroma.sqlite3": None,
    },
    "README.md": None,
    "resources": {
        "Tugbot": {
            "meshes": None,
            "model.config": None,
            "model.sdf": None,
            "thumbnails": None,
        }
    },
    "templates": {"config.yaml": None, "task_list.json": None},
}

# =============================================================================
# HELPERS
# =============================================================================

def check_structure(base_path, structure):
    """Recursively check structure against filesystem."""
    missing = []
    for name, sub in structure.items():
        path = os.path.join(base_path, name)
        if not os.path.exists(path):
            missing.append(path)
        elif isinstance(sub, dict):
            missing.extend(check_structure(path, sub))
    return missing


def load_providers_from_env(env_path=".env"):
    """Parse .env file and detect available providers."""
    providers = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith("GROQ_API_KEY") and not line.strip().endswith('""'):
                    providers.append("groq")
                if line.startswith("GOOGLE_API_KEY") and not line.strip().endswith('""'):
                    providers.append("google")
                if line.startswith("OPENAI_API_KEY") and not line.strip().endswith('""'):
                    providers.append("openai")
    return providers


def next_step():
    """Move wizard to next step."""
    st.session_state.step += 1

# =============================================================================
# INIT SESSION STATE
# =============================================================================
if "step" not in st.session_state:
    st.session_state.step = 0
if "providers" not in st.session_state:
    st.session_state.providers = []
if "results" not in st.session_state:
    st.session_state.results = {}
if "logs" not in st.session_state:
    st.session_state.logs = {}

# =============================================================================
# STEP 0: Welcome
# =============================================================================
if st.session_state.step == 0:
    st.markdown(
        """
        <h2 style="text-align:center;">Welcome to AgentBridge Setup Wizard</h2>
        <p style="text-align:center; font-size:20px;">Let's get everything running for you!</p>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("Start Wizard", width='stretch'):
            next_step()

    st.markdown(
        "<h3 style='text-align:center;margin-top:30px;'>Jump to a step</h3>",
        unsafe_allow_html=True,
    )

    colA, colB, colC = st.columns([1, 2, 1])
    with colB:
        st.button("Step 1 - Setup .env", width='stretch', on_click=lambda: st.session_state.update(step=1))
        st.button("Step 2 - Verify data folder", width='stretch', on_click=lambda: st.session_state.update(step=2))
        st.button("Step 3 - Configure config.yaml", width='stretch', on_click=lambda: st.session_state.update(step=3))
        st.button("Step 4 - Check AgentBridge modules", width='stretch', on_click=lambda: st.session_state.update(step=4))

# =============================================================================
# STEP 1: Setup .env
# =============================================================================
elif st.session_state.step == 1:
    st.header("Step 1️⃣: Setting up your `.env` file")
    st.write("Please provide your API keys below. At least one main provider is required.")

    groq = st.text_input("🔑 GROQ_API_KEY", placeholder="your-groq-api-key")
    google = st.text_input("🔑 GOOGLE_API_KEY", placeholder="your-google-api-key")
    openai = st.text_input("🔑 OPENAI_API_KEY", placeholder="your-openai-api-key")
    langsmith = st.text_input("🔑 LANGSMITH_API_KEY (optional)", placeholder="your-langsmith-api-key")

    # Track providers dynamically
    st.session_state.providers = []
    if groq:
        st.session_state.providers.append("groq")
    if google:
        st.session_state.providers.append("google")
    if openai:
        st.session_state.providers.append("openai")

    if st.session_state.providers:
        st.info(f"✅ Detected providers: {', '.join(st.session_state.providers)}")
    else:
        st.warning("⚠️ Please enter at least one provider key (Groq, Google, or OpenAI).")

    if st.session_state.providers:
        if st.button("Next ➡️"):
            env_content = f'''# API Keys
GROQ_API_KEY="{groq}"
GOOGLE_API_KEY="{google}"
OPENAI_API_KEY="{openai}"

# LangChain (optional)
LANGSMITH_API_KEY="{langsmith}"
'''
            with open(".env", "w") as f:
                f.write(env_content)
            st.success("✅ `.env` file created successfully!")
            next_step()

# =============================================================================
# STEP 2: Check data folder
# =============================================================================
elif st.session_state.step == 2:
    if not os.path.exists(".env"):
        st.error("❌ You must complete Step 1 (setup `.env`) before continuing.")
        if st.button("⬅️ Go to Step 1"):
            st.session_state.step = 1
    else:
        st.session_state.providers = load_providers_from_env(".env")

        st.header("Step 2️⃣: Verifying `src/agentbridge/data` folder")

        if not os.path.exists(DATA_ROOT):
            st.error(f"❌ Data folder not found at `{DATA_ROOT}`")
        else:
            missing = check_structure(DATA_ROOT, EXPECTED_STRUCTURE)
            if missing:
                st.error("⚠️ The following required files/folders are missing:")
                for m in missing:
                    st.text(f"- {m}")
                st.warning("Please fix the missing files and then click 'Check Again'.")
                if st.button("🔄 Check Again"):
                    st.rerun()
            else:
                st.success("✅ All required files and folders are present!")
                if st.button("Next ➡️"):
                    next_step()

# =============================================================================
# STEP 3: Config.yaml editor
# =============================================================================
elif st.session_state.step == 3:
    if not os.path.exists(".env"):
        st.error("❌ You must complete Step 1 (setup `.env`) before continuing.")
        if st.button("⬅️ Go to Step 1"):
            st.session_state.step = 1
    elif not os.path.exists(DATA_ROOT):
        st.error("❌ You must complete Step 2 (verify data folder) before continuing.")
        if st.button("⬅️ Go to Step 2"):
            st.session_state.step = 2
    else:
        st.session_state.providers = load_providers_from_env(".env")

        st.header("Step 3️⃣: Configure `config.yaml`")

        if not os.path.exists(CONFIG_PATH):
            st.error(f"❌ Could not find `{CONFIG_PATH}`")
        else:
            with open(CONFIG_PATH, "r") as f:
                config = yaml_ruamel.load(f)

            available_models = config.get("models", {})
            agents = [
                "tasks", "orchestrator", "delegator", "prechecker", "describer",
                "translator_SDF", "translator_URDF", "translator_MSF",
                "tester", "debugger", "spawner", "spawner_AGV",
            ]

            st.subheader("⚙️ Global Settings")
            if st.session_state.providers:
                default_provider = str(config["tasks"].get("provider", st.session_state.providers[0]))
                default_model = str(config["tasks"].get("model", ""))

                global_provider = st.selectbox(
                    "Select a global provider (applies to all agents)",
                    options=st.session_state.providers,
                    index=st.session_state.providers.index(default_provider.lower())
                        if default_provider.lower() in st.session_state.providers else 0,
                    key="global_provider",
                )

                global_models = available_models.get(global_provider.capitalize(), [])
                global_model = st.selectbox(
                    "Select a global model (applies to all agents)",
                    options=global_models,
                    index=global_models.index(default_model) if default_model in global_models else 0,
                    key="global_model",
                )

                col1, col2, col3 = st.columns([3, 4, 3])
                with col2:
                    if st.button("Apply Global Settings to All", width='stretch'):
                        for agent in agents:
                            if agent in config:
                                config[agent]["provider"] = global_provider
                                config[agent]["model"] = global_model
                        with open(CONFIG_PATH, "w") as f:
                            yaml_ruamel.dump(config, f)
                        st.success(f"✅ Applied {global_provider} / {global_model} to all agents!")
                        st.rerun()

            else:
                st.error("❌ No providers available. Please complete Step 1 first.")
                global_provider, global_model = None, None

            updated = {}
            for agent in agents:
                if agent in config:
                    st.markdown(f"### 🔹 {agent}")
                    current_provider = str(config[agent].get("provider", st.session_state.providers[0]))
                    current_model = str(config[agent].get("model", ""))

                    provider = st.selectbox(
                        f"Provider for {agent}",
                        options=st.session_state.providers,
                        index=st.session_state.providers.index(current_provider.lower())
                            if current_provider.lower() in st.session_state.providers else 0,
                    )

                    models = available_models.get(provider.capitalize(), [])
                    model = st.selectbox(
                        f"Model for {agent}",
                        options=models,
                        index=models.index(current_model) if current_model in models else 0,
                    )

                    updated[agent] = {
                        "url": config[agent].get("url", ""),
                        "provider": provider,
                        "model": model,
                    }

            col1, col2, col3 = st.columns([2,1,2])
            with col2:
                if st.button("➡️ Save & Next", width='stretch'):
                    for agent, values in updated.items():
                        config[agent]["provider"] = values["provider"]
                        config[agent]["model"] = values["model"]
                        config[agent]["url"] = values["url"]

                    with open(CONFIG_PATH, "w") as f:
                        yaml_ruamel.dump(config, f)

                    st.success("✅ Config.yaml updated successfully!", icon="💾")
                    next_step()

# =============================================================================
# STEP 4: Check AgentBridge modules
# =============================================================================
elif st.session_state.step == 4:
    st.markdown("<h2 style='text-align:center;'>Step 4️⃣: Checking AgentBridge modules</h2>", unsafe_allow_html=True)

    # Helpers
    def get_port_from_url(url: str):
        parsed = urlparse(url)
        return parsed.port if parsed.port else None

    def load_config_agents(config_path=CONFIG_PATH):
        with open(config_path, "r") as f:
            config = yaml_ruamel.load(f)
        agents = {}
        for name, values in config.items():
            if isinstance(values, dict) and "url" in values:
                port = get_port_from_url(str(values["url"]))
                agents[name] = {"url": values["url"], "port": port}
        return agents

    def free_port(port):
        killed = []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.connections(kind='inet'):
                    if conn.laddr.port == port:
                        proc.send_signal(signal.SIGINT)
                        try:
                            proc.wait(timeout=5)
                            killed.append(f"✅ Gracefully stopped {proc.name()} (PID {proc.pid}) on port {port}")
                        except psutil.TimeoutExpired:
                            proc.kill()
                            killed.append(f"⚠️ Force killed {proc.name()} (PID {proc.pid}) on port {port}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return killed

    def run_check(name, cmd, cwd=None, timeout=20, port=None):
        try:
            proc = subprocess.Popen(
                cmd, cwd=cwd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            logs, success = [], False
            start_time = time.time()
            while True:
                if proc.poll() is not None:
                    break
                line = proc.stdout.readline()
                if line:
                    logs.append(line.strip())
                    if "Application startup complete" in line or "Uvicorn running" in line:
                        success = True
                        break
                if time.time() - start_time > timeout:
                    logs.append("⏳ Timeout reached")
                    break
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=5)
                logs.append("✅ Process exited gracefully with SIGINT")
            except subprocess.TimeoutExpired:
                proc.kill()
                logs.append("⚠️ Process force killed after timeout")
            if port:
                logs.extend(free_port(port))
            return success, "\n".join(logs)
        except Exception as e:
            return False, f"❌ Exception in {name}: {e}"

    def build_path_map():
        path_map = {
            "Orchestrator": ("uv run server.py", "src/agentbridge/agents/supervisors/orchestrator"),
            "Delegator": ("uv run main.py", "src/agentbridge/app"),
            "MCP Server": ("uv run mcp_server.py", "src/agentbridge/tools"),
            "Task Manager": ("uv run main.py", "src/agentbridge/app"),
        }
        workers_root = "src/agentbridge/agents/workers"
        if os.path.exists(workers_root):
            for worker in os.listdir(workers_root):
                worker_path = os.path.join(workers_root, worker)
                if os.path.isdir(worker_path):
                    path_map[worker] = ("uv run .", worker_path)
        return path_map

    # Start checks
    col1, col2, col3 = st.columns([3, 4, 3])
    with col2:
        if st.button("Start Checks", width='stretch'):
            agents = load_config_agents(CONFIG_PATH)
            path_map = build_path_map()
            results, logs = {}, {}
            for agent, meta in agents.items():
                if agent in path_map:
                    cmd, cwd = path_map[agent]
                    port = meta["port"]
                    st.write(f"🔍 Checking **{agent}**...")
                    success, log = run_check(agent, cmd, cwd=cwd, port=port)
                    results[agent] = success
                    logs[agent] = log
                    if success:
                        st.success(f"{agent} ✅ Success")
                    else:
                        st.error(f"{agent} ❌ Failed")
                    with st.expander(f"📜 Logs for {agent}"):
                        st.code(log)
            st.session_state.results = results
            st.session_state.logs = logs

    # Show summary if results exist
    if st.session_state.results:
        summary_data = []
        for agent, ok in st.session_state.results.items():
            port = "?"  # optionally include port if needed
            summary_data.append({
                "Agent": agent,
                "Status": "✅ Success" if ok else "❌ Failed"
            })
        df_summary = pd.DataFrame(summary_data)
        st.subheader("📊 Summary Report")
        st.dataframe(df_summary, width='stretch')

        if all(st.session_state.results.values()):
            colA, colB, colC = st.columns([3, 2, 3])
            with colB:
                if st.button("➡️ Next", width='stretch'):
                    st.session_state.step = 5
                    st.rerun()
        else:
            st.warning("⚠️ Some modules failed. Please review the logs before proceeding.")

# =============================================================================
# STEP 5: Finish
# =============================================================================
elif st.session_state.step == 5:
    st.header("🎉 You’re all set!")

    st.markdown("""
    <div style="font-size:18px; margin-bottom:20px;">
    Now you can launch <b>AgentBridge</b> the way you want. Here are some handy commands:
    </div>
    """, unsafe_allow_html=True)

    # Show each command in its own copyable block
    st.write("➡️ Run app + MCP + orchestrator + dashboard")
    st.code("uv run agentbridge", language="bash")

    st.write("➡️ Run all workers in addition to the core components")
    st.code("uv run agentbridge --all-workers", language="bash")
    
    st.write("➡️ Run only the 'describer' worker")
    st.code("uv run agentbridge -w describer", language="bash")
    
    st.write("➡️ Run multiple workers")
    st.code("uv run agentbridge -w describer -w spawner", language="bash")    

    st.write("➡️ List all detected workers and exit")
    st.code("uv run agentbridge --list-workers", language="bash")

    st.write("➡️ Skip the app")
    st.code("uv run agentbridge --no-app", language="bash")
    
    st.write("➡️ Skip the dashboard")
    st.code("uv run agentbridge --no-dashboard", language="bash")

    st.write("➡️ Skip MCP and orchestrator (custom setup)")
    st.code("uv run agentbridge --no-mcp --no-orchestrator", language="bash")

    # Finish button
    col1, col2, col3 = st.columns([3,2,3])
    with col2:
        if st.button("🏁 Finish", width='stretch'):
            st.success("Wizard complete! You can now run `uv run agentbridge` from your terminal.")
            st.session_state.step = 0  # reset wizard

