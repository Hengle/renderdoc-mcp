"""Shader analysis tools: disassemble_shader, get_shader_reflection, get_cbuffer_contents."""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from renderdoc_mcp.session import get_session
from renderdoc_mcp.util import (
    rd,
    to_json,
    make_error,
    SHADER_STAGE_MAP,
    serialize_shader_variable,
    serialize_sig_element,
)


def register(mcp: FastMCP):
    @mcp.tool()
    def disassemble_shader(
        stage: str,
        target: Optional[str] = None,
        event_id: Optional[int] = None,
    ) -> str:
        """Disassemble the shader bound at the specified stage.

        Args:
            stage: Shader stage (vertex, hull, domain, geometry, pixel, compute).
            target: Disassembly target/format. If omitted, uses the first available.
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
            return to_json(make_error(f"Unknown shader stage: {stage}", "API_ERROR"))

        state = session.controller.GetPipelineState()
        refl = state.GetShaderReflection(stage_enum)
        if refl is None:
            return to_json(make_error(f"No shader bound at stage '{stage}'", "API_ERROR"))

        pipe = state.GetGraphicsPipelineObject()
        targets = session.controller.GetDisassemblyTargets(True)

        if not targets:
            return to_json(make_error("No disassembly targets available", "API_ERROR"))

        if target is None:
            target = targets[0]
        elif target not in targets:
            return to_json(make_error(
                f"Unknown disassembly target: {target}. Available: {targets}", "API_ERROR"
            ))

        disasm = session.controller.DisassembleShader(pipe, refl, target)

        return to_json({
            "stage": stage,
            "target": target,
            "available_targets": list(targets),
            "disassembly": disasm,
        })

    @mcp.tool()
    def get_shader_reflection(
        stage: str,
        event_id: Optional[int] = None,
    ) -> str:
        """Get reflection information for the shader at the specified stage.

        Returns input/output signatures, constant buffer layouts, and resource bindings.

        Args:
            stage: Shader stage (vertex, hull, domain, geometry, pixel, compute).
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
            return to_json(make_error(f"Unknown shader stage: {stage}", "API_ERROR"))

        state = session.controller.GetPipelineState()
        refl = state.GetShaderReflection(stage_enum)
        if refl is None:
            return to_json(make_error(f"No shader bound at stage '{stage}'", "API_ERROR"))

        result: dict = {
            "stage": stage,
            "resource_id": str(refl.resourceId),
            "entry_point": refl.entryPoint,
        }

        # Input signature
        result["input_signature"] = [serialize_sig_element(s) for s in refl.inputSignature]
        # Output signature
        result["output_signature"] = [serialize_sig_element(s) for s in refl.outputSignature]

        # Constant blocks
        cbs = []
        for cb in refl.constantBlocks:
            cbs.append({
                "name": cb.name,
                "byte_size": cb.byteSize,
                "bind_point": cb.fixedBindNumber,
                "variables_count": len(cb.variables),
            })
        result["constant_blocks"] = cbs

        # Read-only resources
        ros = []
        for ro in refl.readOnlyResources:
            ros.append({
                "name": ro.name,
                "type": str(ro.resType),
                "bind_point": ro.fixedBindNumber,
            })
        result["read_only_resources"] = ros

        # Read-write resources
        rws = []
        for rw in refl.readWriteResources:
            rws.append({
                "name": rw.name,
                "type": str(rw.resType),
                "bind_point": rw.fixedBindNumber,
            })
        result["read_write_resources"] = rws

        # Samplers
        samplers = []
        for s in refl.samplers:
            samplers.append({
                "name": s.name,
                "bind_point": s.fixedBindNumber,
            })
        result["samplers"] = samplers

        return to_json(result)

    @mcp.tool()
    def get_cbuffer_contents(
        stage: str,
        cbuffer_index: int,
        event_id: Optional[int] = None,
    ) -> str:
        """Get the actual values of a constant buffer at the specified shader stage.

        Returns a tree of variable names and their current values.

        Args:
            stage: Shader stage (vertex, hull, domain, geometry, pixel, compute).
            cbuffer_index: Index of the constant buffer (from get_shader_reflection).
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
            return to_json(make_error(f"Unknown shader stage: {stage}", "API_ERROR"))

        state = session.controller.GetPipelineState()
        refl = state.GetShaderReflection(stage_enum)
        if refl is None:
            return to_json(make_error(f"No shader bound at stage '{stage}'", "API_ERROR"))

        if cbuffer_index < 0 or cbuffer_index >= len(refl.constantBlocks):
            return to_json(make_error(
                f"cbuffer_index {cbuffer_index} out of range (0-{len(refl.constantBlocks)-1})",
                "API_ERROR",
            ))

        pipe = state.GetGraphicsPipelineObject()
        entry = state.GetShaderEntryPoint(stage_enum)
        cb_bind = state.GetConstantBlock(stage_enum, cbuffer_index, 0)

        cbuffer_vars = session.controller.GetCBufferVariableContents(
            pipe, refl.resourceId, stage_enum, entry,
            cbuffer_index, cb_bind.descriptor.resource, 0, 0,
        )

        variables = [serialize_shader_variable(v) for v in cbuffer_vars]

        return to_json({
            "stage": stage,
            "cbuffer_index": cbuffer_index,
            "cbuffer_name": refl.constantBlocks[cbuffer_index].name,
            "variables": variables,
        })
