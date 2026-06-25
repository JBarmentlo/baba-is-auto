# BabaMCP

An [MCP](https://modelcontextprotocol.io) server that wraps the `pyBaba` "Baba Is
You" simulator, so an LLM/agent can play the game: observe the board grid (not an
image), make moves, check win/lose status, switch levels, and undo.

It is a thin, in-process Python layer over the `pyBaba` pybind11 module — no game
logic is reimplemented here.

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
| `list_maps()` | List built-in map names. |
| `get_rules()` | Active rules as object-name triples, e.g. `["BABA","IS","YOU"]`. |

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

# 2. Run the server (stdio transport).
uv run --project Extensions/BabaMCP baba-mcp
```

If you prefer to build the extension in place (matching the repo's Python tests):

```bash
python setup.py build_ext --inplace        # produces pyBaba.cpython-3XX-*.so at the repo root
```

The server adds the repo root to `sys.path`, so an in-place `pyBaba*.so` is found
regardless of where the server is launched from.

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

```bash
uv run --project Extensions/BabaMCP mcp dev Extensions/BabaMCP/baba_mcp/server.py
```

## Registering with a client

Claude Code / Claude Desktop `mcpServers` entry:

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

## Configuration

- `BABA_REPO_ROOT` — override the detected repo root (where map paths are resolved from).
- `BABA_MAPS_DIR` — override the maps directory (default `Resources/Maps`).

## Notes

- The server holds a single global "current game"; `load_map`/`load_raw_map`/`reset`
  clear the move history used by `undo`. This is designed for a single client over
  stdio. For a multi-client/HTTP transport you would need per-session game state.
