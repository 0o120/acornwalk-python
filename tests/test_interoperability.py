import copy
from types import SimpleNamespace
import unittest
from collections import UserDict
from collections.abc import Mapping

import acornwalk as walk


def literal(value=1, **extra):
    return {"type": "Literal", "value": value, **extra}


class InteroperabilityTests(unittest.TestCase):
    def test_mapping_identity_and_range_searches(self):
        child = literal("\U00010400", range=[0, 4])
        expr = {"type": "ExpressionStatement", "expression": child, "range": [0, 5]}
        root = {"type": "Program", "body": [expr], "range": [0, 5]}
        original = copy.deepcopy(root)
        seen = []
        walk.full(root, lambda node, state, kind: seen.append(node))
        self.assertIs(seen[0], child)
        self.assertEqual(root, original)
        self.assertIs(walk.findNodeAt(root, 0, 4, "Literal").node, child)
        self.assertIs(walk.findNodeAround(root, 3, "Literal").node, child)
        self.assertIs(walk.findNodeAfter(root, 0, "Literal").node, child)
        self.assertIs(walk.findNodeBefore(root, 4, "Literal").node, child)

    def test_field_aliases_and_missing_optionals(self):
        node = SimpleNamespace(type="ForOfStatement", await_=True)
        self.assertTrue(walk.getField(node, "await"))
        self.assertTrue(walk.getField(SimpleNamespace(isAsync=True), "async"))
        self.assertTrue(walk.getField(SimpleNamespace(allowAwait=True), "await"))
        self.assertFalse(walk.getField({"async": False, "isAsync": True}, "async"))
        self.assertTrue(walk.getField({"async": True}, "async"))
        self.assertIsNone(walk.getField(node, "missing"))
        expression = {"type": "ArrowFunctionExpression", "params": [], "body": literal(), "expression": True, "async": True}
        walk.full(expression, lambda *args: None)
        anonymous = {"type": "ExportDefaultDeclaration", "declaration": {
            "type": "FunctionDeclaration", "params": [], "body": {"type": "BlockStatement", "body": []}}}
        walk.full(anonymous, lambda *args: None)

    def test_defaults_for_permissive_native_nodes_preserve_declared_nulls(self):
        class Native:
            def __init__(self):
                self.type = "Identifier"
                self.optional = None
            def __getattr__(self, name):
                return None
        native = Native()
        self.assertEqual(walk.getField(native, "missing", ()), ())
        self.assertIsNone(walk.getField(native, "optional", False))

    def test_unhashable_string_field_names_retain_native_and_custom_get_semantics(self):
        class FieldName(str):
            __hash__ = None
        class Native:
            def __getattribute__(self, name):
                if name == "value":
                    return 1
                return object.__getattribute__(self, name)
        class Custom(UserDict):
            def get(self, name, default=None):
                return 1 if name == "value" else default
        name = FieldName("value")
        self.assertEqual(walk.getField(Native(), name), 1)
        self.assertEqual(walk.getField(Custom(), name), 1)

    def test_fast_access_preserves_custom_properties_and_mapping_get(self):
        class Namespace(SimpleNamespace):
            @property
            def type(self):
                return "Literal"
        node = Namespace()
        node.__dict__["type"] = "Identifier"
        self.assertEqual(walk.getField(node, "type"), "Literal")
        class Custom(dict):
            def get(self, name, default=None):
                return "Literal" if name == "type" else super().get(name, default)
        custom = Custom(type="Identifier", value=1)
        self.assertEqual(walk.getField(custom, "type"), "Literal")
        self.assertEqual(walk.getField(UserDict(type="Identifier"), "type"), "Identifier")
        seen = []
        walk.full(custom, lambda node, state, category: seen.append((node, category)))
        self.assertIs(seen[0][0], custom)
        self.assertEqual(seen[0][1], "Literal")

    def test_cached_mapping_detection_tracks_virtual_registration(self):
        class Virtual:
            type = "AttributeType"
            def get(self, name, default=None):
                return "MappingType" if name == "type" else default
        node = Virtual()
        self.assertEqual(walk.getField(node, "type"), "AttributeType")
        Mapping.register(Virtual)
        self.assertEqual(walk.getField(node, "type"), "MappingType")

    def test_callback_mapping_registration_and_mapping_get_changes_are_observed(self):
        expected_alternate = {"type": "EmptyStatement"}
        class Native:
            def __init__(self):
                self.type = "IfStatement"
                self.test = {"type": "Literal", "value": 1}
                self.consequent = {"type": "EmptyStatement"}
                self.alternate = None
            def get(self, name, default=None):
                if name == "alternate":
                    return expected_alternate
                return getattr(self, name, default)
        node = Native()
        seen = []
        def register(child, state, kind):
            seen.append(child)
            if child is node.test:
                Mapping.register(Native)
        walk.full(node, register)
        self.assertTrue(any(child is expected_alternate for child in seen))

        mapping = UserDict(type="IfStatement", test=literal(),
            consequent={"type": "EmptyStatement"}, alternate=None)
        def replace_get(child, state, kind):
            if child is mapping["test"]:
                mapping.get = lambda name, default=None: (expected_alternate if name == "alternate"
                    else mapping.data.get(name, default))
        observed = []
        walk.full(mapping, lambda child, state, kind: (replace_get(child, state, kind), observed.append(child)))
        self.assertTrue(any(child is expected_alternate for child in observed))

    def test_class_proxy_mapping_and_native_descriptors(self):
        class Proxy:
            @property
            def __class__(self):
                return UserDict
            def get(self, name, default=None):
                return "Literal" if name == "type" else default
        self.assertEqual(walk.getField(Proxy(), "type"), "Literal")
        class Native:
            @property
            def type(self):
                return "Literal"
            def __init__(self):
                self.__dict__["type"] = "Identifier"
        self.assertEqual(walk.getField(Native(), "type"), "Literal")

    def test_position_validation(self):
        self.assertEqual(walk.nodeRange(SimpleNamespace(type="Identifier", range=[2, 4])), (2, 4))
        self.assertEqual(walk.nodeRange({"type": "Identifier", "start": 2, "end": 4}), (2, 4))
        for fields in ({}, {"range": [1]}, {"range": [4, 2]}, {"range": [-1, 2]},
                {"range": [0, True]}, {"range": "ab"}, {"start": 1, "end": None}):
            with self.assertRaisesRegex(ValueError, "Identifier"):
                walk.findNodeAround({"type": "Identifier", **fields}, 1)
        for pos in (-1, True, 1.5):
            with self.assertRaises((ValueError, TypeError)):
                walk.findNodeAround(literal(range=[0, 1]), pos)
        with self.assertRaises(ValueError):
            walk.findNodeAt(literal(range=[0, 1]), 4, 2)

    def test_module_attributes_and_import_options(self):
        value = literal("json")
        attribute = {"type": "ImportAttribute", "key": {"type": "Identifier", "name": "type"}, "value": value}
        for kind in ("ImportDeclaration", "ExportNamedDeclaration", "ExportAllDeclaration"):
            node = {"type": kind, "specifiers": [], "source": literal("./x.json"), "attributes": [attribute]}
            seen = []
            walk.full(node, lambda node, state, category: seen.append(node))
            self.assertTrue(any(node is attribute for node in seen))
            self.assertTrue(any(node is value for node in seen))
            self.assertFalse(any(node is attribute["key"] for node in seen))
        options = {"type": "ObjectExpression", "properties": [{"type": "Property", "key": {"type": "Identifier", "name": "with"},
            "value": {"type": "Identifier", "name": "options"}, "computed": False}]}
        node = {"type": "ImportExpression", "source": literal("./x"), "options": options}
        seen = []
        walk.full(node, lambda node, state, category: seen.append(node))
        self.assertTrue(any(node is options for node in seen))

    def test_modern_classes_chain_and_legacy_fields(self):
        for kind in ("PropertyDefinition", "FieldDefinition"):
            value = {"type": "ChainExpression", "expression": {"type": "CallExpression",
                "callee": {"type": "MemberExpression", "object": {"type": "ThisExpression"},
                    "property": {"type": "PrivateIdentifier", "name": "p"}, "computed": False, "optional": True},
                "arguments": [literal()], "optional": True}}
            root = {"type": "ClassDeclaration", "id": None, "body": {"type": "ClassBody", "body": [
                {"type": kind, "key": literal("computed"), "computed": True, "value": value},
                {"type": "StaticBlock", "body": [{"type": "EmptyStatement"}]}]}}
            seen = []
            walk.full(root, lambda node, state, category: seen.append(node))
            self.assertTrue(any(node is value for node in seen))

    def test_jsx_fragment_and_expression_children(self):
        expression = {"type": "Identifier", "name": "value"}
        root = {"type": "JSXFragment", "openingFragment": {"type": "JSXOpeningFragment"},
            "closingFragment": {"type": "JSXClosingFragment"}, "children": [{"type": "JSXElement",
                "openingElement": {"type": "JSXOpeningElement", "name": {"type": "JSXMemberExpression",
                    "object": {"type": "JSXIdentifier", "name": "UI"}, "property": {"type": "JSXIdentifier", "name": "Box"}},
                    "attributes": [{"type": "JSXSpreadAttribute", "argument": expression},
                        {"type": "JSXAttribute", "name": {"type": "JSXNamespacedName", "namespace": {"type": "JSXIdentifier", "name": "ns"},
                            "name": {"type": "JSXIdentifier", "name": "key"}}, "value": literal("yes")} ]},
                "closingElement": None, "children": [{"type": "JSXText", "value": "text"},
                    {"type": "JSXExpressionContainer", "expression": {"type": "JSXEmptyExpression"}},
                    {"type": "JSXSpreadChild", "expression": expression}]}]}
        original = copy.deepcopy(root)
        seen = []
        walk.full(root, lambda node, state, category: seen.append(node))
        self.assertEqual(sum(node is expression for node in seen), 2)
        self.assertEqual(root, original)
        self.assertTrue(any(node["type"] == "JSXNamespacedName" for node in seen))


if __name__ == "__main__":
    unittest.main()
