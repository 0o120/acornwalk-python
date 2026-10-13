import json
from pathlib import Path
import random
import shutil
import subprocess
from types import SimpleNamespace
import unittest

import acornwalk as walk
from fixtures import fixtures


def native(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{key: native(child) for key, child in value.items()})
    if isinstance(value, list):
        return [native(child) for child in value]
    return value


def expression_trees():
    rng = random.Random(20261012)
    counter = 0
    def build(depth, start):
        nonlocal counter
        kind = "Identifier" if depth == 0 else rng.choice(("Identifier", "BinaryExpression", "UnaryExpression"))
        node = {"type": kind, "start": start, "testId": counter}
        counter += 1
        if kind == "Identifier":
            node["name"] = "\U00010400" if rng.randrange(3) == 0 else "x"
            node["end"] = start + (2 if node["name"] != "x" else 1)
        elif kind == "BinaryExpression":
            left = build(depth - 1, start)
            right = build(depth - 1, left["end"] + 1)
            node.update(left=left, right=right, operator="+", end=right["end"])
        else:
            argument = build(depth - 1, start + 1)
            node.update(argument=argument, operator="!", prefix=True, end=argument["end"])
        return node
    return [build(5, 0) for _ in range(50)]


class PropertyTests(unittest.TestCase):
    def test_mapping_native_callback_order_and_identity(self):
        for mapping in fixtures():
            obj = native(mapping)
            mapping_result, native_result = [], []
            walk.full(mapping, lambda node, state, kind: mapping_result.append([node["testId"], kind]))
            walk.full(obj, lambda node, state, kind: native_result.append([node.testId, kind]))
            self.assertEqual(mapping_result, native_result)
            result = []
            walk.fullAncestor(obj, lambda node, state, stack, kind: result.append((node, stack[-1])))
            self.assertTrue(all(node is ancestor for node, ancestor in result))

    @unittest.skipUnless(shutil.which("node"), "Node.js needed for differential search properties")
    def test_seeded_search_properties_against_pinned_upstream(self):
        roots = expression_trees()
        reference = subprocess.run(["node", str(Path(__file__).parent / "reference/search.mjs")],
            input=json.dumps(roots), capture_output=True, text=True, check=True)
        expected = json.loads(reference.stdout)
        for root, reference_queries in zip(roots, expected, strict=True):
            actual = []
            match = lambda result: None if result is None else result.node["testId"]
            for pos in range(root["end"] + 2):
                for test in (None, "Identifier", "Expression"):
                    actual.append([match(walk.findNodeAround(root, pos, test)), match(walk.findNodeAfter(root, pos, test)),
                        match(walk.findNodeBefore(root, pos, test)), match(walk.findNodeAt(root, pos, None, test)),
                        match(walk.findNodeAt(root, None, pos, test))])
            self.assertEqual(actual, reference_queries)


if __name__ == "__main__":
    unittest.main()
