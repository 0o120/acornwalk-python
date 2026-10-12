import unittest
import copy
import pickle
import weakref

from acornwalk import Found


class ResultTests(unittest.TestCase):
    def test_fields_keep_original_identities(self):
        node, state = {}, []
        result = Found(node, state)
        self.assertIs(result.node, node)
        self.assertIs(result.state, state)

    def test_positional_pattern_matching_and_field_annotations(self):
        node, state = {}, []
        match Found(node, state):
            case Found(matched_node, matched_state):
                self.assertIs(matched_node, node)
                self.assertIs(matched_state, state)
            case _:
                self.fail("Found did not expose its positional fields")
        self.assertEqual(Found.__match_args__, ("node", "state"))
        self.assertEqual(Found.__annotations__, {"node": object, "state": object})

    def test_immutable_fields_and_exact_instance(self):
        result = Found("node", "state")
        for name in ("node", "state", "extra"):
            with self.assertRaises(AttributeError):
                setattr(result, name, None)
            with self.assertRaises(AttributeError):
                delattr(result, name)

    def test_repr_equality_and_hash_follow_existing_result_behavior(self):
        first, second = Found("node", 1), Found("node", 1)
        self.assertEqual(repr(first), "Found(node='node', state=1)")
        self.assertEqual(first, second)
        self.assertNotEqual(first, Found("other", 1))
        self.assertNotEqual(first, ("node", 1))
        self.assertEqual(hash(first), hash(("node", 1)))
        with self.assertRaises(TypeError):
            hash(Found({}, None))

    def test_subclasses_remain_distinct_and_can_add_non_field_attributes(self):
        class Extended(Found):
            pass
        result = Extended("node", "state")
        result.extra = 1
        self.assertEqual(result.extra, 1)
        self.assertNotEqual(result, Found("node", "state"))
        for name in ("node", "state"):
            with self.assertRaises(AttributeError):
                setattr(result, name, None)
            with self.assertRaises(AttributeError):
                delattr(result, name)

    def test_recursive_repr_is_bounded(self):
        node = []
        result = Found(node, None)
        node.append(result)
        self.assertEqual(repr(result), "Found(node=[...], state=None)")

    def test_standard_object_copy_pickle_and_weak_reference(self):
        node, state = {}, []
        result = Found(node, state)
        shallow = copy.copy(result)
        self.assertIs(shallow.node, node)
        self.assertIs(shallow.state, state)
        restored = pickle.loads(pickle.dumps(result))
        self.assertEqual(restored, result)
        self.assertIs(weakref.ref(result)(), result)

    def test_deepcopy_preserves_cyclic_state_and_node_identity(self):
        state = []
        result = Found({"type": "EmptyStatement"}, state)
        state.append(result)
        cloned = copy.deepcopy(result)
        self.assertIs(cloned.state[0], cloned)
        self.assertIsNot(cloned.node, result.node)
        node = {"found": None}
        original = Found(node, None)
        node["found"] = original
        cloned_node = copy.deepcopy(original)
        self.assertIs(cloned_node.node["found"], cloned_node)


if __name__ == "__main__":
    unittest.main()
