"""Every public operation must retain extension children and node identity."""
import copy
import unittest
from types import SimpleNamespace

from fixtures import proposal_fixtures

import acornwalk as walk

try:
    import esprima
except ImportError:
    esprima = None


def proposal_tree():
    expression = {'type': 'Identifier', 'name': 'dec', 'range': [1, 4]}
    decorator = {'type': 'Decorator', 'expression': expression, 'range': [0, 4]}
    member_expression = {'type': 'Identifier', 'name': 'field', 'range': [16, 21]}
    member_decorator = {'type': 'Decorator', 'expression': member_expression, 'range': [15, 21]}
    key = {'type': 'Identifier', 'name': 'key', 'range': [32, 35]}
    value = {'type': 'Literal', 'value': '\U0001f600', 'range': [37, 41]}
    accessor = {'type': 'AccessorProperty', 'decorators': [member_decorator],
                'computed': True, 'key': key, 'value': value, 'range': [15, 42]}
    body = {'type': 'ClassBody', 'body': [accessor], 'range': [14, 44]}
    cls = {'type': 'ClassDeclaration', 'id': None, 'decorators': [decorator],
           'superClass': None, 'body': body, 'range': [0, 44]}
    root = {'type': 'Program', 'body': [cls], 'range': [0, 44],
            'comments': [{'type': 'Line', 'value': 'retained', 'range': [44, 54]}]}
    expected = [expression, decorator, member_expression, member_decorator,
                key, value, accessor, body, cls, root]
    return root, expected


def native(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{key: native(child) for key, child in value.items()})
    if isinstance(value, list):
        return [native(child) for child in value]
    return value


def collect(root, api, state):
    seen = []
    if api == 'full':
        walk.full(root, lambda node, st, kind: seen.append(node), state=state)
    elif api == 'fullAncestor':
        def visit(node, st, ancestors, kind):
            assert st is state
            assert ancestors[-1] is node
            seen.append(node)
        walk.fullAncestor(root, visit, state=state)
    else:
        kinds = set()
        walk.full(root, lambda node, st, kind: kinds.add(walk.getField(node, 'type')))
        if api == 'recursive':
            base = walk.Base()
            def callback(kind):
                def visit(node, st, c):
                    assert st is state
                    base[kind](node, st, c)
                    seen.append(node)
                return visit
            walk.recursive(root, state, {kind: callback(kind) for kind in kinds})
        else:
            def visit(node, st, *ancestors):
                assert st is state
                if ancestors:
                    assert ancestors[0][-1] is node
                seen.append(node)
            getattr(walk, api)(root, {kind: visit for kind in kinds}, state=state)
    return seen


class ProposalWalkerTests(unittest.TestCase):
    def test_ordinary_subtrees_still_prune_by_their_own_ranges(self):
        root, _ = proposal_tree()
        root['range'] = [0, 100]
        root['body'].insert(0, {'type': 'ExpressionStatement', 'range': [50, 60],
                               'expression': {'type': 'Literal', 'value': 'no range'}})
        self.assertEqual(walk.findNodeAt(root, 0, 4, 'Decorator').node['type'], 'Decorator')
        self.assertEqual(walk.findNodeAround(root, 1, 'Decorator').node['type'], 'Decorator')
        self.assertEqual(walk.findNodeBefore(root, 4, 'Decorator').node['type'], 'Decorator')
        self.assertIsNone(walk.findNodeAfter(root, 80, 'Decorator'))

    def test_export_pruning_uses_leading_decorator_bounds_without_changing_node_matches(self):
        root, expected = proposal_tree()
        exported = {'type': 'ExportNamedDeclaration', 'declaration': root['body'][0],
                    'specifiers': [], 'source': None, 'range': [5, 44]}
        root['body'] = [exported]
        decorator = expected[1]
        for convert in (lambda value: value, native):
            tree = convert(root)
            wrapper = walk.getField(tree, 'body')[0]
            cls = walk.getField(wrapper, 'declaration')
            target = walk.getField(cls, 'decorators')[0]
            for entry in (tree, wrapper):
                self.assertIs(walk.findNodeAt(entry, 0, 4, 'Decorator').node, target)
                self.assertIs(walk.findNodeAt(entry, None, 4, 'Decorator').node, target)
                self.assertIs(walk.findNodeAt(entry, 0, None, 'Decorator').node, target)
                self.assertIs(walk.findNodeAround(entry, 1, 'Decorator').node, target)
                self.assertIs(walk.findNodeAfter(entry, 0, 'Decorator').node, target)
                self.assertIs(walk.findNodeBefore(entry, 4, 'Decorator').node, target)
                # Expanding traversal bounds must not make the export itself
                # match positions outside its actual range.
                self.assertIsNone(walk.findNodeAround(entry, 1, 'ExportNamedDeclaration'))
                self.assertIsNone(walk.findNodeAt(entry, 0, 44, 'ExportNamedDeclaration'))
            self.assertEqual(walk.nodeRange(wrapper), (5, 44))
        self.assertEqual(decorator['range'], [0, 4])

    def test_extension_inventory_fixtures_are_traversable(self):
        for root in proposal_fixtures():
            seen = []
            walk.full(root, lambda node, state, kind, seen=seen: seen.append(node))
            self.assertIs(seen[-1], root)
            if walk.getField(root, 'type').endswith('Specifier'):
                self.assertEqual(seen, [root])
            else:
                self.assertTrue(any(walk.getField(node, 'type') == 'Identifier' for node in seen))

    def test_all_traversal_apis_keep_decorator_children_and_identity(self):
        for convert in (lambda value: value, native):
            root, expected = proposal_tree()
            if convert is native:
                root = native(root)
                expected = collect(root, 'full', None)
            original = copy.deepcopy(root)
            state = {'calls': 0}
            expected_ids = [id(node) for node in expected]
            for api in ('full', 'fullAncestor', 'simple', 'ancestor', 'recursive'):
                seen = collect(root, api, state)
                self.assertEqual([id(node) for node in seen], expected_ids, api)
                self.assertEqual(root, original)

    def test_searches_find_decorators_and_auto_accessors_with_utf16_positions(self):
        root, expected = proposal_tree()
        for node in expected:
            kind = node['type']
            start, end = node['range']
            for result in (walk.findNodeAt(root, start, end, kind),
                           walk.findNodeAround(root, start, kind),
                           walk.findNodeAfter(root, start, kind),
                           walk.findNodeBefore(root, end, kind)):
                self.assertIs(result.node, node)
        self.assertEqual(walk.nodeRange(expected[5]), (37, 41))

    def test_method_field_and_class_expression_decorators(self):
        root, expected = proposal_tree()
        for cls_kind in ('ClassDeclaration', 'ClassExpression'):
            root['body'][0]['type'] = cls_kind
            for member_kind in ('PropertyDefinition', 'MethodDefinition', 'AccessorProperty'):
                member = root['body'][0]['body']['body'][0]
                member['type'] = member_kind
                seen = []
                walk.full(root, lambda node, state, kind, seen=seen: seen.append(node))
                self.assertEqual([id(node) for node in seen], [id(node) for node in expected])

    @unittest.skipUnless(esprima is not None, 'coordinated parser required')
    def test_export_decorator_searches_cover_every_placement_and_preserve_ancestor_identity(self):
        sources = ['@d export class C{}', '@d export default class C{}',
                   '@d export default class {}', 'export @d class C{}',
                   'export default @d class C{}', 'export default @d class {}']
        for source in sources:
            tree = esprima.parseModule('/*\U0001f600*/\n' + source,
                                       {'decorators': True, 'range': True, 'loc': True, 'comment': True})
            original = tree.toDict()
            for root in (tree, original):
                wrapper = walk.getField(root, 'body')[0]
                cls = walk.getField(wrapper, 'declaration')
                target = walk.getField(cls, 'decorators')[0]
                expression = walk.getField(target, 'expression')
                state = object()
                ancestors = []
                walk.fullAncestor(root, lambda node, st, stack, kind, ancestors=ancestors:
                                  ancestors.append((node, list(stack))), state=state)
                path = next(stack for node, stack in ancestors if node is target)
                self.assertEqual([id(node) for node in path], [id(root), id(wrapper), id(cls), id(target)])
                for entry in (root, wrapper, cls):
                    for node in (target, expression):
                        start, end = walk.nodeRange(node)
                        kind = walk.getField(node, 'type')
                        for found in (walk.findNodeAt(entry, start, end, kind, state=state),
                                      walk.findNodeAround(entry, start, kind, state=state),
                                      walk.findNodeAfter(entry, start, kind, state=state),
                                      walk.findNodeBefore(entry, end, kind, state=state)):
                            self.assertIs(found.node, node, source)
                            self.assertIs(found.state, state)
                self.assertEqual(walk.nodeRange(wrapper), tuple(walk.getField(wrapper, 'range')))
            self.assertEqual(tree.toDict(), original)

    @unittest.skipUnless(esprima is not None, 'coordinated parser required')
    def test_native_parser_nodes_resources_import_phases_comments_and_positions(self):
        source = '@dec class C {@field accessor [key]="\U0001f600"; @method m(){}} '\
                 'async function f(){for await(await using x of xs){}} '\
                 'import defer * as ns from "m"; const v=import.source("m",options); // note'
        options = {'decorators': True, 'explicitResourceManagement': True,
                   'deferredImportEvaluation': True, 'sourcePhaseImports': True,
                   'ecmaVersion': 2026, 'range': True, 'loc': True, 'comment': True}
        tree = esprima.parseModule(source, options)
        original = tree.toDict()
        for root in (tree, original):
            seen = []
            walk.full(root, lambda node, state, kind, seen=seen: seen.append(node))
            names = [walk.getField(node, 'name') for node in seen]
            self.assertIn('dec', names)
            self.assertIn('field', names)
            self.assertIn('method', names)
            self.assertIn('key', names)
            self.assertIn('options', names)
            kinds = [walk.getField(node, 'type') for node in seen]
            self.assertEqual(kinds.count('Decorator'), 3)
            self.assertEqual(kinds.count('AccessorProperty'), 1)
            self.assertNotIn('Line', kinds)
            for node in seen:
                if walk.getField(node, 'type') in ('Decorator', 'AccessorProperty', 'ImportExpression'):
                    start, end = walk.nodeRange(node)
                    self.assertIs(walk.findNodeAt(root, start, end, walk.getField(node, 'type')).node, node)
        self.assertEqual(tree.toDict(), original)


if __name__ == '__main__':
    unittest.main()
