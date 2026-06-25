"""Example external entry point for the Baba Is You MCP server.

Build the server with the factory, then serve it however you like. This default
serves streamable-HTTP on 0.0.0.0:8000 (endpoint /mcp); clients select a game by
sending a `baba_session_id` header. Edit/replace freely.

Run:
    uv run --project Extensions/BabaMCP python main.py
"""

from baba_mcp import create_baba_mcp

mcp = create_baba_mcp(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")  # or: mcp.run()  # stdio
