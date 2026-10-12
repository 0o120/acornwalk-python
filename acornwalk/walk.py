# MIT License

# Copyright (C) 2012-2020 by various contributors (see AUTHORS)

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


#  AST walker module for Mozilla Parser API compatible trees

from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from types import SimpleNamespace
from abc import get_cache_token


class VisitorTable(Protocol):
    """Indexed dispatch contract accepted by baseVisitor parameters."""
    def __getitem__(self, kind: str): ...


_MISSING = object()
_ALIASES = {"async": ("isAsync", "async_"), "await": ("allowAwait", "await_")}
_MAPPING_TYPES = {}


def _is_mapping(node):
    node_type = type(node)
    # Python's isinstance also observes an object's custom __class__ proxy.
    if node.__class__ is not node_type:
        return isinstance(node, Mapping)
    token = get_cache_token()
    cached = _MAPPING_TYPES.get(node_type)
    if cached is None or cached[0] != token:
        cached = (token, issubclass(node_type, Mapping))
        if len(_MAPPING_TYPES) >= 128:
            _MAPPING_TYPES.clear()
        _MAPPING_TYPES[node_type] = cached
    return cached[1]


def _attribute(node, name):
    value = getattr(node, name, _MISSING)
    if value is None:
        # esprima objects return None from __getattr__ for every absent field.
        # Distinguish that fallback from a declared, intentionally null field.
        namespace = getattr(node, "__dict__", None)
        declared = isinstance(namespace, Mapping) and name in namespace
        declared = declared or any(name in vars(cls) for cls in type(node).__mro__)
        if not declared:
            return _MISSING
    return value


def getField(node: object, name: str, default: Any = None) -> Any:
    """Read an ESTree field from a mapping or native node without copying it."""
    node_type = type(node)
    if node_type is SimpleNamespace:
        fields = node.__dict__
        value = fields.get(name, _MISSING)
        if (value is _MISSING or value is None) and name in _ALIASES:
            for alias in _ALIASES[name]:
                candidate = fields.get(alias, _MISSING)
                if candidate is not _MISSING and candidate is not None:
                    value = candidate
                    break
    elif node_type is dict or _is_mapping(node):
        value = node.get(name, _MISSING)
        if value is _MISSING and name in _ALIASES:
            for alias in _ALIASES[name]:
                value = node.get(alias, _MISSING)
                if value is not _MISSING:
                    break
    else:
        value = _attribute(node, name)
        if (value is _MISSING or value is None) and name in _ALIASES:
            for alias in _ALIASES[name]:
                candidate = _attribute(node, alias)
                if candidate is not _MISSING and candidate is not None:
                    value = candidate
                    break
    return default if value is _MISSING else value


def _kind(node: object, override: str | None = None) -> str:
    if override is not None:
        kind = override
    elif type(node) is dict:
        kind = node.get("type")
    elif type(node) is SimpleNamespace:
        kind = node.__dict__.get("type")
    else:
        kind = getField(node, "type")
    if not isinstance(kind, str) or not kind:
        raise ValueError("AST nodes require a nonempty string type field")
    return kind


def nodeRange(node: object) -> tuple[int, int]:
    """Return validated UTF-16 offsets, preferring start/end over range."""
    start, end = getField(node, "start"), getField(node, "end")
    if start is None and end is None:
        positions = getField(node, "range")
        if isinstance(positions, Sequence) and not isinstance(positions, (str, bytes)) and len(positions) == 2:
            start, end = positions
    if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int)
            or not isinstance(end, int) or start < 0 or end < start):
        raise ValueError(f"Node {getField(node, 'type', '<unknown>')!r} requires valid integer UTF-16 start/end or range offsets")
    return start, end


def _position(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer UTF-16 offset")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")


def _base(baseVisitor: VisitorTable | None) -> VisitorTable:
    return Base() if baseVisitor is None else baseVisitor


def _dispatch(visitor, kind):
    try:
        handler = visitor[kind]
    except (KeyError, AttributeError) as exc:
        raise ValueError(f"No walker for node type {kind!r}; provide a custom base visitor") from exc
    if not callable(handler):
        raise TypeError(f"Walker for node type {kind!r} must be callable")
    return handler


def simple(node, visitors, baseVisitor=None, state=None, override=None):
    """Call selected visitors after walking children (postorder)."""
    visitor = _base(baseVisitor)
    def c(node, st, override=None):
        kind = _kind(node, override)
        _dispatch(visitor, kind)(node, st, c)
        found = visitors.get(kind)
        if found is not None:
            found(node, st)
    c(node, state, override)


def ancestor(node, visitors, baseVisitor=None, state=None, override=None):
    """Like simple, with the current ancestor stack as a third argument."""
    visitor = _base(baseVisitor)
    ancestors = []
    def c(node, st, override=None):
        kind = _kind(node, override)
        is_new = not ancestors or ancestors[-1] is not node
        if is_new:
            ancestors.append(node)
        try:
            _dispatch(visitor, kind)(node, st, c)
            found = visitors.get(kind)
            if found is not None:
                found(node, ancestors if st is None else st, ancestors)
        finally:
            if is_new:
                ancestors.pop()
    c(node, state, override)


def recursive(node, state, funcs, baseVisitor=None, override=None):
    """Walk with overrides that control their own child recursion."""
    visitor = make({} if funcs is None else funcs, baseVisitor)
    def c(node, st, override=None):
        _dispatch(visitor, _kind(node, override))(node, st, c)
    c(node, state, override)


def makeTest(test):
    if isinstance(test, str):
        return lambda kind, node: kind == test
    if test is None:
        return lambda kind, node: True
    if not callable(test):
        raise TypeError("Search test must be a node type string, callable, or None")
    return test


@dataclass(frozen=True)
class Found:
    """A search match retaining the original node and state."""
    node: object
    state: object


class _Found(Exception):
    def __init__(self, node, state):
        self.result = Found(node, state)


def full(node, callback, baseVisitor=None, state=None, override=None):
    """Call callback once per node after its semantic children."""
    visitor = _base(baseVisitor)
    last = None
    def c(node, st, override=None):
        nonlocal last
        kind = _kind(node, override)
        _dispatch(visitor, kind)(node, st, c)
        if last is not node:
            callback(node, st, kind)
            last = node
    c(node, state, override)


def fullAncestor(node, callback, baseVisitor=None, state=None, override=None):
    """A full walk with callback(node, state, ancestors, category)."""
    visitor = _base(baseVisitor)
    ancestors = []
    last = None
    def c(node, st, override=None):
        nonlocal last
        kind = _kind(node, override)
        is_new = not ancestors or ancestors[-1] is not node
        if is_new:
            ancestors.append(node)
        try:
            _dispatch(visitor, kind)(node, st, c)
            if last is not node:
                callback(node, ancestors if st is None else st, ancestors, kind)
                last = node
        finally:
            if is_new:
                ancestors.pop()
    c(node, state, override)


def findNodeAt(node: object, start: int | None, end: int | None, test=None, baseVisitor=None, state=None) -> Found | None:
    """Find the innermost matching exact range; None is a wildcard."""
    if start is not None:
        _position(start, "start")
    if end is not None:
        _position(end, "end")
    if start is not None and end is not None and end < start:
        raise ValueError("end must not precede start")
    visitor, test = _base(baseVisitor), makeTest(test)
    def c(node, st, override=None):
        node_start, node_end = nodeRange(node)
        kind = _kind(node, override)
        if (start is None or node_start <= start) and (end is None or node_end >= end):
            _dispatch(visitor, kind)(node, st, c)
        if (start is None or node_start == start) and (end is None or node_end == end) and test(kind, node):
            raise _Found(node, st)
    try:
        c(node, state)
    except _Found as found:
        return found.result
    return None


def findNodeAround(node: object, pos: int, test=None, baseVisitor=None, state=None) -> Found | None:
    """Find the innermost match containing pos, including end boundaries."""
    _position(pos, "pos")
    visitor, test = _base(baseVisitor), makeTest(test)
    def c(node, st, override=None):
        node_start, node_end = nodeRange(node)
        kind = _kind(node, override)
        if node_start > pos or node_end < pos:
            return
        _dispatch(visitor, kind)(node, st, c)
        if test(kind, node):
            raise _Found(node, st)
    try:
        c(node, state)
    except _Found as found:
        return found.result
    return None


def findNodeAfter(node: object, pos: int, test=None, baseVisitor=None, state=None) -> Found | None:
    """Find the first outermost match starting at or after pos."""
    _position(pos, "pos")
    visitor, test = _base(baseVisitor), makeTest(test)
    def c(node, st, override=None):
        node_start, node_end = nodeRange(node)
        if node_end < pos:
            return
        kind = _kind(node, override)
        if node_start >= pos and test(kind, node):
            raise _Found(node, st)
        _dispatch(visitor, kind)(node, st, c)
    try:
        c(node, state)
    except _Found as found:
        return found.result
    return None


def findNodeBefore(node: object, pos: int, test=None, baseVisitor=None, state=None) -> Found | None:
    """Find the closest preceding match; ties favor the outer node."""
    _position(pos, "pos")
    visitor, test = _base(baseVisitor), makeTest(test)
    best = None
    def c(node, st, override=None):
        node_start, node_end = nodeRange(node)
        nonlocal best
        if node_start > pos:
            return
        kind = _kind(node, override)
        if node_end <= pos and (best is None or nodeRange(best.node)[1] < node_end) and test(kind, node):
            best = Found(node, st)
        _dispatch(visitor, kind)(node, st, c)
    c(node, state)
    return best


class _Overlay:
    def __init__(self, funcs, base):
        self.funcs = dict(funcs)
        self.base = base

    def __getitem__(self, kind):
        return self.funcs[kind] if kind in self.funcs else self.base[kind]


def make(funcs, baseVisitor=None):
    """Overlay handlers without modifying the supplied base."""
    return _Overlay(funcs, _base(baseVisitor))


def skipThrough(node, st, c):
    c(node, st)

def ignore(_node, _st, _c):
	pass

#  Node walkers.



class Base:

    def __init__(self):
        pass
    
    def __getitem__(self, key):
        return self.__dict__[key] if key in self.__dict__ else getattr(type(self), key)
        
    def Program(node, st, c):
        for stmt in getField(node, "body"):
            c(stmt, st, "Statement")

    def BlockStatement(node, st, c):
        for stmt in getField(node, "body"):
            c(stmt, st, "Statement")
    
    def StaticBlock(node, st, c):
        for stmt in getField(node, "body"):
            c(stmt, st, "Statement")

    def Statement(node, st, c):
        return skipThrough(node, st, c)
        
    def EmptyStatement(node, st, c):
        return ignore(node, st, c)

    def ExpressionStatement(node, st, c):
        return c(getField(node, "expression"), st, "Expression")
    
    def ParenthesizedExpression(node, st, c):
        return c(getField(node, "expression"), st, "Expression")
    
    def ChainExpression(node, st, c):
        return c(getField(node, "expression"), st, "Expression")
        
    def IfStatement(node, st, c):
        c(getField(node, "test"), st, "Expression")
        c(getField(node, "consequent"), st, "Statement")
        if getField(node, "alternate"):
            c(getField(node, "alternate"), st, "Statement")
    
    def LabeledStatement(node, st, c):
        return c(getField(node, "body"), st, "Statement")
    
    def BreakStatement(node, st, c):
        return ignore(node, st, c)
    
    def ContinueStatement(node, st, c):
        return ignore(node, st, c)
    
    def WithStatement(node, st, c):
        c(getField(node, "object"), st, "Expression")
        c(getField(node, "body"), st, "Statement")

    def SwitchStatement(node, st, c):
        c(getField(node, "discriminant"), st, "Expression")
        for cs in getField(node, "cases"):
            c(cs, st)

    def SwitchCase(node, st, c):
        if getField(node, "test"):
            c(getField(node, "test"), st, "Expression")
        for cons in getField(node, "consequent"):
            c(cons, st, "Statement")

    def ReturnStatement(node, st, c):
        if getField(node, "argument"):
            c(getField(node, "argument"), st, "Expression")

    def YieldExpression(node, st, c):
        if getField(node, "argument"):
            c(getField(node, "argument"), st, "Expression")

    def AwaitExpression(node, st, c):
        if getField(node, "argument"):
            c(getField(node, "argument"), st, "Expression")

    def ThrowStatement(node, st, c):
        return c(getField(node, "argument"), st, "Expression")
    
    def SpreadElement(node, st, c):
        c(getField(node, "argument"), st, "Expression")
    
    def TryStatement(node, st, c):
        c(getField(node, "block"), st, "Statement")
        if getField(node, "handler"):
            c(getField(node, "handler"), st)
        if getField(node, "finalizer"):
            c(getField(node, "finalizer"), st, "Statement")
    
    def CatchClause(node, st, c):
        if getField(node, "param"):
            c(getField(node, "param"), st, "Pattern")
        c(getField(node, "body"), st, "Statement")

    def WhileStatement(node, st, c):
        c(getField(node, "test"), st, "Expression")
        c(getField(node, "body"), st, "Statement")
    
    def DoWhileStatement(node, st, c):
        c(getField(node, "test"), st, "Expression")
        c(getField(node, "body"), st, "Statement")

    
    def ForStatement(node, st, c):
        if getField(node, "init"):
            c(getField(node, "init"), st, "ForInit")
        if getField(node, "test"):
            c(getField(node, "test"), st, "Expression")
        if getField(node, "update"):
            c(getField(node, "update"), st, "Expression")
        c(getField(node, "body"), st, "Statement")
    
    def ForInStatement(node, st, c):
        c(getField(node, "left"), st, "ForInit")
        c(getField(node, "right"), st, "Expression")
        c(getField(node, "body"), st, "Statement")
    
    def ForOfStatement(node, st, c):
        c(getField(node, "left"), st, "ForInit")
        c(getField(node, "right"), st, "Expression")
        c(getField(node, "body"), st, "Statement")

    def ForInit(node, st, c):
        if getField(node, "type") == "VariableDeclaration":
            c(node, st)
        else:
            c(node, st, "Expression")

    def DebuggerStatement(node, st, c):
        return ignore(node, st, c)

    def FunctionDeclaration(node, st, c):
        return c(node, st, "Function")

    def VariableDeclaration(node, st, c):
        for decl in getField(node, "declarations"):
            c(decl, st)

    def VariableDeclarator(node, st, c):
        c(getField(node, "id"), st, "Pattern")
        if getField(node, "init"):
            c(getField(node, "init"), st, "Expression")

    def Function(node, st, c):
        if getField(node, "id"):
            c(getField(node, "id"), st, "Pattern")
        for param in getField(node, "params"):
            c(param, st, "Pattern")
        c(getField(node, "body"), st, "Expression" if getField(node, "expression") else "Statement")

    def Pattern(node, st, c):
        if getField(node, "type") == "Identifier":
            c(node, st, "VariablePattern")
        elif getField(node, "type") == "MemberExpression":
            c(node, st, "MemberPattern")
        else:
            c(node, st)

    def VariablePattern(node, st, c):
        return ignore(node, st, c)

    def MemberPattern(node, st, c):
        return skipThrough(node, st, c)

    def RestElement(node, st, c):
        return c(getField(node, "argument"), st, "Pattern")

    def ArrayPattern(node, st, c):
        for elt in getField(node, "elements"):
            if elt:
                c(elt, st, "Pattern")

    def ObjectPattern(node, st, c):
        for prop in getField(node, "properties"):
            if getField(prop, "type") == 'Property':
                if getField(prop, "computed"):
                    c(getField(prop, "key"), st, "Expression")
                c(getField(prop, "value"), st, "Pattern")
            elif getField(prop, "type") == "RestElement":
                c(getField(prop, "argument"), st, "Pattern")

    def Expression(node, st, c):
        return skipThrough(node, st, c)

    def ThisExpression(node, st, c):
        return ignore(node, st, c)

    def Super(node, st, c):
        return ignore(node, st, c)

    def MetaProperty(node, st, c):
        return ignore(node, st, c)

    def ArrayExpression(node, st, c):
        for elt in getField(node, "elements"):
            if elt:
                c(elt, st, "Expression")

    def ObjectExpression(node, st, c):
        for prop in getField(node, "properties"):
            c(prop, st)

    def FunctionExpression(node, st, c):
        return c(node, st, "Function")

    def ArrowFunctionExpression(node, st, c):
        return c(node, st, "Function")

    def SequenceExpression(node, st, c):
        for expr in getField(node, "expressions"):
            c(expr, st, "Expression")

    def TemplateLiteral(node, st, c):
        for quasi in getField(node, "quasis"):
            c(quasi, st)
        for expr in getField(node, "expressions"):
            c(expr, st, "Expression")

    def TemplateElement(node, st, c):
        return ignore(node, st, c)

    def UnaryExpression(node, st, c):
        c(getField(node, "argument"), st, "Expression")

    def UpdateExpression(node, st, c):
        c(getField(node, "argument"), st, "Expression")

    def BinaryExpression(node, st, c):
        c(getField(node, "left"), st, "Expression")
        c(getField(node, "right"), st, "Expression")

    def LogicalExpression(node, st, c):
        c(getField(node, "left"), st, "Expression")
        c(getField(node, "right"), st, "Expression")

    def AssignmentExpression(node, st, c):
        c(getField(node, "left"), st, "Pattern")
        c(getField(node, "right"), st, "Expression")

    def AssignmentPattern(node, st, c):
        c(getField(node, "left"), st, "Pattern")
        c(getField(node, "right"), st, "Expression")

    def ConditionalExpression(node, st, c):
        c(getField(node, "test"), st, "Expression")
        c(getField(node, "consequent"), st, "Expression")
        c(getField(node, "alternate"), st, "Expression")

    def NewExpression(node, st, c):
        c(getField(node, "callee"), st, "Expression")
        if getField(node, "arguments"):
            for arg in getField(node, "arguments"):
                c(arg, st, "Expression")

    def CallExpression(node, st, c):
        c(getField(node, "callee"), st, "Expression")
        if getField(node, "arguments"):
            for arg in getField(node, "arguments"):
                c(arg, st, "Expression")

    def MemberExpression(node, st, c):
        c(getField(node, "object"), st, "Expression")
        if getField(node, "computed"):
            c(getField(node, "property"), st, "Expression")

    def ExportNamedDeclaration(node, st, c):
        if getField(node, "declaration"):
            c(getField(node, "declaration"), st, "Statement" if (getField(node, "type") == "ExportNamedDeclaration" or getField(getField(node, "declaration"), "id")) else "Expression")
        if getField(node, "source"):
            c(getField(node, "source"), st, "Expression")
        for attribute in getField(node, "attributes", ()) or ():
            c(attribute, st)

    def ExportDefaultDeclaration(node, st, c):
        if getField(node, "declaration"):
            declaration = getField(node, "declaration")
            c(declaration, st, "Statement" if _kind(declaration).endswith("Declaration") else "Expression")
        if getField(node, "source"):
            c(getField(node, "source"), st, "Expression")

    def ExportAllDeclaration(node, st, c):
        if getField(node, "exported"):
            c(getField(node, "exported"), st)
        c(getField(node, "source"), st, "Expression")
        for attribute in getField(node, "attributes", ()) or ():
            c(attribute, st)

    def ImportDeclaration(node, st, c):
        for spec in getField(node, "specifiers"):
            c(spec, st)
        c(getField(node, "source"), st, "Expression")
        for attribute in getField(node, "attributes", ()) or ():
            c(attribute, st)

    def ImportAttribute(node, st, c):
        c(getField(node, "value"), st, "Expression")

    def ImportExpression(node, st, c):
        c(getField(node, "source"), st, "Expression")
        if getField(node, "options") is not None:
            c(getField(node, "options"), st, "Expression")

    def ImportSpecifier(node, st, c):
        return ignore(node, st, c)

    def ImportDefaultSpecifier(node, st, c):
        return ignore(node, st, c)

    def ImportNamespaceSpecifier(node, st, c):
        return ignore(node, st, c)

    def Identifier(node, st, c):
        return ignore(node, st, c)

    def PrivateIdentifier(node, st, c):
        return ignore(node, st, c)

    def Literal(node, st, c):
        return ignore(node, st, c)

    def TaggedTemplateExpression(node, st, c):
        c(getField(node, "tag"), st, "Expression")
        c(getField(node, "quasi"), st, "Expression")

    def ClassDeclaration(node, st, c):
        return c(node, st, "Class")

    def ClassExpression(node, st, c):
        return c(node, st, "Class")

    def Class(node, st, c):
        if getField(node, "id"):
            c(getField(node, "id"), st, "Pattern")
        if getField(node, "superClass"):
            c(getField(node, "superClass"), st, "Expression")
        c(getField(node, "body"), st)

    def ClassBody(node, st, c):
        for elt in getField(node, "body"):
            c(elt, st)

    def MethodDefinition(node, st, c):
        if getField(node, "computed"):
            c(getField(node, "key"), st, "Expression")
        if getField(node, "value"):
            c(getField(node, "value"), st, "Expression")

    def PropertyDefinition(node, st, c):
        if getField(node, "computed"):
            c(getField(node, "key"), st, "Expression")
        if getField(node, "value"):
            c(getField(node, "value"), st, "Expression")

    def Property(node, st, c):
        if getField(node, "computed"):
            c(getField(node, "key"), st, "Expression")
        if getField(node, "value"):
            c(getField(node, "value"), st, "Expression")

    # The old parser used FieldDefinition for modern PropertyDefinition.
    FieldDefinition = PropertyDefinition

    # JSX is an explicit parser extension. Names have JSX-specific leaf types,
    # so they are observable without being reported as evaluated Identifiers.
    def JSXElement(node, st, c):
        c(getField(node, "openingElement"), st)
        for child in getField(node, "children", ()):
            c(child, st)
        if getField(node, "closingElement") is not None:
            c(getField(node, "closingElement"), st)

    def JSXFragment(node, st, c):
        c(getField(node, "openingFragment"), st)
        for child in getField(node, "children", ()):
            c(child, st)
        c(getField(node, "closingFragment"), st)

    def JSXOpeningElement(node, st, c):
        c(getField(node, "name"), st)
        for attribute in getField(node, "attributes", ()):
            c(attribute, st)

    def JSXClosingElement(node, st, c):
        c(getField(node, "name"), st)

    def JSXAttribute(node, st, c):
        c(getField(node, "name"), st)
        if getField(node, "value") is not None:
            c(getField(node, "value"), st)

    def JSXExpressionContainer(node, st, c):
        expression = getField(node, "expression")
        c(expression, st, None if _kind(expression) == "JSXEmptyExpression" else "Expression")

    def JSXSpreadAttribute(node, st, c):
        c(getField(node, "argument"), st, "Expression")

    def JSXSpreadChild(node, st, c):
        c(getField(node, "expression"), st, "Expression")

    def JSXMemberExpression(node, st, c):
        c(getField(node, "object"), st)
        c(getField(node, "property"), st)

    def JSXNamespacedName(node, st, c):
        c(getField(node, "namespace"), st)
        c(getField(node, "name"), st)

    JSXIdentifier = JSXText = JSXEmptyExpression = JSXOpeningFragment = JSXClosingFragment = ignore

