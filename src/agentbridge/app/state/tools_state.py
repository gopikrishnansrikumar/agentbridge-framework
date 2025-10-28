from langchain_mcp_adapters.client import MultiServerMCPClient


async def fetch_tools():
    # Configure MCP servers as needed
    client = MultiServerMCPClient(
        {
            "mjcf": {
                "url": "http://localhost:8000/sse",
                "transport": "sse",
            }
        }
    )
    tools = await client.get_tools()
    # Each tool is a dict; ensure it's serializable if caching
    return tools
