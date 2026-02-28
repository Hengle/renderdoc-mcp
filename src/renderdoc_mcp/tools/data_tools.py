"""Data extraction tools: save_texture, get_buffer_data, pick_pixel, get_texture_stats, export_draw_textures, save_render_target, export_mesh."""

from __future__ import annotations

import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from renderdoc_mcp.session import get_session
from renderdoc_mcp.util import (
    rd,
    to_json,
    make_error,
    FILE_TYPE_MAP,
    SHADER_STAGE_MAP,
    MESH_DATA_STAGE_MAP,
)


MAX_BUFFER_READ = 65536  # 64 KB limit


def register(mcp: FastMCP):
    @mcp.tool()
    def save_texture(
        resource_id: str,
        output_path: str,
        file_type: str = "png",
        mip: int = 0,
    ) -> str:
        """Save a texture resource to an image file.

        Args:
            resource_id: The texture resource ID string.
            output_path: Absolute path for the output file.
            file_type: Output format: png, jpg, bmp, tga, hdr, exr, dds (default: png).
            mip: Mip level to save (default 0). Use -1 for all mips (DDS only).
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

        ft = FILE_TYPE_MAP.get(file_type.lower())
        if ft is None:
            return to_json(make_error(f"Unknown file type: {file_type}. Valid: {list(FILE_TYPE_MAP.keys())}", "API_ERROR"))

        output_path = os.path.normpath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        texsave = rd.TextureSave()
        texsave.resourceId = tex_id
        texsave.destType = ft
        texsave.mip = mip
        texsave.slice.sliceIndex = 0
        texsave.alpha = rd.AlphaMapping.Preserve

        session.controller.SaveTexture(texsave, output_path)

        return to_json({
            "status": "saved",
            "output_path": output_path,
            "resource_id": resource_id,
            "file_type": file_type,
            "mip": mip,
        })

    @mcp.tool()
    def get_buffer_data(
        resource_id: str,
        offset: int = 0,
        length: int = 256,
        format: str = "hex",
    ) -> str:
        """Read raw data from a buffer resource.

        Args:
            resource_id: The buffer resource ID string.
            offset: Byte offset to start reading from (default 0).
            length: Number of bytes to read (default 256, max 65536).
            format: Output format: "hex" for hex dump, "floats" to interpret as float32 array.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)

        buf_id = session.resolve_resource_id(resource_id)
        if buf_id is None:
            return to_json(make_error(f"Buffer resource '{resource_id}' not found", "INVALID_RESOURCE_ID"))

        length = min(length, MAX_BUFFER_READ)
        data = session.controller.GetBufferData(buf_id, offset, length)

        result: dict = {
            "resource_id": resource_id,
            "offset": offset,
            "bytes_read": len(data),
        }

        if format == "floats":
            import struct
            num_floats = len(data) // 4
            floats = list(struct.unpack_from(f"{num_floats}f", data))
            result["data"] = [round(f, 6) for f in floats]
            result["format"] = "float32"
        else:
            # Hex dump - show lines of 16 bytes
            lines = []
            for i in range(0, len(data), 16):
                chunk = data[i:i+16]
                hex_part = " ".join(f"{b:02x}" for b in chunk)
                lines.append(f"{offset+i:08x}: {hex_part}")
            result["data"] = "\n".join(lines)
            result["format"] = "hex"

        return to_json(result)

    @mcp.tool()
    def pick_pixel(
        resource_id: str,
        x: int,
        y: int,
        event_id: Optional[int] = None,
    ) -> str:
        """Get the RGBA value of a specific pixel in a texture.

        Args:
            resource_id: The texture resource ID string.
            x: X coordinate of the pixel.
            y: Y coordinate of the pixel.
            event_id: Optional event ID to navigate to first.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        err = session.ensure_event(event_id)
        if err:
            return to_json(err)

        tex_id = session.resolve_resource_id(resource_id)
        if tex_id is None:
            return to_json(make_error(f"Texture resource '{resource_id}' not found", "INVALID_RESOURCE_ID"))

        # PickPixel returns a PixelValue
        val = session.controller.PickPixel(tex_id, x, y, rd.Subresource(0, 0, 0), rd.CompType.Typeless)

        return to_json({
            "resource_id": resource_id,
            "x": x,
            "y": y,
            "rgba": {
                "r": val.floatValue[0],
                "g": val.floatValue[1],
                "b": val.floatValue[2],
                "a": val.floatValue[3],
            },
            "rgba_uint": {
                "r": val.uintValue[0],
                "g": val.uintValue[1],
                "b": val.uintValue[2],
                "a": val.uintValue[3],
            },
        })

    @mcp.tool()
    def get_texture_stats(
        resource_id: str,
        event_id: Optional[int] = None,
    ) -> str:
        """Get min/max/average statistics for a texture at the current event.

        Args:
            resource_id: The texture resource ID string.
            event_id: Optional event ID to navigate to first.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        err = session.ensure_event(event_id)
        if err:
            return to_json(err)

        tex_id = session.resolve_resource_id(resource_id)
        if tex_id is None:
            return to_json(make_error(f"Texture resource '{resource_id}' not found", "INVALID_RESOURCE_ID"))

        histogram = session.controller.GetMinMax(tex_id, rd.Subresource(0, 0, 0), rd.CompType.Typeless)

        return to_json({
            "resource_id": resource_id,
            "min": {
                "r": histogram[0].floatValue[0],
                "g": histogram[0].floatValue[1],
                "b": histogram[0].floatValue[2],
                "a": histogram[0].floatValue[3],
            },
            "max": {
                "r": histogram[1].floatValue[0],
                "g": histogram[1].floatValue[1],
                "b": histogram[1].floatValue[2],
                "a": histogram[1].floatValue[3],
            },
        })

    @mcp.tool()
    def export_draw_textures(
        event_id: int,
        output_dir: str,
        skip_small: bool = True,
    ) -> str:
        """Batch export all textures bound to a draw call's pixel shader.

        Args:
            event_id: The event ID of the draw call.
            output_dir: Directory to save exported textures.
            skip_small: Skip textures 4x4 or smaller (placeholder textures). Default True.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        err = session.set_event(event_id)
        if err:
            return to_json(err)

        state = session.controller.GetPipelineState()
        ps_refl = state.GetShaderReflection(rd.ShaderStage.Pixel)
        if ps_refl is None:
            return to_json(make_error("No pixel shader bound at this event", "API_ERROR"))

        output_dir = os.path.normpath(output_dir)
        os.makedirs(output_dir, exist_ok=True)

        exported = []
        skipped = []
        for i, ro_refl in enumerate(ps_refl.readOnlyResources):
            try:
                ro_bind = state.GetReadOnlyResources(rd.ShaderStage.Pixel, i, False)
                for b in ro_bind:
                    rid_str = str(b.descriptor.resource)
                    tex_desc = session.get_texture_desc(rid_str)
                    if tex_desc is None:
                        continue

                    if skip_small and tex_desc.width <= 4 and tex_desc.height <= 4:
                        skipped.append({"name": ro_refl.name, "resource_id": rid_str,
                                        "size": f"{tex_desc.width}x{tex_desc.height}"})
                        continue

                    filename = f"{ro_refl.name}_{tex_desc.width}x{tex_desc.height}.png"
                    # Sanitize filename
                    filename = filename.replace("/", "_").replace("\\", "_")
                    out_path = os.path.join(output_dir, filename)

                    texsave = rd.TextureSave()
                    texsave.resourceId = tex_desc.resourceId
                    texsave.destType = rd.FileType.PNG
                    texsave.mip = 0
                    texsave.slice.sliceIndex = 0
                    texsave.alpha = rd.AlphaMapping.Preserve
                    session.controller.SaveTexture(texsave, out_path)

                    exported.append({
                        "name": ro_refl.name,
                        "resource_id": rid_str,
                        "size": f"{tex_desc.width}x{tex_desc.height}",
                        "output_path": out_path,
                    })
            except Exception:
                pass

        return to_json({
            "event_id": event_id,
            "exported": exported,
            "exported_count": len(exported),
            "skipped": skipped,
            "skipped_count": len(skipped),
        })

    @mcp.tool()
    def save_render_target(
        event_id: int,
        output_path: str,
        save_depth: bool = False,
    ) -> str:
        """Save the current render target(s) at a specific event.

        Args:
            event_id: The event ID to capture the render target from.
            output_path: Output file path or directory. If directory, auto-names the file.
            save_depth: Also save the depth target (default False).
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        err = session.set_event(event_id)
        if err:
            return to_json(err)

        state = session.controller.GetPipelineState()
        output_path = os.path.normpath(output_path)
        saved = []

        # Save color target
        outputs = state.GetOutputTargets()
        color_target = None
        for o in outputs:
            if int(o.resource) != 0:
                color_target = o
                break

        if color_target is None:
            return to_json(make_error("No color render target bound at this event", "API_ERROR"))

        rid_str = str(color_target.resource)
        tex_desc = session.get_texture_desc(rid_str)

        if os.path.isdir(output_path):
            fname = f"rt_color_eid{event_id}.png"
            color_path = os.path.join(output_path, fname)
        else:
            color_path = output_path
            os.makedirs(os.path.dirname(color_path), exist_ok=True)

        texsave = rd.TextureSave()
        texsave.resourceId = color_target.resource
        texsave.destType = rd.FileType.PNG
        texsave.mip = 0
        texsave.slice.sliceIndex = 0
        texsave.alpha = rd.AlphaMapping.Preserve
        session.controller.SaveTexture(texsave, color_path)

        color_info: dict = {"type": "color", "resource_id": rid_str, "output_path": color_path}
        if tex_desc is not None:
            color_info["size"] = f"{tex_desc.width}x{tex_desc.height}"
            color_info["format"] = str(tex_desc.format.Name())
        saved.append(color_info)

        # Optionally save depth target
        if save_depth:
            try:
                dt = state.GetDepthTarget()
                if int(dt.resource) != 0:
                    dt_rid = str(dt.resource)
                    if os.path.isdir(output_path):
                        depth_path = os.path.join(output_path, f"rt_depth_eid{event_id}.png")
                    else:
                        base, ext = os.path.splitext(color_path)
                        depth_path = f"{base}_depth{ext}"

                    texsave = rd.TextureSave()
                    texsave.resourceId = dt.resource
                    texsave.destType = rd.FileType.PNG
                    texsave.mip = 0
                    texsave.slice.sliceIndex = 0
                    texsave.alpha = rd.AlphaMapping.Preserve
                    session.controller.SaveTexture(texsave, depth_path)

                    depth_info: dict = {"type": "depth", "resource_id": dt_rid, "output_path": depth_path}
                    dt_desc = session.get_texture_desc(dt_rid)
                    if dt_desc is not None:
                        depth_info["size"] = f"{dt_desc.width}x{dt_desc.height}"
                        depth_info["format"] = str(dt_desc.format.Name())
                    saved.append(depth_info)
            except Exception:
                pass

        return to_json({"event_id": event_id, "saved": saved, "count": len(saved)})

    @mcp.tool()
    def export_mesh(
        event_id: int,
        output_path: str,
    ) -> str:
        """Export mesh data from a draw call as OBJ format.

        Uses post-vertex-shader data to get transformed positions, normals, and UVs.

        Args:
            event_id: The event ID of the draw call.
            output_path: Output file path for the .obj file.
        """
        import struct as _struct

        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        err = session.set_event(event_id)
        if err:
            return to_json(err)

        postvs = session.controller.GetPostVSData(0, 0, rd.MeshDataStage.VSOut)
        if postvs.vertexResourceId == rd.ResourceId.Null():
            return to_json(make_error("No post-VS data available for this event", "API_ERROR"))

        state = session.controller.GetPipelineState()
        vs_refl = state.GetShaderReflection(rd.ShaderStage.Vertex)
        if vs_refl is None:
            return to_json(make_error("No vertex shader bound", "API_ERROR"))

        # Parse output signature to find position/normal/uv offsets
        out_sig = vs_refl.outputSignature
        pos_idx = None
        norm_idx = None
        uv_idx = None
        offset_map: list[tuple[str, int, int]] = []  # (semantic, start_float, comp_count)
        float_offset = 0
        for sig in out_sig:
            name = (sig.semanticName or sig.varName or "").upper()
            if "POSITION" in name or "SV_POSITION" in name.replace("SV_Position", "SV_POSITION"):
                pos_idx = float_offset
            elif "NORMAL" in name:
                norm_idx = float_offset
            elif "TEXCOORD" in name and uv_idx is None:
                uv_idx = float_offset
            offset_map.append((name, float_offset, sig.compCount))
            float_offset += sig.compCount

        if pos_idx is None:
            # Fallback: assume first 4 floats are position
            pos_idx = 0

        num_verts = postvs.numIndices
        data = session.controller.GetBufferData(
            postvs.vertexResourceId, postvs.vertexByteOffset,
            num_verts * postvs.vertexByteStride,
        )

        floats_per_vertex = postvs.vertexByteStride // 4

        # Parse all vertices
        positions = []
        normals = []
        uvs = []
        for i in range(num_verts):
            off = i * postvs.vertexByteStride
            if off + postvs.vertexByteStride > len(data):
                break
            vfloats = list(_struct.unpack_from(f"{floats_per_vertex}f", data, off))

            # Position (x, y, z) - skip w
            if pos_idx is not None and pos_idx + 3 <= len(vfloats):
                positions.append((vfloats[pos_idx], vfloats[pos_idx + 1], vfloats[pos_idx + 2]))
            else:
                positions.append((0.0, 0.0, 0.0))

            if norm_idx is not None and norm_idx + 3 <= len(vfloats):
                normals.append((vfloats[norm_idx], vfloats[norm_idx + 1], vfloats[norm_idx + 2]))

            if uv_idx is not None and uv_idx + 2 <= len(vfloats):
                uvs.append((vfloats[uv_idx], vfloats[uv_idx + 1]))

        # Write OBJ
        output_path = os.path.normpath(output_path)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        lines = [f"# Exported from RenderDoc MCP - event {event_id}"]
        lines.append(f"# Vertices: {len(positions)}")

        for p in positions:
            lines.append(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}")

        for n in normals:
            lines.append(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}")

        for uv in uvs:
            lines.append(f"vt {uv[0]:.6f} {uv[1]:.6f}")

        # Triangles (1-indexed)
        has_normals = len(normals) == len(positions)
        has_uvs = len(uvs) == len(positions)
        for i in range(0, len(positions) - 2, 3):
            i1, i2, i3 = i + 1, i + 2, i + 3  # OBJ is 1-indexed
            if has_normals and has_uvs:
                lines.append(f"f {i1}/{i1}/{i1} {i2}/{i2}/{i2} {i3}/{i3}/{i3}")
            elif has_normals:
                lines.append(f"f {i1}//{i1} {i2}//{i2} {i3}//{i3}")
            elif has_uvs:
                lines.append(f"f {i1}/{i1} {i2}/{i2} {i3}/{i3}")
            else:
                lines.append(f"f {i1} {i2} {i3}")

        with open(output_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        return to_json({
            "event_id": event_id,
            "output_path": output_path,
            "vertices": len(positions),
            "normals": len(normals),
            "uvs": len(uvs),
            "triangles": len(positions) // 3,
        })
