"""Pipeline inspection tools: get_pipeline_state, get_shader_bindings, get_vertex_inputs, get_draw_call_state."""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from renderdoc_mcp.session import get_session
from renderdoc_mcp.util import (
    rd,
    to_json,
    make_error,
    SHADER_STAGE_MAP,
    BLEND_FACTOR_MAP,
    BLEND_OP_MAP,
    COMPARE_FUNC_MAP,
    STENCIL_OP_MAP,
    CULL_MODE_MAP,
    FILL_MODE_MAP,
    TOPOLOGY_MAP,
    enum_str,
    blend_formula,
    serialize_sig_element,
)


def _serialize_viewport(vp) -> dict:
    return {
        "x": vp.x, "y": vp.y,
        "width": vp.width, "height": vp.height,
        "min_depth": vp.minDepth, "max_depth": vp.maxDepth,
    }


def _serialize_scissor(sc) -> dict:
    return {
        "x": sc.x, "y": sc.y,
        "width": sc.width, "height": sc.height,
    }


def _serialize_blend_eq(eq) -> dict:
    return {
        "source": enum_str(eq.source, BLEND_FACTOR_MAP, "BlendFactor."),
        "destination": enum_str(eq.destination, BLEND_FACTOR_MAP, "BlendFactor."),
        "operation": enum_str(eq.operation, BLEND_OP_MAP, "BlendOp."),
    }


def _serialize_pipeline_state(state) -> dict:
    """Extract a comprehensive pipeline state summary."""
    result: dict = {}

    # Shader stages
    shaders = {}
    for name, stage in SHADER_STAGE_MAP.items():
        if stage == rd.ShaderStage.Compute:
            continue
        refl = state.GetShaderReflection(stage)
        if refl is not None:
            shaders[name] = {
                "bound": True,
                "entry_point": state.GetShaderEntryPoint(stage),
                "resource_id": str(refl.resourceId),
            }
        else:
            shaders[name] = {"bound": False}
    result["shaders"] = shaders

    # Input assembly
    try:
        topo = state.GetPrimitiveTopology()
        result["topology"] = enum_str(topo, TOPOLOGY_MAP, "Topology.")
    except Exception:
        pass

    # Viewports and scissors
    try:
        viewports = state.GetViewports()
        result["viewports"] = [_serialize_viewport(vp) for vp in viewports]
    except Exception:
        pass

    try:
        scissors = state.GetScissors()
        result["scissors"] = [_serialize_scissor(sc) for sc in scissors]
    except Exception:
        pass

    # Rasterizer state
    try:
        raster = state.GetRasterizer()
        result["rasterizer"] = {
            "fill_mode": enum_str(raster.fillMode, FILL_MODE_MAP, "FillMode."),
            "cull_mode": enum_str(raster.cullMode, CULL_MODE_MAP, "CullMode."),
            "front_ccw": raster.frontCCW,
            "depth_bias": raster.depthBias,
            "depth_clip": raster.depthClip,
            "scissor_enable": raster.scissorEnable,
            "multisample_enable": raster.multisampleEnable,
        }
    except Exception:
        pass

    # Color blend
    try:
        cb = state.GetColorBlend()
        blends = []
        for b in cb.blends:
            color_eq = _serialize_blend_eq(b.colorBlend)
            alpha_eq = _serialize_blend_eq(b.alphaBlend)
            entry = {
                "enabled": b.enabled,
                "write_mask": b.writeMask,
                "color": color_eq,
                "alpha": alpha_eq,
            }
            if b.enabled:
                entry["formula"] = blend_formula(
                    color_eq["source"], color_eq["destination"], color_eq["operation"],
                    alpha_eq["source"], alpha_eq["destination"], alpha_eq["operation"],
                )
            blends.append(entry)
        result["color_blend"] = {
            "blend_factor": [cb.blendFactor.x, cb.blendFactor.y, cb.blendFactor.z, cb.blendFactor.w],
            "blends": blends,
        }
    except Exception:
        pass

    # Depth state
    try:
        ds = state.GetDepthState()
        result["depth_state"] = {
            "depth_enable": ds.depthEnable,
            "depth_function": enum_str(ds.depthFunction, COMPARE_FUNC_MAP, "CompareFunc."),
            "depth_write_mask": ds.depthWrites,
        }
    except Exception:
        pass

    # Stencil state
    try:
        ss = state.GetStencilState()
        result["stencil_state"] = {
            "stencil_enable": ss.stencilEnable,
        }
    except Exception:
        pass

    # Output targets
    try:
        outputs = state.GetOutputTargets()
        result["output_targets"] = [
            {"resource_id": str(o.resource)} for o in outputs if int(o.resource) != 0
        ]
    except Exception:
        pass

    try:
        depth = state.GetDepthTarget()
        if int(depth.resource) != 0:
            result["depth_target"] = {"resource_id": str(depth.resource)}
    except Exception:
        pass

    return result


def register(mcp: FastMCP):
    @mcp.tool()
    def get_pipeline_state(event_id: Optional[int] = None) -> str:
        """Get the full graphics pipeline state at the current or specified event.

        Returns topology, viewports, scissors, rasterizer, blend, depth, stencil state,
        bound shaders, and output targets.

        Args:
            event_id: Optional event ID to navigate to first. Uses current event if omitted.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        err = session.ensure_event(event_id)
        if err:
            return to_json(err)

        state = session.controller.GetPipelineState()
        result = _serialize_pipeline_state(state)
        result["event_id"] = session.current_event
        return to_json(result)

    @mcp.tool()
    def get_shader_bindings(stage: str, event_id: Optional[int] = None) -> str:
        """Get resource bindings for a specific shader stage at the current event.

        Shows constant buffers, shader resource views (SRVs), UAVs, and samplers.

        Args:
            stage: Shader stage name (vertex, hull, domain, geometry, pixel, compute).
            event_id: Optional event ID to navigate to first.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        err = session.ensure_event(event_id)
        if err:
            return to_json(err)

        stage_enum = SHADER_STAGE_MAP.get(stage.lower())
        if stage_enum is None:
            return to_json(make_error(f"Unknown shader stage: {stage}. Valid: {list(SHADER_STAGE_MAP.keys())}", "API_ERROR"))

        state = session.controller.GetPipelineState()
        refl = state.GetShaderReflection(stage_enum)
        if refl is None:
            return to_json(make_error(f"No shader bound at stage '{stage}'", "API_ERROR"))

        bindings: dict = {"stage": stage, "event_id": session.current_event}

        # Constant buffers
        cbs = []
        for i, cb_refl in enumerate(refl.constantBlocks):
            try:
                cb_bind = state.GetConstantBlock(stage_enum, i, 0)
                cbs.append({
                    "index": i,
                    "name": cb_refl.name,
                    "byte_size": cb_refl.byteSize,
                    "resource_id": str(cb_bind.descriptor.resource),
                })
            except Exception:
                cbs.append({"index": i, "name": cb_refl.name, "error": "failed to read binding"})
        bindings["constant_buffers"] = cbs

        # Read-only resources (SRVs)
        ros = []
        for i, ro_refl in enumerate(refl.readOnlyResources):
            try:
                ro_bind = state.GetReadOnlyResources(stage_enum, i, False)
                entries = []
                for b in ro_bind:
                    entries.append({
                        "resource_id": str(b.descriptor.resource),
                    })
                ros.append({
                    "index": i,
                    "name": ro_refl.name,
                    "type": str(ro_refl.textureType),
                    "bindings": entries,
                })
            except Exception:
                ros.append({"index": i, "name": ro_refl.name, "error": "failed to read binding"})
        bindings["read_only_resources"] = ros

        # Read-write resources (UAVs)
        rws = []
        for i, rw_refl in enumerate(refl.readWriteResources):
            try:
                rw_bind = state.GetReadWriteResources(stage_enum, i, False)
                entries = []
                for b in rw_bind:
                    entries.append({
                        "resource_id": str(b.descriptor.resource),
                    })
                rws.append({
                    "index": i,
                    "name": rw_refl.name,
                    "type": str(rw_refl.textureType),
                    "bindings": entries,
                })
            except Exception:
                rws.append({"index": i, "name": rw_refl.name, "error": "failed to read binding"})
        bindings["read_write_resources"] = rws

        # Samplers
        samplers = []
        for i, s_refl in enumerate(refl.samplers):
            try:
                s_bind = state.GetSamplers(stage_enum, i, False)
                entries = []
                for b in s_bind:
                    entries.append({
                        "resource_id": str(b.descriptor.resource),
                    })
                samplers.append({
                    "index": i,
                    "name": s_refl.name,
                    "bindings": entries,
                })
            except Exception:
                samplers.append({"index": i, "name": s_refl.name, "error": "failed to read binding"})
        bindings["samplers"] = samplers

        return to_json(bindings)

    @mcp.tool()
    def get_vertex_inputs(event_id: Optional[int] = None) -> str:
        """Get vertex input layout and buffer bindings at the current event.

        Shows vertex attributes (name, format, offset), vertex buffer bindings, and index buffer.

        Args:
            event_id: Optional event ID to navigate to first.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)
        err = session.ensure_event(event_id)
        if err:
            return to_json(err)

        state = session.controller.GetPipelineState()

        # Index buffer
        ib = state.GetIBuffer()
        ib_info = {
            "resource_id": str(ib.resourceId),
            "byte_offset": ib.byteOffset,
            "byte_stride": ib.byteStride,
        }

        # Vertex buffers
        vbs = state.GetVBuffers()
        vb_list = []
        for i, vb in enumerate(vbs):
            if int(vb.resourceId) == 0:
                continue
            vb_list.append({
                "slot": i,
                "resource_id": str(vb.resourceId),
                "byte_offset": vb.byteOffset,
                "byte_stride": vb.byteStride,
            })

        # Vertex attributes
        attrs = state.GetVertexInputs()
        attr_list = []
        for a in attrs:
            attr_list.append({
                "name": a.name,
                "vertex_buffer": a.vertexBuffer,
                "byte_offset": a.byteOffset,
                "per_instance": a.perInstance,
                "instance_rate": a.instanceRate,
                "format": str(a.format.Name()),
            })

        result = {
            "event_id": session.current_event,
            "index_buffer": ib_info,
            "vertex_buffers": vb_list,
            "vertex_attributes": attr_list,
        }
        return to_json(result)

    @mcp.tool()
    def get_draw_call_state(event_id: int) -> str:
        """Get complete draw call state in a single call.

        Returns action info, blend, depth, stencil, rasterizer, bound textures,
        render targets, and shader summaries — everything needed to understand a draw call.

        Args:
            event_id: The event ID of the draw call to inspect.
        """
        session = get_session()
        err = session.require_open()
        if err:
            return to_json(err)

        result = _get_draw_state_dict(session, event_id)
        if "error" in result:
            return to_json(result)
        return to_json(result)


def _get_draw_state_dict(session, event_id: int) -> dict:
    """Internal helper: build a complete draw call state dict.

    Shared by get_draw_call_state and diff_draw_calls.
    """
    err = session.set_event(event_id)
    if err:
        return err

    action = session.get_action(event_id)
    if action is None:
        return make_error(f"Event ID {event_id} not found", "INVALID_EVENT_ID")

    sf = session.structured_file
    state = session.controller.GetPipelineState()

    result: dict = {
        "event_id": event_id,
        "action_name": action.GetName(sf),
        "vertex_count": action.numIndices,
        "instance_count": action.numInstances,
    }

    # Topology
    try:
        topo = state.GetPrimitiveTopology()
        result["topology"] = enum_str(topo, TOPOLOGY_MAP, "Topology.")
    except Exception:
        result["topology"] = "Unknown"

    # Blend state (first enabled blend target)
    try:
        cb = state.GetColorBlend()
        if cb.blends:
            b = cb.blends[0]
            color_eq = _serialize_blend_eq(b.colorBlend)
            alpha_eq = _serialize_blend_eq(b.alphaBlend)
            blend_info: dict = {
                "enabled": b.enabled,
                "color_src": color_eq["source"],
                "color_dst": color_eq["destination"],
                "color_op": color_eq["operation"],
                "alpha_src": alpha_eq["source"],
                "alpha_dst": alpha_eq["destination"],
                "alpha_op": alpha_eq["operation"],
            }
            if b.enabled:
                blend_info["formula"] = blend_formula(
                    color_eq["source"], color_eq["destination"], color_eq["operation"],
                    alpha_eq["source"], alpha_eq["destination"], alpha_eq["operation"],
                )
            result["blend"] = blend_info
    except Exception:
        pass

    # Depth state
    try:
        ds = state.GetDepthState()
        result["depth"] = {
            "test": ds.depthEnable,
            "write": ds.depthWrites,
            "func": enum_str(ds.depthFunction, COMPARE_FUNC_MAP, "CompareFunc."),
        }
    except Exception:
        pass

    # Stencil state
    try:
        ss = state.GetStencilState()
        result["stencil"] = {"enabled": ss.stencilEnable}
    except Exception:
        pass

    # Rasterizer
    try:
        raster = state.GetRasterizer()
        result["rasterizer"] = {
            "cull": enum_str(raster.cullMode, CULL_MODE_MAP, "CullMode."),
            "fill": enum_str(raster.fillMode, FILL_MODE_MAP, "FillMode."),
            "front_ccw": raster.frontCCW,
        }
    except Exception:
        pass

    # Textures bound to pixel shader
    textures = []
    try:
        ps_refl = state.GetShaderReflection(rd.ShaderStage.Pixel)
        if ps_refl is not None:
            for i, ro_refl in enumerate(ps_refl.readOnlyResources):
                try:
                    ro_bind = state.GetReadOnlyResources(rd.ShaderStage.Pixel, i, False)
                    for b in ro_bind:
                        rid_str = str(b.descriptor.resource)
                        tex_desc = session.get_texture_desc(rid_str)
                        tex_entry: dict = {
                            "slot": i,
                            "name": ro_refl.name,
                            "resource_id": rid_str,
                        }
                        if tex_desc is not None:
                            tex_entry["size"] = f"{tex_desc.width}x{tex_desc.height}"
                            tex_entry["format"] = str(tex_desc.format.Name())
                        textures.append(tex_entry)
                except Exception:
                    pass
    except Exception:
        pass
    result["textures"] = textures

    # Render targets
    render_targets = []
    try:
        outputs = state.GetOutputTargets()
        for o in outputs:
            if int(o.resource) == 0:
                continue
            rid_str = str(o.resource)
            rt_entry: dict = {"resource_id": rid_str}
            tex_desc = session.get_texture_desc(rid_str)
            if tex_desc is not None:
                rt_entry["size"] = f"{tex_desc.width}x{tex_desc.height}"
                rt_entry["format"] = str(tex_desc.format.Name())
            render_targets.append(rt_entry)
    except Exception:
        pass
    result["render_targets"] = render_targets

    # Depth target
    try:
        dt = state.GetDepthTarget()
        if int(dt.resource) != 0:
            rid_str = str(dt.resource)
            dt_entry: dict = {"resource_id": rid_str}
            tex_desc = session.get_texture_desc(rid_str)
            if tex_desc is not None:
                dt_entry["size"] = f"{tex_desc.width}x{tex_desc.height}"
                dt_entry["format"] = str(tex_desc.format.Name())
            result["depth_target"] = dt_entry
    except Exception:
        pass

    # Shader summaries
    shaders = {}
    for sname, sstage in SHADER_STAGE_MAP.items():
        if sstage == rd.ShaderStage.Compute:
            continue
        refl = state.GetShaderReflection(sstage)
        if refl is None:
            continue
        info: dict = {
            "resource_id": str(refl.resourceId),
            "entry_point": state.GetShaderEntryPoint(sstage),
        }
        if sname == "vertex":
            info["inputs"] = [s.semanticIdxName or s.varName for s in refl.inputSignature]
        if sname == "pixel":
            info["texture_count"] = len(refl.readOnlyResources)
        shaders[sname] = info
    result["shaders"] = shaders

    return result
