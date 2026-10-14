# acornwalk

A pure Python semantic walker for ECMAScript ESTree ASTs, targeting node shapes
used by ECMAScript 2026 and the explicit JSX extension. Python 3.11+; no runtime
dependencies. Native parser objects and deserialized mappings are accepted
without copying nodes or mutating the AST.

```console
python -m pip install "acornwalk>=2,<3"
```

The 2.x release preserves the import and camelCase APIs and requires Python
3.11 or newer. It has no runtime dependencies. For native parser ASTs, install
`esprima-fork` 5.x separately (imported as `esprima`) and request `range=True`
when using position searches. See the
[migration notes](https://github.com/0o120/acornwalk-python/blob/master/CHANGELOG.md)
for the changes to searches, callback state and result objects.

```python
import acornwalk as walk
ast = {"type": "Program", "range": [0, 2], "body": [
    {"type": "ExpressionStatement", "range": [0, 2], "expression":
        {"type": "Identifier", "name": "x", "range": [0, 1]}}
]}
names = []
walk.simple(ast, {"Identifier": lambda node, state: state.append(node["name"])}, state=names)
assert names == ["x"]
assert walk.findNodeAt(ast, 0, 1, "Identifier").node is ast["body"][0]["expression"]
```

| API | Callback or result |
| --- | --- |
| `simple(node, visitors, baseVisitor=None, state=None, override=None)` | Postorder `visitor(node, state)` |
| `ancestor(node, visitors, baseVisitor=None, state=None, override=None)` | Postorder `visitor(node, state, ancestors)` |
| `recursive(node, state, funcs, baseVisitor=None, override=None)` | `visitor(node, state, recurse)` controls child recursion |
| `full(node, callback, baseVisitor=None, state=None, override=None)` | `callback(node, state, category)` |
| `fullAncestor(node, callback, baseVisitor=None, state=None, override=None)` | `callback(node, state, ancestors, category)` |
| `make(funcs, baseVisitor=None)` | Independent handler overlay |
| `findNodeAt(node, start, end, test=None, baseVisitor=None, state=None)` | Innermost exact range match; `None` bounds are wildcards |
| `findNodeAround(node, pos, test=None, baseVisitor=None, state=None)` | Innermost containing match, including end boundary |
| `findNodeAfter(node, pos, test=None, baseVisitor=None, state=None)` | First outermost match starting at/after `pos` |
| `findNodeBefore(node, pos, test=None, baseVisitor=None, state=None)` | Greatest end at/before `pos`; ties favor outer nodes |

Searches return `Found(node, state)` or `None`. Tests are node type strings,
`None` for any type, or `(category, node) -> bool` callables. Callback exceptions
propagate. Ancestor stacks contain the current node and are reused; copy the
list when retaining it. State `None` supplies ancestors as state for ancestor
walkers. Explicit `False`, `0`, `""`, `{}` and `[]` remain the supplied state.

```python
seen = []
walk.fullAncestor(ast, lambda node, state, stack, category:
    seen.append((walk.getField(node, "type"), len(stack))))
walk.recursive(ast, names, {"Identifier": lambda node, state, recurse:
    state.append(walk.getField(node, "name"))})
base = walk.make({"MyExtension": lambda node, state, recurse:
    recurse(walk.getField(node, "argument"), state, "Expression")})
walk.simple({"type": "MyExtension", "argument": ast["body"][0]["expression"]}, {}, base)
```

Visitor keys may be concrete types or categories such as `Expression`,
`Statement`, `Pattern` and `VariablePattern`. Bindings use `VariablePattern`;
ordinary references use `Identifier`. Noncomputed keys, labels, import binding
metadata, export specifier metadata and meta-property names are skipped as
evaluated references. Import attributes visit their value, not their key.
This is semantic traversal, not an exhaustive serialization visitor.

Custom bases may be mappings, `Base` objects or overlays. Instance and subclass
overrides are honored. Base handlers have the unbound signature
`(node, state, recurse)`; subclass handlers should use that signature or
`@staticmethod`. `make` does not mutate the supplied base. Unknown types raise
`ValueError` naming the type and the extension mechanism.

Positions are nonnegative integer **UTF-16 code-unit offsets**. Searches use
`start/end` or two-element `range`; `start/end` take precedence. Astral characters
occupy two units. Offsets are read as supplied, not converted from Python scalar
indices. With `esprima-fork`, request `range=True`. Missing/invalid positions
raise `ValueError`. `nodeRange(node)` exposes this accessor. `getField(node,
name, default=None)` reads mapping/attribute fields and native `isAsync`/`async_`
and `allowAwait`/`await_` aliases. An explicit canonical mapping field takes precedence.
Missing native fields honor the supplied default even for esprima's permissive
attribute lookup; declared null fields retain `None`.

Modern traversal covers object rest/spread, async functions/generators,
for-await metadata, chains, private names, public/private fields, static blocks,
module attributes and dynamic import options. Operators and literal metadata
use ordinary expression/leaf shapes. Legacy `FieldDefinition` is accepted as a
`PropertyDefinition` alias. Explicit JSX handlers cover elements, fragments,
names, attributes, expression containers, spread attributes/children and empty
expressions. JSX names keep their JSX-specific node types.

Decorators (`Decorator.expression`), decorated class/member arrays and
auto-accessors (`AccessorProperty`) have built-in handlers. Resource declaration
bindings and source/deferred import phases use their ordinary ESTree child
roles. Source positions preceding exported classes remain searchable even when
the class's decorators begin before the export wrapper's range; search matches
still use the original node bounds.

TypeScript, Flow and unrelated proposal nodes require custom visitors.
The walker does not validate grammar or editions. Mechanically walking an
unknown declaration kind with existing node shapes does not advertise parser
support for proposals. Circular graphs and excessive recursion depth are outside
the AST contract.

See [contributor instructions](https://github.com/0o120/acornwalk-python/blob/master/CONTRIBUTING.md)
and [CI results](https://github.com/0o120/acornwalk-python/actions).
Core parity is pinned
to [acorn-walk in acorn 8.15.0](https://github.com/acornjs/acorn/tree/8.15.0/acorn-walk).
Python differences include `None` state handling, mappings/ranges, validated
offsets, native aliases and the documented JSX extension.

[Performance measurements](https://github.com/0o120/acornwalk-python/blob/master/PERFORMANCE.md)
compare the original, modern
starting and current versions, including the old destructuring omission and
remaining native validation cost.

Release automation and version bumps are documented in [RELEASING.md](https://github.com/0o120/acornwalk-python/blob/master/RELEASING.md).
