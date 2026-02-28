"""Unit tests for renderdoc_mcp.util — serialization helpers and flag conversion."""

import json
import sys
import unittest
from unittest.mock import MagicMock


# Mock the renderdoc module before any imports touch it
mock_rd = MagicMock()


class MockActionFlags:
    NoFlags = 0
    Clear = 1
    Drawcall = 2
    Dispatch = 4
    CmdList = 8
    SetMarker = 16
    PushMarker = 32
    PopMarker = 64
    Present = 128
    MultiAction = 256
    Copy = 512
    Resolve = 1024
    GenMips = 2048
    PassBoundary = 4096
    Indexed = 8192
    Instanced = 16384
    Auto = 32768
    Indirect = 65536
    MeshDispatch = 131072


mock_rd.ActionFlags = MockActionFlags
sys.modules["renderdoc"] = mock_rd
sys.modules["_renderdoc"] = mock_rd

# Now safe to import
from renderdoc_mcp.util import (  # noqa: E402
    flags_to_list,
    make_error,
    to_json,
    serialize_action,
    serialize_shader_variable,
    _ACTION_FLAG_NAMES,
)
import renderdoc_mcp.util as util  # noqa: E402

# Ensure util.rd points to our mock
util.rd = mock_rd


class TestFlagsToList(unittest.TestCase):
    def setUp(self):
        util._ACTION_FLAG_NAMES = None

    def test_single_flag(self):
        result = flags_to_list(MockActionFlags.Drawcall)
        self.assertIn("Drawcall", result)
        self.assertEqual(len(result), 1)

    def test_combined_flags(self):
        result = flags_to_list(MockActionFlags.Drawcall | MockActionFlags.Indexed)
        self.assertIn("Drawcall", result)
        self.assertIn("Indexed", result)

    def test_no_flags(self):
        result = flags_to_list(0)
        self.assertEqual(result, [])

    def test_all_known_flags(self):
        # Test that all single-bit flags are detected
        combined = MockActionFlags.Clear | MockActionFlags.Dispatch | MockActionFlags.Present
        result = flags_to_list(combined)
        self.assertIn("Clear", result)
        self.assertIn("Dispatch", result)
        self.assertIn("Present", result)
        self.assertEqual(len(result), 3)


class TestMakeError(unittest.TestCase):
    def test_basic_error(self):
        err = make_error("something went wrong", "TEST_CODE")
        self.assertEqual(err["error"], "something went wrong")
        self.assertEqual(err["code"], "TEST_CODE")

    def test_default_code(self):
        err = make_error("oops")
        self.assertEqual(err["code"], "API_ERROR")


class TestToJson(unittest.TestCase):
    def test_compact_output(self):
        result = to_json({"a": 1, "b": [2, 3]})
        parsed = json.loads(result)
        self.assertEqual(parsed, {"a": 1, "b": [2, 3]})
        self.assertNotIn(": ", result)
        self.assertNotIn(", ", result)

    def test_roundtrip(self):
        data = {"nested": {"key": "value"}, "list": [1, 2, 3]}
        result = json.loads(to_json(data))
        self.assertEqual(result, data)


class TestSerializeAction(unittest.TestCase):
    def _make_action(self, event_id=1, name="DrawIndexed", flags=2,
                     num_indices=100, num_instances=1, children=None):
        action = MagicMock()
        action.eventId = event_id
        action.GetName.return_value = name
        action.flags = flags
        action.numIndices = num_indices
        action.numInstances = num_instances
        action.children = children or []
        action.outputs = []
        action.depthOutput = MagicMock()
        action.depthOutput.__int__ = lambda self: 0
        return action

    def setUp(self):
        util._ACTION_FLAG_NAMES = None

    def test_basic_serialization(self):
        action = self._make_action()
        sf = MagicMock()
        result = serialize_action(action, sf)
        self.assertEqual(result["event_id"], 1)
        self.assertEqual(result["num_indices"], 100)
        self.assertIn("flags", result)
        self.assertIn("Drawcall", result["flags"])

    def test_depth_limited(self):
        child = self._make_action(event_id=2, name="child")
        parent = self._make_action(event_id=1, children=[child])
        sf = MagicMock()
        result = serialize_action(parent, sf, max_depth=0)
        self.assertNotIn("children", result)
        self.assertEqual(result["children_count"], 1)

    def test_children_included_within_depth(self):
        child = self._make_action(event_id=2, name="child")
        parent = self._make_action(event_id=1, children=[child])
        sf = MagicMock()
        result = serialize_action(parent, sf, max_depth=2)
        self.assertIn("children", result)
        self.assertEqual(len(result["children"]), 1)
        self.assertEqual(result["children"][0]["event_id"], 2)


class TestSerializeShaderVariable(unittest.TestCase):
    def _make_var(self, name="testVar", rows=1, columns=4, values=None, members=None):
        var = MagicMock()
        var.name = name
        var.rows = rows
        var.columns = columns
        var.members = members or []
        if values is None:
            values = [1.0, 2.0, 3.0, 4.0]
        var.value.f32v = values
        return var

    def test_leaf_variable(self):
        var = self._make_var()
        result = serialize_shader_variable(var)
        self.assertEqual(result["name"], "testVar")
        self.assertEqual(result["value"], [1.0, 2.0, 3.0, 4.0])
        self.assertEqual(result["rows"], 1)
        self.assertEqual(result["columns"], 4)

    def test_multi_row_variable(self):
        # 4x4 matrix
        values = list(range(16))
        var = self._make_var(name="matrix", rows=4, columns=4, values=[float(v) for v in values])
        result = serialize_shader_variable(var)
        self.assertEqual(result["rows"], 4)
        self.assertEqual(len(result["value"]), 4)  # 4 rows

    def test_nested_variable(self):
        child = self._make_var(name="member", columns=1, values=[42.0])
        parent = self._make_var(name="struct", members=[child])
        result = serialize_shader_variable(parent)
        self.assertEqual(result["name"], "struct")
        self.assertIn("members", result)
        self.assertEqual(len(result["members"]), 1)
        self.assertEqual(result["members"][0]["name"], "member")

    def test_depth_limit(self):
        child = self._make_var(name="deep_child", members=[self._make_var(name="deeper")])
        parent = self._make_var(name="root", members=[child])
        result = serialize_shader_variable(parent, max_depth=1)
        self.assertIn("members", result)
        # At depth 1, child's members should not be expanded
        self.assertNotIn("members", result["members"][0])


if __name__ == "__main__":
    unittest.main()
