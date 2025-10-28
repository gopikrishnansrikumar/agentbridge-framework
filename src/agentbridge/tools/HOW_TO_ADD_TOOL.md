
# 🧩 HOW_TO_ADD_TOOL.md  
### How to Add a New Tool to the MCP Server

This guide explains how to **add a new tool** to the **MCP Server** in AgentBridge.  
A tool is a callable function that the agents use to perform tasks such as reading files, validating models, or launching Gazebo simulations.

---

## 🧱 1. Project Location

The MCP Server and tools are located here:

```
src/agentbridge/tools/
├── mcp_server.py        # Main MCP server (define tools here)
├── utils/               # Helper modules (imported by tools)
└── HOW_TO_ADD_TOOL.md   # This guide
```

---

## ⚙️ 2. Where to Add the Tool

All MCP tools are defined inside **`mcp_server.py`**.  
You’ll find several existing examples such as:

```python
@mcp.tool()
async def read_mjcf_file(path: str) -> str:
    ...
```

To add a new one, simply define a new function with the same pattern.

---

## 🧰 3. Add a New Tool

Add your function inside **`mcp_server.py`**, decorated with `@mcp.tool()`:

```python
@mcp.tool()
async def my_new_tool(param1: str, param2: int = 0) -> str:
    """Brief description of what this tool does.

    Args:
        param1 (str): Description of the first parameter.
        param2 (int, optional): Optional parameter.

    Returns:
        str: A result or confirmation message.
    """
    # Your logic here
    result = f"Processed {param1} successfully with param2={param2}"
    return result
```

That’s it — no extra registration needed.

---

## 🧩 4. Run the MCP Server

Once you’ve added your new tool, restart the MCP server:

```bash
cd src/agentbridge/tools
uv run mcp_server.py
```

The MCP server automatically loads and registers all decorated tools.

---

## 🧠 5. Verify Your Tool

After starting the server:
1. Open the **AgentBridge GUI**.  
2. Go to the **“Tools”** tab.  
3. Look for your new tool (e.g., `my_new_tool`).  

If it appears there, your registration worked successfully. ✅

---

## 🧪 6. Example

Example: Add a file-checking tool in `mcp_server.py`:

```python
@mcp.tool()
async def check_file_exists(path: str) -> str:
    """Check if a file exists and return a readable message."""
    import os
    if not os.path.exists(path):
        return f"❌ File not found: {path}"
    return f"✅ File exists: {path} ({os.path.getsize(path)} bytes)"
```

After saving and restarting the MCP server,  
you’ll see **check_file_exists** listed in the GUI’s **Tools** tab.

---

## 📋 7. Quick Checklist

| Step | Action |
|------|---------|
| ✅ | Open `src/agentbridge/tools/mcp_server.py` |
| ✅ | Add function with `@mcp.tool()` decorator |
| ✅ | Write logic and docstring |
| ✅ | Restart the MCP server |
| ✅ | Verify in AgentBridge GUI |

---

### 🧭 Notes

- Tools can be **async** or **sync** functions.  
- Keep function names **unique** and meaningful.  
- Always validate file paths before reading or writing.  
- Return **human-readable** messages or structured data.  
- Helper logic can go in the `utils/` directory.
