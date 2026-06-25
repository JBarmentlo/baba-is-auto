# BabaMCP

An [MCP](https://modelcontextprotocol.io) server that wraps the `pyBaba` "Baba Is
You" simulator, so an LLM/agent can play the game: observe the board grid (not an
image), make moves, check win/lose status, switch levels, and undo.

It is a thin, in-process Python layer over the `pyBaba` pybind11 module — no game
logic is reimplemented here.

Runs over **stdio** or **HTTP** (streamable-http), and supports **many concurrent
sessions** — over HTTP each request selects its game with a `baba_session_id`
header (see [Transports & sessions](#transports--sessions)).

## Tools

| Tool | Description |
| --- | --- |
| `get_state()` | Current board as a 2D grid (`grid[y][x]` = list of stacked object-type names), plus `width`, `height`, `map`, `status`. |
| `get_status()` | `success` (won) / `dead` (lost) / `in_progress` / `invalid` (or `no_game`). |
| `do_action(action)` | One move: `"up" | "down" | "left" | "right" | "idle"` (case-insensitive). Returns the new state. |
| `do_actions(actions)` | A list of moves; stops early on win/loss. Returns state + `applied`, `requested`, `stopped_reason`. |
| `undo(steps=1)` | Undo the last N moves (Reset + deterministic replay; the sim has no native undo). |
| `reset()` | Restart the current level and clear history. |
| `load_map(name)` | Load a built-in map by name, e.g. `"simple_map"`. |
| `load_raw_map(map_contents)` | Load a map from raw text in the native format (validated first — see below). |
| `list_maps()` | List built-in map names. Works without a session header. |
| `get_rules()` | Active rules as object-name triples, e.g. `["BABA","IS","YOU"]`. |
| `end_session()` | Free the caller's session (its game/history). A later call lazily recreates a fresh one. |
| `list_sessions()` | List active sessions (`id`, `map`, `moves`) for debugging/ops. |

### Native map format (`load_raw_map`)

A `width height` header line followed by exactly `width*height` integer `ObjectType`
codes (same as `Resources/Maps/*.txt`). Example (3×4):

```
3 4
132 132 132
4   67  77
114 132 132
132 132 132
```

## Transports & sessions

The server can be served two ways:

- **stdio** — the client launches it as a subprocess; there is a single implicit
  session (id `"stdio"`). No header needed.
- **HTTP** (streamable-http) — reachable over the network at `/mcp`. Each request
  selects its game via the **`baba_session_id` request header**; distinct ids get
  independent games that persist across requests. State-touching tools **require**
  the header over HTTP and return a clear error if it's missing (`list_maps` does
  not). Sessions are held in memory (a live game per id), capped at `max_sessions`
  with FIFO eviction; `end_session()` frees one early.

### Use the factory in your own server

`create_baba_mcp(**kwargs) -> FastMCP` builds a fully-configured instance (all
tools registered, isolated session store). Serve it however you like:

```python
from baba_mcp import create_baba_mcp

mcp = create_baba_mcp(host="0.0.0.0", port=8000)   # kwargs forwarded to FastMCP(...)
mcp.run(transport="streamable-http")               # or mcp.run() for stdio
# or mount the ASGI app: app = mcp.streamable_http_app()  # endpoint at /mcp
```

`create_baba_mcp` accepts `max_sessions` (default 256), `require_session_header`
(default True), and any `FastMCP` kwargs; `stateless_http=True` and
`json_response=True` are defaulted but overridable. A ready-to-edit example is in
[`main.py`](./main.py).

### Connecting an HTTP client

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client(
    "http://HOST:8000/mcp", headers={"baba_session_id": "my-game-1"}
) as (read, write, _):
    async with ClientSession(read, write) as s:
        await s.initialize()
        await s.call_tool("do_action", {"action": "right"})
```

## Build & run

`pyBaba` is a compiled extension and must be built against the **same Python
interpreter** this server runs under (the `.so` is ABI-specific). Building it needs
`cmake` + a vcpkg toolchain (see the repo `README.md` / `Dockerfile` for the full
toolchain: `autoconf autoconf-archive automake libtool pkg-config ninja-build zip`,
plus `cmake>=3.31.6`). From the repo root:

```bash
export VCPKG_ROOT=/path/to/vcpkg            # bootstrapped vcpkg checkout
export VCPKG_EXTRA_CURL_OPTS=-k             # only if behind SSL interception

# 1. Sync this MCP project's environment. This builds + installs the local
#    `pybaba` (via vcpkg) and `mcp` into Extensions/BabaMCP/.venv.
uv sync --project Extensions/BabaMCP

# 2a. Run over stdio (default).
uv run --project Extensions/BabaMCP baba-mcp

# 2b. Or run over HTTP (streamable-http at http://0.0.0.0:8000/mcp).
BABA_MCP_TRANSPORT=http BABA_MCP_HOST=0.0.0.0 BABA_MCP_PORT=8000 \
  uv run --project Extensions/BabaMCP baba-mcp
# 2c. Or run your own entry point (see main.py / the factory above).
uv run --project Extensions/BabaMCP python Extensions/BabaMCP/main.py
```

The console entry `baba-mcp` is env-driven: `BABA_MCP_TRANSPORT` (`stdio` default
| `http`), `BABA_MCP_HOST` (default `0.0.0.0`), `BABA_MCP_PORT` (default `8000`),
`BABA_MCP_HTTP_PATH` (default `/mcp`).

If you prefer to build the extension in place (matching the repo's Python tests):

```bash
python setup.py build_ext --inplace        # produces pyBaba.cpython-3XX-*.so at the repo root
```

The server adds the repo root to `sys.path`, so an in-place `pyBaba*.so` is found
regardless of where the server is launched from.

### Container image (HTTP) + enroot `.sqsh`

`Dockerfile.mcp` (at the repo root) builds a self-contained image whose entrypoint
starts the **HTTP** MCP; the port is set with the `BABA_MCP_PORT` env var. It builds
`pyBaba` against a pinned uv-managed CPython 3.12 used for both build and runtime
(so the module ABI always matches).

```bash
# Build (uses the heavy vcpkg toolchain; ~15 min cold).
docker build -f Dockerfile.mcp -t baba-mcp:latest .

# Run — pick the port with BABA_MCP_PORT.
docker run --rm -e BABA_MCP_PORT=8000 -p 8000:8000 baba-mcp:latest
# serves streamable-http at http://0.0.0.0:8000/mcp ; clients send a
# `baba_session_id` header (see "Connecting an HTTP client").
```

Override the port (or any other `BABA_MCP_*`) at run time, e.g.
`docker run -e BABA_MCP_PORT=9000 -p 9000:9000 baba-mcp:latest`.

For Slurm/pyxis clusters, produce an enroot squashfs from the image:

```bash
enroot import -o baba-mcp.sqsh dockerd://baba-mcp:latest
# then, e.g.:  srun --container-image=./baba-mcp.sqsh --container-env=BABA_MCP_PORT=8000 ...
```

The import captures the image's `BABA_MCP_*` env and the entrypoint
(`/opt/venv/bin/python -m baba_mcp.server`), so the `.sqsh` starts the HTTP server
directly; override `BABA_MCP_PORT` via your scheduler's env mechanism.

### Build on a bare CPU node (from scratch)

These are the exact, reproducible steps for a fresh, minimal Linux CPU node (the
kind this was first built on). The node had `git`, `g++`, `make`, `curl`, `unzip`,
`tar`, and `uv` available, but **no** `cmake`, `vcpkg`, `zip`, `autotools`, or
Python build tooling. Run as root (for `apt-get`); the heavy step is vcpkg building
its dependencies (it compiles **CPython, OpenSSL, etc. from source** — use all
cores, ~10–15 min on 32 cores).

```bash
REPO=/path/to/baba-is-auto            # this repository
cd "$REPO"

# 1. System packages. zip + autotools are REQUIRED — several vcpkg ports
#    (e.g. libb2) fail their autoreconf/archive steps without them.
apt-get update
apt-get install -y \
    zip unzip tar curl git \
    build-essential pkg-config \
    autoconf autoconf-archive automake libtool \
    ninja-build

# 2. cmake (>=3.31.6) + ninja. The system Python here has no pip, so install
#    cmake via a throwaway uv venv (or use apt if it ships a new enough cmake).
uv venv --python 3.10 .buildvenv
uv pip install --python .buildvenv "cmake>=3.31.6" ninja
export PATH="$REPO/.buildvenv/bin:$PATH"

# 3. vcpkg. Use a FULL clone, not --depth 1: vcpkg.json pins a builtin-baseline
#    commit that a shallow clone won't contain (you'd hit "failed to git show
#    versions/baseline.json"). If you already shallow-cloned, run
#    `git -C $VCPKG_ROOT fetch --unshallow`.
export VCPKG_ROOT="$HOME/vcpkg"
export VCPKG_EXTRA_CURL_OPTS="-k"          # only if behind SSL interception
git clone https://github.com/microsoft/vcpkg.git "$VCPKG_ROOT"
"$VCPKG_ROOT/bootstrap-vcpkg.sh" -disableMetrics

# 4. A venv for the BUILD + RUN interpreter. The pyBaba .so is ABI-specific, so
#    the interpreter used here must match the one that runs the server. The
#    system Python lacks setuptools, hence a dedicated venv.
uv venv --python 3.12 .venv
uv pip install --python .venv setuptools wheel pybind11 mcp

# 5. Build the extension in place (uses all cores via -j; vcpkg at concurrency
#    = cores). Produces pyBaba.cpython-3XX-*.so at the repo root.
.venv/bin/python setup.py build_ext --inplace
ls pyBaba*.so

# 6. (Optional) Sync the MCP project env. With the vcpkg binary cache now warm,
#    this rebuilds pyBaba in seconds rather than re-compiling dependencies.
uv sync --project Extensions/BabaMCP
```

Quick sanity check, then run:

```bash
.venv/bin/python -c "import pyBaba; g=pyBaba.Game('Resources/Maps/baba_is_you.txt'); print(g.GetMap().GetWidth(), g.GetPlayState().name)"
uv run --project Extensions/BabaMCP baba-mcp
```

**Gotchas seen on a bare node (each one aborts the build):**

- Missing `zip` → vcpkg bootstrap refuses to run.
- Missing autotools (`autoconf`/`automake`/`libtool`/`autoconf-archive`) → vcpkg
  ports like `libb2` fail in `autoreconf`.
- Shallow vcpkg clone → baseline commit missing (`git show versions/baseline.json`
  fails). Use a full clone or `git fetch --unshallow`.
- `cmake` missing or older than 3.31.6 → top-level `CMakeLists.txt` rejects it.
- Building/running the server with a different Python than the one that built the
  `.so` → `ImportError` (ABI mismatch).

### Interactive testing

`main.py` exposes a module-level `mcp` instance for the inspector:

```bash
uv run --project Extensions/BabaMCP mcp dev Extensions/BabaMCP/main.py
```

## Registering with a client

**stdio** — Claude Code / Claude Desktop `mcpServers` entry:

```json
{
  "mcpServers": {
    "baba": {
      "command": "uv",
      "args": ["run", "--project", "/ABS/PATH/Extensions/BabaMCP", "baba-mcp"]
    }
  }
}
```

**HTTP** — point the client at the URL and pass the session header:

```json
{
  "mcpServers": {
    "baba": {
      "url": "http://HOST:8000/mcp",
      "headers": { "baba_session_id": "my-game-1" }
    }
  }
}
```

## Configuration

- `BABA_REPO_ROOT` — override the detected repo root (where map paths are resolved from).
- `BABA_MAPS_DIR` — override the maps directory (default `Resources/Maps`).
- `BABA_MCP_TRANSPORT` / `BABA_MCP_HOST` / `BABA_MCP_PORT` / `BABA_MCP_HTTP_PATH` —
  transport selection for the `baba-mcp` console entry (see [Build & run](#build--run)).

## Notes

- **Sessions** are in-memory and live only as long as the process. Each holds a
  live game keyed by `baba_session_id`; `load_map`/`load_raw_map`/`reset` clear that
  session's `undo` history. The store is capped (`max_sessions`, FIFO eviction).
- **Single process only.** Because state lives in one process's memory, run a single
  worker. Multiple worker processes would not share sessions (you'd need an external
  store).
- **Security.** The HTTP server is **unauthenticated** and binding `0.0.0.0` does not
  enable DNS-rebind protection — run it on a trusted network or behind a reverse
  proxy / auth layer. Pass `TransportSecuritySettings` via the factory if you need
  host/origin allow-lists.
