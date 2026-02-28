"""Advanced tools: pixel_history, get_post_vs_data."""

from __future__ import annotations

import struct
from typing import Optional

from mcp.server.fastmcp import FastMCP

from renderdoc_mcp.session import get_session
from renderdoc_mcp.util import (
    rd,
    to_json,
    make_error,
    MESH_DATA_STAGE_MAP,
)


def _find_texture_id(resource_id_str: str):
    controller = get_session().controller
    for tex in controller.GetTextures():
        if str(tex.resourceId) == resource_id_str:
            return tex.resourceId
    return None


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

        tex_id = _find_texture_id(resource_id)
        if tex_id is None:
            return to_json(make_error(f"Texture resource '{resource_id}' not found", "INVALID_RESOURCE_ID"))

        history = session.controller.PixelHistory(
            tex_id, x, y, rd.Subresource(0, 0, 0), rd.CompType.Typeless,
        )

        results = []
        for mod in history:
            entry: dict = {
                "event_id": mod.eventId,
                "passed": not mod.Passed(),
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
