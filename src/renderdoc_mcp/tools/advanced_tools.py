"""Advanced tools: pixel_history, get_post_vs_data, diff_draw_calls, analyze_render_passes."""

from __future__ import annotations

import struct
from typing import Optional

from mcp.server.fastmcp import FastMCP

from renderdoc_mcp.session import get_session
from renderdoc_mcp.util import (
    rd,
    to_json,
    make_error,
    flags_to_list,
    MESH_DATA_STAGE_MAP,
)


def register(mcp: FastMCP):
    @mcp.tool()
    def pixel_history(
        resource_id: str,
        x: int,
        y: int,
    ) -> str:
        """Get the full modification history of a pixel across all events in the frame.

        Shows every event that wrote to this pixel, with before/after values and
        pass/fail status (depth test, stencil test, etc.).

        Args:
            resource_id: The texture resource ID (must be a render target).
            x: X coordinate of the pixel.
            y: Y coordinate of the pixel.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        if session.current_event is None:
            return to_json(make_error("No event selected. Use set_event first.", "INVALID_EVENT_ID"))

        tex_id = session.resolve_resource_id(resource_id)
        if tex_id is None:
            return to_json(make_error(f"Texture resource '{resource_id}' not found", "INVALID_RESOURCE_ID"))

        history = session.controller.PixelHistory(
            tex_id, x, y, rd.Subresource(0, 0, 0), rd.CompType.Typeless,
        )

        results = []
        for mod in history:
            entry: dict = {
                "event_id": mod.eventId,
                "passed": mod.Passed(),
            }
            # Pre-modification value
            pre = mod.preMod
            entry["pre_value"] = {
                "r": pre.col.floatValue[0],
                "g": pre.col.floatValue[1],
                "b": pre.col.floatValue[2],
                "a": pre.col.floatValue[3],
                "depth": pre.depth,
                "stencil": pre.stencil,
            }
            # Post-modification value
            post = mod.postMod
            entry["post_value"] = {
                "r": post.col.floatValue[0],
                "g": post.col.floatValue[1],
                "b": post.col.floatValue[2],
                "a": post.col.floatValue[3],
                "depth": post.depth,
                "stencil": post.stencil,
            }

            # Check if pixel actually changed
            entry["pixel_changed"] = (
                pre.col.floatValue[0] != post.col.floatValue[0]
                or pre.col.floatValue[1] != post.col.floatValue[1]
                or pre.col.floatValue[2] != post.col.floatValue[2]
                or pre.col.floatValue[3] != post.col.floatValue[3]
            )

            results.append(entry)

        return to_json({
            "resource_id": resource_id,
            "x": x,
            "y": y,
            "modifications": results,
            "count": len(results),
        })

    @mcp.tool()
    def get_post_vs_data(
        stage: str = "vsout",
        max_vertices: int = 100,
        event_id: Optional[int] = None,
    ) -> str:
        """Get post-vertex-shader transformed vertex data for the current draw call.

        Args:
            stage: Data stage: "vsin" (vertex input), "vsout" (after vertex shader),
                  "gsout" (after geometry shader). Default: "vsout".
            max_vertices: Maximum number of vertices to return (default 100).
            event_id: Optional event ID to navigate to first.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        err = session.ensure_event(event_id)
        if err:
            return to_json(err)

        mesh_stage = MESH_DATA_STAGE_MAP.get(stage.lower())
        if mesh_stage is None:
            return to_json(make_error(
                f"Unknown mesh stage: {stage}. Valid: {list(MESH_DATA_STAGE_MAP.keys())}",
                "API_ERROR",
            ))

        postvs = session.controller.GetPostVSData(0, 0, mesh_stage)

        if postvs.vertexResourceId == rd.ResourceId.Null():
            return to_json(make_error("No post-VS data available for current event", "API_ERROR"))

        # Get the output signature to know the attribute layout
        state = session.controller.GetPipelineState()
        if stage.lower() == "vsin":
            # For vertex input, use vertex input attributes
            attrs = state.GetVertexInputs()
            attr_info = [{"name": a.name, "format": str(a.format)} for a in attrs]
        else:
            vs_refl = state.GetShaderReflection(rd.ShaderStage.Vertex)
            if vs_refl is None:
                return to_json(make_error("No vertex shader bound", "API_ERROR"))
            attr_info = []
            for sig in vs_refl.outputSignature:
                name = sig.semanticIdxName if sig.varName == "" else sig.varName
                attr_info.append({
                    "name": name,
                    "var_type": str(sig.varType),
                    "comp_count": sig.compCount,
                    "system_value": str(sig.systemValue),
                })

        # Read vertex data
        num_verts = min(postvs.numIndices, max_vertices)
        data = session.controller.GetBufferData(
            postvs.vertexResourceId, postvs.vertexByteOffset,
            num_verts * postvs.vertexByteStride,
        )

        # Parse vertices as float arrays
        vertices = []
        floats_per_vertex = postvs.vertexByteStride // 4
        for i in range(num_verts):
            offset = i * postvs.vertexByteStride
            if offset + postvs.vertexByteStride > len(data):
                break
            vertex_floats = list(struct.unpack_from(
                f"{floats_per_vertex}f", data, offset
            ))
            vertices.append([round(f, 6) for f in vertex_floats])

        return to_json({
            "stage": stage,
            "event_id": session.current_event,
            "attributes": attr_info,
            "vertex_stride": postvs.vertexByteStride,
            "total_vertices": postvs.numIndices,
            "returned_vertices": len(vertices),
            "vertices": vertices,
        })

    @mcp.tool()
    def diff_draw_calls(eid1: int, eid2: int) -> str:
        """Compare two draw calls and return their state differences.

        Useful for understanding what changed between two similar draw calls.

        Args:
            eid1: Event ID of the first draw call.
            eid2: Event ID of the second draw call.
        """
        from renderdoc_mcp.tools.pipeline_tools import _get_draw_state_dict

        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)

        state1 = _get_draw_state_dict(session, eid1)
        if "error" in state1:
            return to_json(state1)

        state2 = _get_draw_state_dict(session, eid2)
        if "error" in state2:
            return to_json(state2)

        diff = _diff_dicts(state1, state2)

        return to_json({
            "eid1": eid1,
            "eid2": eid2,
            "differences": diff,
            "identical": len(diff) == 0,
        })

    @mcp.tool()
    def analyze_render_passes() -> str:
        """Auto-detect render pass boundaries and summarize each pass.

        Detects passes by Clear actions and output target changes.
        Returns a list of render passes with draw count, RT info, and event range.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)

        sf = session.structured_file
        passes: list[dict] = []
        current_pass: dict | None = None
        last_outputs: tuple | None = None

        for eid in sorted(session._action_map.keys()):
            action = session._action_map[eid]
            is_clear = bool(action.flags & rd.ActionFlags.Clear)
            is_draw = bool(action.flags & rd.ActionFlags.Drawcall)

            if not is_clear and not is_draw:
                continue

            # Determine current outputs
            outputs = tuple(str(o) for o in action.outputs if int(o) != 0)

            # Detect pass boundary: clear or output target change
            new_pass = False
            if is_clear:
                new_pass = True
            elif outputs and outputs != last_outputs:
                new_pass = True

            if new_pass and (is_clear or current_pass is None):
                # Start a new pass
                if current_pass is not None:
                    passes.append(current_pass)
                current_pass = {
                    "pass_index": len(passes),
                    "start_event": eid,
                    "end_event": eid,
                    "start_action": action.GetName(sf),
                    "draw_count": 0,
                    "clear_count": 0,
                    "render_targets": list(outputs) if outputs else [],
                }

            if current_pass is None:
                current_pass = {
                    "pass_index": 0,
                    "start_event": eid,
                    "end_event": eid,
                    "start_action": action.GetName(sf),
                    "draw_count": 0,
                    "clear_count": 0,
                    "render_targets": list(outputs) if outputs else [],
                }

            current_pass["end_event"] = eid
            if is_draw:
                current_pass["draw_count"] += 1
            if is_clear:
                current_pass["clear_count"] += 1

            if outputs:
                last_outputs = outputs
                # Update RT info if changed within pass
                for o in outputs:
                    if o not in current_pass["render_targets"]:
                        current_pass["render_targets"].append(o)

        if current_pass is not None:
            passes.append(current_pass)

        # Enrich with RT size info
        for p in passes:
            rt_info = []
            for rid_str in p["render_targets"]:
                entry: dict = {"resource_id": rid_str}
                tex_desc = session.get_texture_desc(rid_str)
                if tex_desc is not None:
                    entry["size"] = f"{tex_desc.width}x{tex_desc.height}"
                    entry["format"] = str(tex_desc.format.Name())
                rt_info.append(entry)
            p["render_target_info"] = rt_info

        return to_json({
            "passes": passes,
            "total_passes": len(passes),
        })


def _diff_dicts(d1: dict, d2: dict, path: str = "") -> dict:
    """Recursively diff two dicts, returning only differing keys."""
    diff: dict = {}
    all_keys = set(d1.keys()) | set(d2.keys())

    for key in all_keys:
        key_path = f"{path}.{key}" if path else key
        v1 = d1.get(key)
        v2 = d2.get(key)

        if v1 == v2:
            continue

        if isinstance(v1, dict) and isinstance(v2, dict):
            sub = _diff_dicts(v1, v2, key_path)
            if sub:
                diff[key] = sub
        elif isinstance(v1, list) and isinstance(v2, list):
            if v1 != v2:
                diff[key] = {"eid1": v1, "eid2": v2}
        else:
            diff[key] = {"eid1": v1, "eid2": v2}

    return diff
