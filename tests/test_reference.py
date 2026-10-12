from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import unittest

import acornwalk as walk
from fixtures import fixtures

REFERENCE = Path(__file__).parent / "reference"


class ReferenceTests(unittest.TestCase):
    def test_concrete_handler_fixture_inventory(self):
        categories = {"Statement", "Expression", "Pattern", "VariablePattern", "MemberPattern", "Function", "Class", "ForInit"}
        supported = {name for name in vars(walk.Base) if not name.startswith("_") and callable(getattr(walk.Base, name))}
        supported -= categories | {"FieldDefinition"}
        supported = {name for name in supported if not name.startswith("JSX")}
        self.assertEqual(supported, {node["type"] for node in fixtures()})

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed only for upstream differential tests")
    def test_pinned_upstream_full_and_ancestor_order(self):
        self.assertEqual(sha256((REFERENCE / "acorn-walk-8.15.0.mjs").read_bytes()).hexdigest(),
            "3597ee95af816bc9785220b9277c79a8e971c876a56adc98cbb21ccfa4427c72")
        inputs = fixtures()
        reference = subprocess.run(["node", str(REFERENCE / "compare.mjs")], input=json.dumps(inputs),
            capture_output=True, text=True, check=True)
        expected = json.loads(reference.stdout)
        for root, result in zip(inputs, expected, strict=True):
            full, ancestors = [], []
            walk.full(root, lambda node, state, category: full.append([node["testId"], category]))
            walk.fullAncestor(root, lambda node, state, stack, category: ancestors.append(
                [node["testId"], category, [parent["testId"] for parent in stack]]))
            self.assertEqual({"full": full, "ancestors": ancestors}, result, root["type"])


if __name__ == "__main__":
    unittest.main()
