"""FastMCP server — registers all tools, resources, and prompts."""

from __future__ import annotations

import atexit

from mcp.server.fastmcp import FastMCP

from renderdoc_mcp.session import get_session
from renderdoc_mcp.tools import (
    session_tools,
    event_tools,
    pipeline_tools,
    resource_tools,
    data_tools,
    shader_tools,
    advanced_tools,
)

mcp = FastMCP(
    "renderdoc-mcp",
    description="RenderDoc graphics debugger MCP server — analyze GPU frame captures (.rdc) with AI",
)

# ── Register all tool modules ──

session_tools.register(mcp)
event_tools.register(mcp)
pipeline_tools.register(mcp)
resource_tools.register(mcp)
data_tools.register(mcp)
shader_tools.register(mcp)
advanced_tools.register(mcp)


# ── Prompts ──

@mcp.prompt()
def debug_draw_call(event_id: int) -> str:
    """Deep-dive analysis of a single draw call.

    Guides through: pipeline state, shader bindings, constant buffers, render targets.
    """
    return f"""Analyze draw call at event {event_id} step by step:

1. First, call `set_event` with event_id={event_id} and `get_action` to understand what this draw call does.
2. Call `get_pipeline_state` to inspect the full pipeline configuration:
   - Check topology, viewports, scissors
   - Check rasterizer state (cull mode, fill mode)
   - Check depth/stencil state
   - Check blend state
3. Call `get_vertex_inputs` to see vertex layout and buffer bindings.
4. For each bound shader stage (vertex, pixel, etc.):
   a. Call `get_shader_bindings` to see what resources are bound
   b. Call `get_shader_reflection` to understand the shader interface
   c. For each constant buffer, call `get_cbuffer_contents` to read actual values
5. Check the render target outputs — if textures are bound, consider using `save_texture`
   or `pick_pixel` to inspect the results.
6. Summarize findings: what this draw call renders, any potential issues found."""


@mcp.prompt()
def find_rendering_issue(description: str) -> str:
    """Guide AI through diagnosing a rendering problem.

    Start from a user description and systematically check common causes.
    """
    return f"""The user reports a rendering issue: "{description}"

Investigate step by step:

1. First, call `list_actions` to get an overview of the frame structure.
2. Use `search_actions` to find draw calls related to the issue:
   - Search by name if the user mentioned specific objects/passes
   - Filter by flags (Drawcall, Clear, etc.) to narrow down
3. For suspicious draw calls, use `set_event` + `get_pipeline_state` to check:
   - Is depth testing configured correctly? (depth_enable, depth_function, depth_write_mask)
   - Is blending set up properly? (enabled, source/dest factors)
   - Is culling correct? (cull_mode, front_ccw)
   - Are scissors/viewports reasonable?
4. Check shader bindings with `get_shader_bindings` — are all expected resources bound?
5. Use `get_cbuffer_contents` to verify shader parameters (transforms, colors, etc.)
6. Use `save_texture` on render targets to visualize intermediate results.
7. If overdraw is suspected, use `pixel_history` on affected pixels.
8. Summarize the root cause and suggest fixes."""


@mcp.prompt()
def analyze_performance() -> str:
    """Performance analysis workflow for a captured frame."""
    return """Analyze the frame for performance issues:

1. Call `list_actions` with max_depth=1 to get a high-level view of the frame structure.
2. Call `search_actions` with flags=["Drawcall"] to count total draw calls.
3. Look for performance red flags:
   a. Search for draw calls with very high vertex counts (numIndices)
   b. Search for redundant Clear operations
   c. Look for draw calls with zero outputs (wasted work)
4. For the most expensive-looking draw calls:
   a. Check `get_pipeline_state` — are there unnecessary state changes?
   b. Check `get_vertex_inputs` — are vertex formats optimal?
   c. Check render target sizes with `list_textures`
5. Use `list_textures` to identify:
   - Very large textures that could be optimized
   - Unused textures (cross-reference with `get_resource_usage`)
6. Use `list_buffers` to find oversized buffers
7. Summarize findings with actionable optimization recommendations:
   - Draw call batching opportunities
   - Texture/buffer size optimizations
   - Redundant state changes
   - Potential overdraw issues"""


# ── Cleanup ──

def _cleanup():
    get_session().shutdown()

atexit.register(_cleanup)


# ── Entry point ──

def main():
    mcp.run()


if __name__ == "__main__":
    main()
