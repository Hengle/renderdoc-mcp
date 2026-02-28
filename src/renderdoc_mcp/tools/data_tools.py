"""Data extraction tools: save_texture, get_buffer_data, pick_pixel, get_texture_stats."""

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
)


def _find_resource_id(resource_id_str: str):
    """Resolve a resource ID string to a ResourceId object."""
    controller = get_session().controller
    for tex in controller.GetTextures():
        if str(tex.resourceId) == resource_id_str:
            return tex.resourceId
    for buf in controller.GetBuffers():
        if str(buf.resourceId) == resource_id_str:
            return buf.resourceId
    for res in controller.GetResources():
        if str(res.resourceId) == resource_id_str:
            return res.resourceId
    return None


def _find_texture_id(resource_id_str: str):
    """Resolve a resource ID string to a texture ResourceId."""
    controller = get_session().controller
    for tex in controller.GetTextures():
        if str(tex.resourceId) == resource_id_str:
            return tex.resourceId
    return None


def _find_buffer_id(resource_id_str: str):
    """Resolve a resource ID string to a buffer ResourceId."""
    controller = get_session().controller
    for buf in controller.GetBuffers():
        if str(buf.resourceId) == resource_id_str:
            return buf.resourceId
    return None


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

        tex_id = _find_texture_id(resource_id)
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

        buf_id = _find_buffer_id(resource_id)
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

        tex_id = _find_texture_id(resource_id)
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

        tex_id = _find_texture_id(resource_id)
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
