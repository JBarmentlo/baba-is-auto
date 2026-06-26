# BabaMCP — Docker / `.sqsh` quickstart

An HTTP [MCP](https://modelcontextprotocol.io) server wrapping the `pyBaba`
"Baba Is You" simulator. The container's entrypoint starts the server over
**streamable-HTTP**; the listen port is set with the `BABA_MCP_PORT` env var.

(Full tool/API docs: `Extensions/BabaMCP/README.md`.)

## Run it

### Prebuilt enroot image (Slurm / pyxis)

A ready-to-use squashfs lives on the shared volume (group `dev`, read access):

```
/mnt/vast/shared/joep/baba/baba-mcp.sqsh
```

```bash
srun --container-image=/mnt/vast/shared/joep/baba/baba-mcp.sqsh \
     --container-env=BABA_MCP_PORT=8000 \
     # ... your --partition / -G / etc.
```

The server then listens on `http://<node>:8000/mcp`.

### Docker

```bash
docker run --rm -e BABA_MCP_PORT=8000 -p 8000:8000 baba-mcp:latest
# serves http://0.0.0.0:8000/mcp
```

### Build / re-export (optional)

```bash
docker build -f Dockerfile.mcp -t baba-mcp:latest .      # ~15 min cold (vcpkg)
enroot import -o baba-mcp.sqsh dockerd://baba-mcp:latest # produce the .sqsh
```

## Configuration (env vars)

| Var | Default | Meaning |
| --- | --- | --- |
| `BABA_MCP_PORT` | `8000` | HTTP listen port |
| `BABA_MCP_HOST` | `0.0.0.0` | bind address |
| `BABA_MCP_HTTP_PATH` | `/mcp` | endpoint path |
| `BABA_MCP_TRANSPORT` | `http` | `http` or `stdio` |

## What to expect from the MCP

- **Transport:** streamable-HTTP at `http://<host>:<port>/mcp`.
- **Sessions:** every request selects its own independent game via the
  **`baba_session_id`** request header. Different ids → different games that
  persist across requests; state-touching tools **require** the header
  (`list_maps` does not).
- **Tools** (12): `get_state`, `get_status`, `do_action`, `do_actions`, `undo`,
  `reset`, `load_map`, `load_raw_map`, `list_maps`, `get_rules`, `end_session`,
  `list_sessions`.
- **State shape:** `get_state` returns the board as a 2-D grid
  (`grid[y][x]` = list of stacked object-type names) plus `width`, `height`,
  `map`, and `status` (`in_progress` / `success` / `dead`).
- **Moves:** `do_action("up"|"down"|"left"|"right"|"idle")`; `do_actions([...])`
  applies a sequence and stops early on win/loss.

### Minimal client

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client(
    "http://HOST:8000/mcp", headers={"baba_session_id": "game-1"}
) as (r, w, _):
    async with ClientSession(r, w) as s:
        await s.initialize()
        print((await s.call_tool("get_state", {})).structuredContent)
        await s.call_tool("do_actions", {"actions": ["right", "right", "up"]})
```

> Note: the server is unauthenticated — run it on a trusted network. It keeps
> session state in one process's memory, so run a single replica.
