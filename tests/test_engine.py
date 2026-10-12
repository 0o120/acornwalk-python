"""Regression coverage for the audited public walker operations."""
import unittest
from types import SimpleNamespace as Node

import acornwalk as walk
from acornwalk import walk as engine


def tree():
    left = Node(type="Literal", value=1, start=0, end=1)
    right = Node(type="Literal", value=2, start=2, end=3)
    expression = Node(type="BinaryExpression", operator="+", left=left, right=right, start=0, end=3)
    statement = Node(type="ExpressionStatement", expression=expression, start=0, end=4)
    return Node(type="Program", body=[statement], start=0, end=4), expression, left, right


class EngineTests(unittest.TestCase):
    def test_public_exports(self):
        for name in ("recursive", "findNodeBefore", "simple", "ancestor", "full", "fullAncestor", "make"):
            self.assertTrue(callable(getattr(walk, name)))

    def test_empty_statement(self):
        seen = []
        walk.simple(Node(type="EmptyStatement"), {"EmptyStatement": lambda node, state: seen.append(node)})
        self.assertEqual(len(seen), 1)

    def test_recursive_defaults_and_overrides(self):
        root, _, left, right = tree()
        seen = []
        engine.recursive(root, seen, {"Literal": lambda node, state, recurse: state.append(node)})
        self.assertEqual(seen, [left, right])
        engine.recursive(root, None, {})

    def test_searches(self):
        root, expr, left, right = tree()
        for predicate in ("Literal", lambda kind, node: kind == "Literal"):
            self.assertIs(walk.findNodeAt(root, 0, 1, predicate).node, left)
            self.assertIs(walk.findNodeAround(root, 2, predicate).node, right)
            self.assertIs(walk.findNodeAfter(root, 1, predicate).node, right)
            self.assertIs(engine.findNodeBefore(root, 2, predicate).node, left)
        self.assertIs(walk.findNodeAt(root, 0, 1, None).node, left)
        self.assertIs(walk.findNodeAround(root, 1, "BinaryExpression").node, expr)
        self.assertIsNone(walk.findNodeAt(root, 10, 11, "Literal"))
        self.assertIsNone(walk.findNodeAround(root, 10, None))
        self.assertIsNone(walk.findNodeAfter(root, 10, None))
        self.assertIsNone(engine.findNodeBefore(root, 0, None))

    def test_search_order_and_state(self):
        root, expr, _, _ = tree()
        state = {}
        self.assertIs(walk.findNodeAround(root, 1, None, state=state).node, expr.left)
        self.assertIs(walk.findNodeAfter(root, 0, None, state=state).node, root)
        self.assertIs(engine.findNodeBefore(root, 4, None, state=state).node, root)
        self.assertIs(walk.findNodeAt(root, 0, 4, "Program", state=state).state, state)

    def test_callbacks_exceptions_propagate(self):
        def fail(*args):
            raise RuntimeError("user callback")
        with self.assertRaisesRegex(RuntimeError, "user callback"):
            walk.findNodeAround(tree()[0], 0, fail)

    def test_full_ancestor_default_and_falsey_states(self):
        root, _, left, right = tree()
        for state in (None, 0, False, "", {}, []):
            seen = []
            walk.fullAncestor(root, lambda node, st, ancestors, kind: seen.append((node, st, list(ancestors), kind)), state=state)
            self.assertEqual(len(seen), 5)
            self.assertIs(seen[0][0], left)
            self.assertIs(seen[1][0], right)
            for node, st, ancestors, kind in seen:
                self.assertIs(ancestors[-1], node)
                self.assertIs(st, state if state is not None else st)
                self.assertIsInstance(kind, str)

    def test_ancestor_preserves_falsey_states(self):
        root, _, _, _ = tree()
        for state in (0, False, "", {}, []):
            seen = []
            walk.ancestor(root, {"Literal": lambda node, st, ancestors: seen.append(st)}, state=state)
            self.assertTrue(all(st is state for st in seen))

    def test_full_preserves_equal_sibling_identity(self):
        first = Node(type="Literal", value=1)
        second = Node(type="Literal", value=1)
        root = Node(type="ArrayExpression", elements=[first, second])
        seen = []
        walk.full(root, lambda node, state, kind: seen.append(node))
        self.assertEqual(len(seen), 3)
        self.assertIs(seen[0], first)
        self.assertIs(seen[1], second)

    def test_make_overlays_do_not_mutate_base(self):
        first = walk.Base()
        handler = lambda node, state, recurse: None
        derived = walk.make({"Literal": handler}, first)
        self.assertIs(derived["Literal"], handler)
        self.assertIsNot(first["Literal"], handler)
        mapping = {"Literal": handler}
        self.assertIs(walk.make({}, mapping)["Literal"], handler)
        self.assertEqual(mapping, {"Literal": handler})

    def test_subclass_and_falsey_base(self):
        seen = []
        class Custom(walk.Base):
            def Literal(node, state, recurse):
                seen.append(node)
        walk.simple(tree()[2], {}, Custom())
        self.assertEqual(len(seen), 1)
        with self.assertRaisesRegex(ValueError, "Literal"):
            walk.simple(tree()[2], {}, {})

    def test_pattern_defaults_and_switch_case(self):
        identifier = Node(type="Identifier", name="x")
        literal = Node(type="Literal", value=7)
        pattern = Node(type="ObjectPattern", properties=[Node(type="Property", computed=False,
            key=identifier, value=Node(type="AssignmentPattern", left=identifier, right=literal))])
        seen = []
        walk.full(pattern, lambda node, st, kind: seen.append(node))
        self.assertTrue(any(node is literal for node in seen))
        self.assertTrue(any(node is identifier for node in seen))
        switch = Node(type="SwitchStatement", discriminant=literal,
            cases=[Node(type="SwitchCase", test=None, consequent=[Node(type="EmptyStatement")])])
        cases = []
        walk.simple(switch, {"SwitchCase": lambda node, st: cases.append(node)})
        self.assertEqual(len(cases), 1)

    def test_unknown_type_diagnostic(self):
        with self.assertRaisesRegex(ValueError, "UnknownThing"):
            walk.simple(Node(type="UnknownThing"), {})

    def test_default_dispatch_observes_class_descriptors_and_callback_changes(self):
        original = walk.Base.Literal
        seen = []
        class Handler:
            def __get__(self, instance, owner):
                return lambda node, state, recurse: seen.append(node)
        try:
            walk.Base.Literal = Handler()
            root, _, left, right = tree()
            walk.full(root, lambda *args: None)
            self.assertEqual(seen, [left, right])
            walk.Base.Literal = original
            def replace(node, state, kind):
                if node is left:
                    walk.Base.Literal = lambda node, state, recurse: seen.append(node)
            seen.clear()
            walk.full(root, replace)
            self.assertEqual(seen, [right])
        finally:
            walk.Base.Literal = original

    def test_full_category_delegation_preserves_custom_lookup_and_state(self):
        for operation in (walk.full, walk.fullAncestor):
            lookups, seen = [], []
            class Custom(walk.Base):
                def __getitem__(self, kind):
                    lookups.append(kind)
                    return super().__getitem__(kind)
            node = Node(type="Literal", value=1)
            state = []
            operation(node, lambda node, passed_state, *args: seen.append((node, passed_state)),
                Custom(), state, "Expression")
            self.assertEqual(lookups, ["Expression", "Literal"])
            self.assertEqual(len(seen), 1)
            self.assertIs(seen[0][0], node)
            self.assertIs(seen[0][1], state)


if __name__ == "__main__":
    unittest.main()
