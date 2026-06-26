"""Smoke-test client for the Baba HTTP MCP server (runs inside the container)."""

import sys

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _payload(result: object) -> dict:
    # FastMCP wraps a bare-dict return under a "result" key in structuredContent;
    # fall back to parsing the JSON text content block.
    sc = getattr(result, "structuredContent", None)
    if isinstance(sc, dict):
        if set(sc.keys()) == {"result"} and isinstance(sc["result"], dict):
            return sc["result"]
        return sc
    content = getattr(result, "content", None)
    if content:
        import json

        text = getattr(content[0], "text", None)
        if text:
            return json.loads(text)
    return {"_raw": str(result)}


async def _play(url: str, session_id: str) -> dict:
    async with streamablehttp_client(url, headers={"baba_session_id": session_id}) as (
        r,
        w,
        _,
    ):
        async with ClientSession(r, w) as s:
            await s.initialize()
            maps = _payload(await s.call_tool("list_maps", {}))
            names = maps.get("maps", [])
            print(f"[{session_id}] list_maps -> {len(names)} maps, first={names[:3]}")
            assert names, "no built-in maps returned"
            loaded = _payload(await s.call_tool("load_map", {"name": names[0]}))
            print(
                f"[{session_id}] load_map {names[0]} -> status={loaded.get('status')} "
                f"{loaded.get('width')}x{loaded.get('height')}"
            )
            moved = _payload(await s.call_tool("do_action", {"action": "right"}))
            print(f"[{session_id}] do_action right -> status={moved.get('status')}")
            status = _payload(await s.call_tool("get_status", {}))
            print(f"[{session_id}] get_status -> {status}")
            return {"maps": names, "loaded": loaded.get("map")}


async def _main() -> None:
    port = sys.argv[1]
    url = f"http://127.0.0.1:{port}/mcp"
    a = await _play(url, "game-A")
    b = await _play(url, "game-B")
    assert a["maps"] == b["maps"], "map listing should be identical across sessions"
    print("SMOKE OK: server up, tools work, two independent sessions ran")


if __name__ == "__main__":
    anyio.run(_main)
