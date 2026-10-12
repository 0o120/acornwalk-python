import copy
from types import SimpleNamespace
import unittest

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
