# renderdoc-mcp

MCP server for [RenderDoc](https://renderdoc.org/) — let AI assistants analyze GPU frame captures (`.rdc` files) for graphics debugging and performance analysis.

Built on the [Model Context Protocol](https://modelcontextprotocol.io/), works with Claude Desktop, Claude Code, and any MCP-compatible client.

## Features

- **19 tools** covering the full RenderDoc analysis workflow
- **3 built-in prompts** for guided debugging
- **Headless** — no GUI needed, runs entirely via RenderDoc's Python replay API
- **Pure Python** — single `pip install`, no build step
- Supports D3D11, D3D12, OpenGL, Vulkan captures

## Quick Start

### 1. Prerequisites

- **Python 3.10+**
- **RenderDoc** installed ([download](https://renderdoc.org/builds))
  - You need the `renderdoc.pyd` (Windows) or `renderdoc.so` (Linux) Python module
  - It ships with every RenderDoc installation

### 2. Install

```bash
git clone https://github.com/Linkingooo/renderdoc-mcp.git
cd renderdoc-mcp
pip install -e .
```

### 3. Find your `renderdoc.pyd` path

The Python module is in your RenderDoc install directory:

| Platform | Typical path |
|----------|-------------|
| Windows  | `C:\Program Files\RenderDoc\renderdoc.pyd` |
| Linux    | `/usr/lib/renderdoc/librenderdoc.so` or where you built it |

You need the **directory** containing this file.

### 4. Configure your MCP client

<details>
<summary><b>Claude Desktop</b></summary>

Edit `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "python",
      "args": ["-m", "renderdoc_mcp"],
      "env": {
        "RENDERDOC_MODULE_PATH": "C:\\Program Files\\RenderDoc"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Claude Code</b></summary>

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "renderdoc": {
      "command": "python",
      "args": ["-m", "renderdoc_mcp"],
      "env": {
        "RENDERDOC_MODULE_PATH": "C:\\Program Files\\RenderDoc"
      }
    }
  }
}
```

</details>

<details>
<summary><b>Run standalone</b></summary>

```bash
# Set the module path
export RENDERDOC_MODULE_PATH="/path/to/renderdoc"   # Linux/macOS
set RENDERDOC_MODULE_PATH=C:\Program Files\RenderDoc  # Windows

# Run
python -m renderdoc_mcp
```

</details>

## Usage Examples

Once configured, just talk to your AI assistant:

> "Open `frame.rdc` and show me what's happening in the frame"

> "Find the draw call that renders the character model and check its pipeline state"

> "Why is my shadow map rendering black? Check the depth pass"

> "Analyze performance — are there any redundant draw calls?"

### Typical Tool Flow

```
open_capture("frame.rdc")           # Load the capture
├── list_actions()                   # See the frame structure
├── set_event(142)                   # Navigate to a draw call
│   ├── get_pipeline_state()         # Inspect rasterizer/blend/depth
│   ├── get_shader_bindings("pixel") # Check what textures/buffers are bound
│   ├── get_cbuffer_contents("pixel", 0)  # Read shader constants
│   └── save_texture(id, "rt.png")   # Export render target
├── pixel_history(id, 512, 384)      # Debug a specific pixel
└── close_capture()                  # Clean up
```

## Tools

### Session Management

| Tool | Description |
|------|-------------|
| `open_capture` | Open a `.rdc` file (auto-closes previous) |
| `close_capture` | Close current capture and free resources |
| `get_capture_info` | Capture metadata: API, action count, resource counts |

### Event Navigation

| Tool | Description |
|------|-------------|
| `list_actions` | List the draw call / action tree with depth control |
| `get_action` | Full detail for a single action |
| `set_event` | Navigate to an event (**required** before pipeline queries) |
| `search_actions` | Search by name pattern and/or action flags |

### Pipeline Inspection

| Tool | Description |
|------|-------------|
| `get_pipeline_state` | Full state: topology, viewports, rasterizer, blend, depth, stencil |
| `get_shader_bindings` | Constant buffers, SRVs, UAVs, samplers for a shader stage |
| `get_vertex_inputs` | Vertex attributes, vertex/index buffer bindings |

### Resource Analysis

| Tool | Description |
|------|-------------|
| `list_textures` | All textures (filterable by format, min width) |
| `list_buffers` | All buffers (filterable by min size) |
| `list_resources` | All named resources (filterable by type, name pattern) |
| `get_resource_usage` | Which events read/write a resource |

### Data Extraction

| Tool | Description |
|------|-------------|
| `save_texture` | Export to PNG, JPG, BMP, TGA, HDR, EXR, or DDS |
| `get_buffer_data` | Read buffer bytes (hex dump or float32 array) |
| `pick_pixel` | RGBA value at a coordinate |
| `get_texture_stats` | Per-channel min/max |

### Shader Analysis

| Tool | Description |
|------|-------------|
| `disassemble_shader` | Shader disassembly (DXBC, DXIL, SPIR-V, etc.) |
| `get_shader_reflection` | Input/output signatures, resource binding layout |
| `get_cbuffer_contents` | Actual constant buffer variable values |

### Advanced

| Tool | Description |
|------|-------------|
| `pixel_history` | Full per-pixel modification history across all events |
| `get_post_vs_data` | Post-transform vertex data (VS out / GS out) |

## Prompts

Built-in prompt templates to guide AI through common workflows:

| Prompt | Description |
|--------|-------------|
| `debug_draw_call` | Deep-dive a single draw call: pipeline → shaders → cbuffers → outputs |
| `find_rendering_issue` | Systematic diagnosis from a problem description |
| `analyze_performance` | Frame-wide perf analysis: draw call count, overdraw, wasted work |

## How It Works

```
AI Assistant ←—MCP—→ renderdoc-mcp server ←—Python API—→ renderdoc.pyd ←→ GPU replay
```

The server uses RenderDoc's headless replay API (`renderdoc.pyd`) to:
1. Open `.rdc` capture files without the GUI
2. Replay frames and query pipeline state at any event
3. Extract textures, buffers, shader data, and pixel history
4. Return structured JSON for the AI to reason about

## Development

```bash
# Install in dev mode
pip install -e .

# Run tests (no RenderDoc needed — uses mocks)
python -m pytest tests/ -v

# Project structure
src/renderdoc_mcp/
├── server.py              # FastMCP server, prompt definitions
├── session.py             # Capture lifecycle management (singleton)
├── util.py                # Serialization, enum maps, module loader
└── tools/
    ├── session_tools.py   # open/close/info
    ├── event_tools.py     # list/get/set/search actions
    ├── pipeline_tools.py  # pipeline state, shader bindings, vertex inputs
    ├── resource_tools.py  # texture/buffer/resource enumeration
    ├── data_tools.py      # texture save, buffer read, pixel pick
    ├── shader_tools.py    # disassembly, reflection, cbuffer contents
    └── advanced_tools.py  # pixel history, post-VS data
```

## License

MIT
