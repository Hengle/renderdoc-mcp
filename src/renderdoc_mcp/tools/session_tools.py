"""Session management tools: open_capture, close_capture, get_capture_info."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from renderdoc_mcp.session import get_session
from renderdoc_mcp.util import to_json


def register(mcp: FastMCP):
    @mcp.tool()
    def open_capture(filepath: str) -> str:
        """Open a RenderDoc capture (.rdc) file for analysis.

        Automatically closes any previously opened capture.
        Returns capture overview: API type, action count, resource counts.

        Args:
            filepath: Absolute path to the .rdc capture file.
        """
        filepath = os.path.normpath(filepath)
        session = get_session()
        result = session.open(filepath)
        return to_json(result)

    @mcp.tool()
    def close_capture() -> str:
        """Close the currently open capture file and free resources."""
        session = get_session()
        return to_json(session.close())

    @mcp.tool()
    def get_capture_info() -> str:
        """Get information about the currently open capture.

        Returns API type, file path, action count, texture/buffer counts.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)

        controller = session.controller
        textures = controller.GetTextures()
        buffers = controller.GetBuffers()

        info = {
            "filepath": session.filepath,
            "total_actions": len(session._action_map),
            "textures": len(textures),
            "buffers": len(buffers),
            "current_event": session.current_event,
        }
        return to_json(info)
