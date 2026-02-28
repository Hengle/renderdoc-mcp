"""Utility functions: renderdoc module loading, serialization helpers, enum mappings."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


def load_renderdoc():
    """Load the renderdoc Python module, configuring paths from environment."""
    if "renderdoc" in sys.modules:
        return sys.modules["renderdoc"]

    module_path = os.environ.get("RENDERDOC_MODULE_PATH", "")
    if module_path:
        if module_path not in sys.path:
            sys.path.insert(0, module_path)
        if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(module_path)

    import renderdoc  # noqa: E402

    return renderdoc


rd = load_renderdoc()

# ── Shader stage mapping ──

SHADER_STAGE_MAP: dict[str, Any] = {
    "vertex": rd.ShaderStage.Vertex,
    "hull": rd.ShaderStage.Hull,
    "domain": rd.ShaderStage.Domain,
    "geometry": rd.ShaderStage.Geometry,
    "pixel": rd.ShaderStage.Pixel,
    "compute": rd.ShaderStage.Compute,
}

# ── FileType mapping ──

FILE_TYPE_MAP: dict[str, Any] = {
    "png": rd.FileType.PNG,
    "jpg": rd.FileType.JPG,
    "bmp": rd.FileType.BMP,
    "tga": rd.FileType.TGA,
    "hdr": rd.FileType.HDR,
    "exr": rd.FileType.EXR,
    "dds": rd.FileType.DDS,
}

# ── MeshDataStage mapping ──

MESH_DATA_STAGE_MAP: dict[str, Any] = {
    "vsin": rd.MeshDataStage.VSIn,
    "vsout": rd.MeshDataStage.VSOut,
    "gsout": rd.MeshDataStage.GSOut,
}


# ── Error helpers ──

def make_error(message: str, code: str = "API_ERROR") -> dict:
    """Return a standardized error dict."""
    return {"error": message, "code": code}


def result_or_raise(result, message: str = "RenderDoc API call failed"):
    """Check a ResultCode and raise RuntimeError on failure."""
    if result != rd.ResultCode.Succeeded:
        raise RuntimeError(f"{message}: {result}")


# ── ActionFlags helpers ──

_ACTION_FLAG_NAMES: dict[int, str] | None = None


def _build_flag_names() -> dict[int, str]:
    """Build a mapping of single-bit flag values to their names."""
    names: dict[int, str] = {}
    for attr in dir(rd.ActionFlags):
        if attr.startswith("_"):
            continue
        val = getattr(rd.ActionFlags, attr)
        if isinstance(val, int) and val != 0 and (val & (val - 1)) == 0:
            names[val] = attr
    return names


def flags_to_list(flags: int) -> list[str]:
    """Convert an ActionFlags bitmask to a list of flag name strings."""
    global _ACTION_FLAG_NAMES
    if _ACTION_FLAG_NAMES is None:
        _ACTION_FLAG_NAMES = _build_flag_names()
    result = []
    for bit, name in _ACTION_FLAG_NAMES.items():
        if flags & bit:
            result.append(name)
    return result


# ── Serialization helpers ──

def serialize_action(action, structured_file, depth: int = 0, max_depth: int = 2) -> dict:
    """Serialize an ActionDescription to a dict."""
    result = {
        "event_id": action.eventId,
        "name": action.GetName(structured_file),
        "flags": flags_to_list(action.flags),
        "num_indices": action.numIndices,
        "num_instances": action.numInstances,
    }
    outputs = []
    for o in action.outputs:
        rid = int(o)
        if rid != 0:
            outputs.append(str(o))
    if outputs:
        result["outputs"] = outputs
    depth_id = int(action.depthOutput)
    if depth_id != 0:
        result["depth_output"] = str(action.depthOutput)

    if depth < max_depth and len(action.children) > 0:
        result["children"] = [
            serialize_action(c, structured_file, depth + 1, max_depth)
            for c in action.children
        ]
    elif len(action.children) > 0:
        result["children_count"] = len(action.children)

    return result


def serialize_action_detail(action, structured_file) -> dict:
    """Serialize a single ActionDescription with full detail (no depth limit on self, but no children expansion)."""
    result = {
        "event_id": action.eventId,
        "name": action.GetName(structured_file),
        "flags": flags_to_list(action.flags),
        "num_indices": action.numIndices,
        "num_instances": action.numInstances,
        "index_offset": action.indexOffset,
        "base_vertex": action.baseVertex,
        "vertex_offset": action.vertexOffset,
        "instance_offset": action.instanceOffset,
        "drawIndex": action.drawIndex,
    }
    outputs = []
    for o in action.outputs:
        rid = int(o)
        if rid != 0:
            outputs.append(str(o))
    result["outputs"] = outputs

    depth_id = int(action.depthOutput)
    result["depth_output"] = str(action.depthOutput) if depth_id != 0 else None

    if action.parent:
        result["parent_event_id"] = action.parent.eventId
    if action.previous:
        result["previous_event_id"] = action.previous.eventId
    if action.next:
        result["next_event_id"] = action.next.eventId
    result["children_count"] = len(action.children)

    return result


def serialize_texture_desc(tex) -> dict:
    """Serialize a TextureDescription to a dict."""
    return {
        "resource_id": str(tex.resourceId),
        "name": tex.name if hasattr(tex, "name") else "",
        "width": tex.width,
        "height": tex.height,
        "depth": tex.depth,
        "array_size": tex.arraysize,
        "mips": tex.mips,
        "format": str(tex.format.Name()),
        "dimension": tex.dimension,
        "msqual": tex.msQual,
        "mssamp": tex.msSamp,
        "creation_flags": tex.creationFlags,
    }


def serialize_buffer_desc(buf) -> dict:
    """Serialize a BufferDescription to a dict."""
    return {
        "resource_id": str(buf.resourceId),
        "name": buf.name if hasattr(buf, "name") else "",
        "length": buf.length,
        "creation_flags": buf.creationFlags,
    }


def serialize_resource_desc(res) -> dict:
    """Serialize a ResourceDescription to a dict."""
    return {
        "resource_id": str(res.resourceId),
        "name": res.name,
        "type": str(res.type),
    }


def serialize_shader_variable(var, max_depth: int = 10, depth: int = 0) -> dict:
    """Recursively serialize a ShaderVariable to a dict."""
    result: dict[str, Any] = {"name": var.name}
    if len(var.members) == 0:
        # Leaf variable - extract values
        values = []
        for r in range(var.rows):
            row_vals = []
            for c in range(var.columns):
                row_vals.append(var.value.f32v[r * var.columns + c])
            values.append(row_vals)
        # Flatten single-row results
        if len(values) == 1:
            result["value"] = values[0]
        else:
            result["value"] = values
        result["rows"] = var.rows
        result["columns"] = var.columns
    elif depth < max_depth:
        result["members"] = [
            serialize_shader_variable(m, max_depth, depth + 1) for m in var.members
        ]
    return result


def serialize_usage_entry(usage) -> dict:
    """Serialize a single EventUsage entry."""
    return {
        "event_id": usage.eventId,
        "usage": str(usage.usage),
    }


def serialize_sig_element(sig) -> dict:
    """Serialize a SigParameter (shader signature element)."""
    return {
        "var_name": sig.varName,
        "semantic_name": sig.semanticName,
        "semantic_index": sig.semanticIndex,
        "semantic_idx_name": sig.semanticIdxName,
        "var_type": str(sig.varType),
        "comp_count": sig.compCount,
        "system_value": str(sig.systemValue),
        "reg_index": sig.regIndex,
    }


def to_json(obj: Any) -> str:
    """Serialize to compact JSON string."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
