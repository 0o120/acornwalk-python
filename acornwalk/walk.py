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

from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from abc import get_cache_token
from reprlib import recursive_repr
from functools import partial


_MISSING = object()
_ALIASES = {"async": ("isAsync", "async_"), "await": ("allowAwait", "await_")}
_MAPPING_TYPES = {}
_READER_TYPES = {}


def _is_mapping(node, node_type):
    # Python's isinstance also observes an object's custom __class__ proxy.
    if node.__class__ is not node_type:
        return isinstance(node, Mapping)
    token = get_cache_token()
    try:
        cached = _MAPPING_TYPES[node_type]
    except KeyError:
        cached = None
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


def getField(node: object, name: str, default: object = None) -> object:
    """Read an ESTree field from a mapping or native node without copying it."""
    node_type = type(node)
    if type(name) is str and name not in _ALIASES:
        if node_type is SimpleNamespace:
            return node.__dict__.get(name, default)
        if node_type is dict or _is_mapping(node, node_type):
            return node.get(name, default)
        value = getattr(node, name, _MISSING)
        if value is None and default is not None:
            # Missing-None and declared-None have the same result when the
            # requested default is None, so only inspect declarations when
            # a different default makes that distinction observable.
            namespace = getattr(node, "__dict__", None)
            declared = isinstance(namespace, Mapping) and name in namespace
            declared = declared or any(name in vars(cls) for cls in type(node).__mro__)
            if not declared:
                return default
        return default if value is _MISSING else value
    if node_type is SimpleNamespace:
        fields = node.__dict__
        value = fields.get(name, _MISSING)
        if (value is _MISSING or value is None) and name in _ALIASES:
            for alias in _ALIASES[name]:
                candidate = fields.get(alias, _MISSING)
                if candidate is not _MISSING and candidate is not None:
                    value = candidate
                    break
    elif node_type is dict or _is_mapping(node, node_type):
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
    else:
        node_type = type(node)
        if node_type is dict or (node_type is not SimpleNamespace and _is_mapping(node, node_type)):
            kind = node.get("type")
        else:
            # A missing/null kind is invalid either way. A literal attribute
            # read also lets Python specialize ordinary native AST access.
            try:
                kind = node.type
            except AttributeError:
                kind = None
    if not isinstance(kind, str) or not kind:
        raise ValueError("AST nodes require a nonempty string type field")
    return kind


def _attribute_field(node, node_type, token, name, default=None):
    if default is not None or get_cache_token() != token or node.__class__ is not node_type:
        return getField(node, name, default)
    return getattr(node, name, None)


def _mapping_field(node, node_type, token, name, default=None):
    if get_cache_token() != token or node.__class__ is not node_type:
        return getField(node, name, default)
    return node.get(name, default)


def _field_reader(node):
    """Bind non-alias field access for one built-in semantic handler."""
    node_type = type(node)
    if node_type is dict:
        return node.get
    if node_type is SimpleNamespace:
        return node.__dict__.get
    # Custom __getattribute__/__class__ implementations must retain every
    # dynamic lookup. Ordinary attributes/descriptors use getattr below; a
    # callback changing Mapping registration or the class selects getField.
    token = get_cache_token()
    try:
        cached = _READER_TYPES[node_type]
    except KeyError:
        cached = None
    if cached is None or cached[0] != token:
        if (node_type.__getattribute__ is not object.__getattribute__
                or node_type.__class__ is not type(node_type)):
            reader = None
        else:
            reader = _mapping_field if issubclass(node_type, Mapping) else _attribute_field
        if len(_READER_TYPES) >= 128:
            _READER_TYPES.clear()
        cached = (token, reader)
        _READER_TYPES[node_type] = cached
    reader = cached[1]
    if reader is None:
        return partial(getField, node)
    return partial(reader, node, node_type, token)


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


def _base(baseVisitor):
    return Base() if baseVisitor is None else baseVisitor


def _dispatch(visitor, kind):
    try:
        handler = visitor[kind]
    except (KeyError, AttributeError) as exc:
        raise ValueError(f"No walker for node type {kind!r}; provide a custom base visitor") from exc
    if not callable(handler):
        raise TypeError(f"Walker for node type {kind!r} must be callable")
    return handler


def _default_dispatch(_visitor, kind):
    # The default instance has no overrides. Resolve the class descriptor
    # directly, preserving changes to Base during callbacks without another
    # Python __getitem__ call for each category and concrete node.
    try:
        handler = getattr(Base, kind)
    except AttributeError as exc:
        raise ValueError(f"No walker for node type {kind!r}; provide a custom base visitor") from exc
    if not callable(handler):
        raise TypeError(f"Walker for node type {kind!r} must be callable")
    return handler


def _select_dispatch(visitor, base_visitor):
    if (base_visitor is None and type(visitor) is _DEFAULT_BASE_CLASS
            and not visitor.__dict__
            and Base.__init__ is _DEFAULT_BASE_INIT
            and Base.__getitem__ is _DEFAULT_BASE_GETITEM):
        return _default_dispatch
    return _dispatch


def simple(node, visitors, baseVisitor=None, state=None, override=None):
    """Call selected visitors after walking children (postorder)."""
    visitor = _base(baseVisitor)
    dispatch = _select_dispatch(visitor, baseVisitor)
    def c(node, st, override=None):
        kind = _kind(node, override)
        dispatch(visitor, kind)(node, st, c)
        found = visitors.get(kind)
        if found is not None:
            found(node, st)
    c(node, state, override)


def ancestor(node, visitors, baseVisitor=None, state=None, override=None):
    """Like simple, with the current ancestor stack as a third argument."""
    visitor = _base(baseVisitor)
    dispatch = _select_dispatch(visitor, baseVisitor)
    ancestors = []
    def c(node, st, override=None):
        kind = _kind(node, override)
        is_new = not ancestors or ancestors[-1] is not node
        if is_new:
            ancestors.append(node)
        try:
            dispatch(visitor, kind)(node, st, c)
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


class Found:
    """A search match retaining the original node and state."""
    __slots__ = ("node", "state", "__weakref__")
    __match_args__ = ("node", "state")
    node: object
    state: object

    def __init__(self, node: object, state: object):
        object.__setattr__(self, "node", node)
        object.__setattr__(self, "state", state)

    def __setattr__(self, name, value):
        if type(self) is Found or name in ("node", "state"):
            raise AttributeError(f"cannot assign to field {name!r}")
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if type(self) is Found or name in ("node", "state"):
            raise AttributeError(f"cannot delete field {name!r}")
        object.__delattr__(self, name)

    @recursive_repr()
    def __repr__(self):
        return f"{self.__class__.__qualname__}(node={self.node!r}, state={self.state!r})"

    def __eq__(self, other):
        if other.__class__ is self.__class__:
            return (self.node, self.state) == (other.node, other.state)
        return NotImplemented

    def __hash__(self):
        return hash((self.node, self.state))

    def __reduce_ex__(self, protocol):
        return (_restore_found, (type(self), self.node, self.state, getattr(self, "__dict__", None)))

    def __deepcopy__(self, memo):
        # Memoize the empty result before visiting either field: node/state
        # containers may point back to the Found object itself.
        from copy import deepcopy
        result = type(self).__new__(type(self))
        memo[id(self)] = result
        object.__setattr__(result, "node", deepcopy(self.node, memo))
        object.__setattr__(result, "state", deepcopy(self.state, memo))
        extras = getattr(self, "__dict__", None)
        if extras:
            result.__dict__.update(deepcopy(extras, memo))
        return result


def _restore_found(cls, node, state, extras):
    result = cls.__new__(cls)
    object.__setattr__(result, "node", node)
    object.__setattr__(result, "state", state)
    if extras:
        result.__dict__.update(extras)
    return result


class _Found(Exception):
    def __init__(self, node, state):
        self.result = Found(node, state)


def full(node, callback, baseVisitor=None, state=None, override=None):
    """Call callback once per node after its semantic children."""
    visitor = _base(baseVisitor)
    dispatch = _select_dispatch(visitor, baseVisitor)
    last = None
    def c(node, st, override=None):
        nonlocal last
        kind = _kind(node, override)
        handler = dispatch(visitor, kind)
        # A category's transparent delegation visits the same object/state.
        # Full walkers report only the final concrete category, so it can be
        # resolved here without a second recursive callback frame.
        while handler is skipThrough:
            kind = _kind(node)
            handler = dispatch(visitor, kind)
        if handler is not ignore:
            handler(node, st, c)
        if last is not node:
            callback(node, st, kind)
            last = node
    c(node, state, override)


def fullAncestor(node, callback, baseVisitor=None, state=None, override=None):
    """A full walk with callback(node, state, ancestors, category)."""
    visitor = _base(baseVisitor)
    dispatch = _select_dispatch(visitor, baseVisitor)
    ancestors = []
    last = None
    def c(node, st, override=None):
        nonlocal last
        kind = _kind(node, override)
        handler = dispatch(visitor, kind)
        while handler is skipThrough:
            kind = _kind(node)
            handler = dispatch(visitor, kind)
        is_new = not ancestors or ancestors[-1] is not node
        if is_new:
            ancestors.append(node)
        try:
            if handler is not ignore:
                handler(node, st, c)
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
    dispatch = _select_dispatch(visitor, baseVisitor)
    def c(node, st, override=None):
        node_start, node_end = nodeRange(node)
        kind = _kind(node, override)
        if (start is None or node_start <= start) and (end is None or node_end >= end):
            dispatch(visitor, kind)(node, st, c)
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
    dispatch = _select_dispatch(visitor, baseVisitor)
    def c(node, st, override=None):
        node_start, node_end = nodeRange(node)
        kind = _kind(node, override)
        if node_start > pos or node_end < pos:
            return
        dispatch(visitor, kind)(node, st, c)
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
    dispatch = _select_dispatch(visitor, baseVisitor)
    def c(node, st, override=None):
        node_start, node_end = nodeRange(node)
        if node_end < pos:
            return
        kind = _kind(node, override)
        if node_start >= pos and test(kind, node):
            raise _Found(node, st)
        dispatch(visitor, kind)(node, st, c)
    try:
        c(node, state)
    except _Found as found:
        return found.result
    return None


def findNodeBefore(node: object, pos: int, test=None, baseVisitor=None, state=None) -> Found | None:
    """Find the closest preceding match; ties favor the outer node."""
    _position(pos, "pos")
    visitor, test = _base(baseVisitor), makeTest(test)
    dispatch = _select_dispatch(visitor, baseVisitor)
    best = None
    def c(node, st, override=None):
        node_start, node_end = nodeRange(node)
        nonlocal best
        if node_start > pos:
            return
        kind = _kind(node, override)
        if node_end <= pos and (best is None or nodeRange(best.node)[1] < node_end) and test(kind, node):
            best = Found(node, st)
        dispatch(visitor, kind)(node, st, c)
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
        read = _field_reader(node)
        for stmt in read("body"):
            c(stmt, st, "Statement")

    def BlockStatement(node, st, c):
        read = _field_reader(node)
        for stmt in read("body"):
            c(stmt, st, "Statement")
    
    def StaticBlock(node, st, c):
        read = _field_reader(node)
        for stmt in read("body"):
            c(stmt, st, "Statement")

    Statement = skipThrough
        
    EmptyStatement = ignore

    def ExpressionStatement(node, st, c):
        read = _field_reader(node)
        return c(read("expression"), st, "Expression")
    
    def ParenthesizedExpression(node, st, c):
        read = _field_reader(node)
        return c(read("expression"), st, "Expression")
    
    def ChainExpression(node, st, c):
        read = _field_reader(node)
        return c(read("expression"), st, "Expression")
        
    def IfStatement(node, st, c):
        read = _field_reader(node)
        c(read("test"), st, "Expression")
        c(read("consequent"), st, "Statement")
        if read("alternate"):
            c(read("alternate"), st, "Statement")
    
    def LabeledStatement(node, st, c):
        read = _field_reader(node)
        return c(read("body"), st, "Statement")
    
    BreakStatement = ignore
    
    ContinueStatement = ignore
    
    def WithStatement(node, st, c):
        read = _field_reader(node)
        c(read("object"), st, "Expression")
        c(read("body"), st, "Statement")

    def SwitchStatement(node, st, c):
        read = _field_reader(node)
        c(read("discriminant"), st, "Expression")
        for cs in read("cases"):
            c(cs, st)

    def SwitchCase(node, st, c):
        read = _field_reader(node)
        if read("test"):
            c(read("test"), st, "Expression")
        for cons in read("consequent"):
            c(cons, st, "Statement")

    def ReturnStatement(node, st, c):
        read = _field_reader(node)
        if read("argument"):
            c(read("argument"), st, "Expression")

    def YieldExpression(node, st, c):
        read = _field_reader(node)
        if read("argument"):
            c(read("argument"), st, "Expression")

    def AwaitExpression(node, st, c):
        read = _field_reader(node)
        if read("argument"):
            c(read("argument"), st, "Expression")

    def ThrowStatement(node, st, c):
        read = _field_reader(node)
        return c(read("argument"), st, "Expression")
    
    def SpreadElement(node, st, c):
        read = _field_reader(node)
        c(read("argument"), st, "Expression")
    
    def TryStatement(node, st, c):
        read = _field_reader(node)
        c(read("block"), st, "Statement")
        if read("handler"):
            c(read("handler"), st)
        if read("finalizer"):
            c(read("finalizer"), st, "Statement")
    
    def CatchClause(node, st, c):
        read = _field_reader(node)
        if read("param"):
            c(read("param"), st, "Pattern")
        c(read("body"), st, "Statement")

    def WhileStatement(node, st, c):
        read = _field_reader(node)
        c(read("test"), st, "Expression")
        c(read("body"), st, "Statement")
    
    def DoWhileStatement(node, st, c):
        read = _field_reader(node)
        c(read("test"), st, "Expression")
        c(read("body"), st, "Statement")

    
    def ForStatement(node, st, c):
        read = _field_reader(node)
        if read("init"):
            c(read("init"), st, "ForInit")
        if read("test"):
            c(read("test"), st, "Expression")
        if read("update"):
            c(read("update"), st, "Expression")
        c(read("body"), st, "Statement")
    
    def ForInStatement(node, st, c):
        read = _field_reader(node)
        c(read("left"), st, "ForInit")
        c(read("right"), st, "Expression")
        c(read("body"), st, "Statement")
    
    def ForOfStatement(node, st, c):
        read = _field_reader(node)
        c(read("left"), st, "ForInit")
        c(read("right"), st, "Expression")
        c(read("body"), st, "Statement")

    def ForInit(node, st, c):
        read = _field_reader(node)
        if read("type") == "VariableDeclaration":
            c(node, st)
        else:
            c(node, st, "Expression")

    DebuggerStatement = ignore

    def FunctionDeclaration(node, st, c):
        return c(node, st, "Function")

    def VariableDeclaration(node, st, c):
        read = _field_reader(node)
        for decl in read("declarations"):
            c(decl, st)

    def VariableDeclarator(node, st, c):
        read = _field_reader(node)
        c(read("id"), st, "Pattern")
        if read("init"):
            c(read("init"), st, "Expression")

    def Function(node, st, c):
        read = _field_reader(node)
        if read("id"):
            c(read("id"), st, "Pattern")
        for param in read("params"):
            c(param, st, "Pattern")
        c(read("body"), st, "Expression" if read("expression") else "Statement")

    def Pattern(node, st, c):
        read = _field_reader(node)
        if read("type") == "Identifier":
            c(node, st, "VariablePattern")
        elif read("type") == "MemberExpression":
            c(node, st, "MemberPattern")
        else:
            c(node, st)

    VariablePattern = ignore

    MemberPattern = skipThrough

    def RestElement(node, st, c):
        read = _field_reader(node)
        return c(read("argument"), st, "Pattern")

    def ArrayPattern(node, st, c):
        read = _field_reader(node)
        for elt in read("elements"):
            if elt:
                c(elt, st, "Pattern")

    def ObjectPattern(node, st, c):
        read = _field_reader(node)
        for prop in read("properties"):
            if getField(prop, "type") == 'Property':
                if getField(prop, "computed"):
                    c(getField(prop, "key"), st, "Expression")
                c(getField(prop, "value"), st, "Pattern")
            elif getField(prop, "type") == "RestElement":
                c(getField(prop, "argument"), st, "Pattern")

    Expression = skipThrough

    ThisExpression = ignore

    Super = ignore

    MetaProperty = ignore

    def ArrayExpression(node, st, c):
        read = _field_reader(node)
        for elt in read("elements"):
            if elt:
                c(elt, st, "Expression")

    def ObjectExpression(node, st, c):
        read = _field_reader(node)
        for prop in read("properties"):
            c(prop, st)

    def FunctionExpression(node, st, c):
        return c(node, st, "Function")

    def ArrowFunctionExpression(node, st, c):
        return c(node, st, "Function")

    def SequenceExpression(node, st, c):
        read = _field_reader(node)
        for expr in read("expressions"):
            c(expr, st, "Expression")

    def TemplateLiteral(node, st, c):
        read = _field_reader(node)
        for quasi in read("quasis"):
            c(quasi, st)
        for expr in read("expressions"):
            c(expr, st, "Expression")

    TemplateElement = ignore

    def UnaryExpression(node, st, c):
        read = _field_reader(node)
        c(read("argument"), st, "Expression")

    def UpdateExpression(node, st, c):
        read = _field_reader(node)
        c(read("argument"), st, "Expression")

    def BinaryExpression(node, st, c):
        read = _field_reader(node)
        c(read("left"), st, "Expression")
        c(read("right"), st, "Expression")

    def LogicalExpression(node, st, c):
        read = _field_reader(node)
        c(read("left"), st, "Expression")
        c(read("right"), st, "Expression")

    def AssignmentExpression(node, st, c):
        read = _field_reader(node)
        c(read("left"), st, "Pattern")
        c(read("right"), st, "Expression")

    def AssignmentPattern(node, st, c):
        read = _field_reader(node)
        c(read("left"), st, "Pattern")
        c(read("right"), st, "Expression")

    def ConditionalExpression(node, st, c):
        read = _field_reader(node)
        c(read("test"), st, "Expression")
        c(read("consequent"), st, "Expression")
        c(read("alternate"), st, "Expression")

    def NewExpression(node, st, c):
        read = _field_reader(node)
        c(read("callee"), st, "Expression")
        if read("arguments"):
            for arg in read("arguments"):
                c(arg, st, "Expression")

    def CallExpression(node, st, c):
        read = _field_reader(node)
        c(read("callee"), st, "Expression")
        if read("arguments"):
            for arg in read("arguments"):
                c(arg, st, "Expression")

    def MemberExpression(node, st, c):
        read = _field_reader(node)
        c(read("object"), st, "Expression")
        if read("computed"):
            c(read("property"), st, "Expression")

    def ExportNamedDeclaration(node, st, c):
        read = _field_reader(node)
        if read("declaration"):
            c(read("declaration"), st, "Statement" if (read("type") == "ExportNamedDeclaration" or getField(read("declaration"), "id")) else "Expression")
        if read("source"):
            c(read("source"), st, "Expression")
        for attribute in read("attributes", ()) or ():
            c(attribute, st)

    def ExportDefaultDeclaration(node, st, c):
        read = _field_reader(node)
        if read("declaration"):
            declaration = read("declaration")
            c(declaration, st, "Statement" if _kind(declaration).endswith("Declaration") else "Expression")
        if read("source"):
            c(read("source"), st, "Expression")

    def ExportAllDeclaration(node, st, c):
        read = _field_reader(node)
        if read("exported"):
            c(read("exported"), st)
        c(read("source"), st, "Expression")
        for attribute in read("attributes", ()) or ():
            c(attribute, st)

    def ImportDeclaration(node, st, c):
        read = _field_reader(node)
        for spec in read("specifiers"):
            c(spec, st)
        c(read("source"), st, "Expression")
        for attribute in read("attributes", ()) or ():
            c(attribute, st)

    def ImportAttribute(node, st, c):
        read = _field_reader(node)
        c(read("value"), st, "Expression")

    def ImportExpression(node, st, c):
        read = _field_reader(node)
        c(read("source"), st, "Expression")
        if read("options") is not None:
            c(read("options"), st, "Expression")

    ImportSpecifier = ignore

    ImportDefaultSpecifier = ignore

    ImportNamespaceSpecifier = ignore

    Identifier = ignore

    PrivateIdentifier = ignore

    Literal = ignore

    def TaggedTemplateExpression(node, st, c):
        read = _field_reader(node)
        c(read("tag"), st, "Expression")
        c(read("quasi"), st, "Expression")

    def ClassDeclaration(node, st, c):
        return c(node, st, "Class")

    def ClassExpression(node, st, c):
        return c(node, st, "Class")

    def Class(node, st, c):
        read = _field_reader(node)
        if read("id"):
            c(read("id"), st, "Pattern")
        if read("superClass"):
            c(read("superClass"), st, "Expression")
        c(read("body"), st)

    def ClassBody(node, st, c):
        read = _field_reader(node)
        for elt in read("body"):
            c(elt, st)

    def MethodDefinition(node, st, c):
        read = _field_reader(node)
        if read("computed"):
            c(read("key"), st, "Expression")
        if read("value"):
            c(read("value"), st, "Expression")

    def PropertyDefinition(node, st, c):
        read = _field_reader(node)
        if read("computed"):
            c(read("key"), st, "Expression")
        if read("value"):
            c(read("value"), st, "Expression")

    def Property(node, st, c):
        read = _field_reader(node)
        if read("computed"):
            c(read("key"), st, "Expression")
        if read("value"):
            c(read("value"), st, "Expression")

    # The old parser used FieldDefinition for modern PropertyDefinition.
    FieldDefinition = PropertyDefinition

    # JSX is an explicit parser extension. Names have JSX-specific leaf types,
    # so they are observable without being reported as evaluated Identifiers.
    def JSXElement(node, st, c):
        read = _field_reader(node)
        c(read("openingElement"), st)
        for child in read("children", ()):
            c(child, st)
        if read("closingElement") is not None:
            c(read("closingElement"), st)

    def JSXFragment(node, st, c):
        read = _field_reader(node)
        c(read("openingFragment"), st)
        for child in read("children", ()):
            c(child, st)
        c(read("closingFragment"), st)

    def JSXOpeningElement(node, st, c):
        read = _field_reader(node)
        c(read("name"), st)
        for attribute in read("attributes", ()):
            c(attribute, st)

    def JSXClosingElement(node, st, c):
        read = _field_reader(node)
        c(read("name"), st)

    def JSXAttribute(node, st, c):
        read = _field_reader(node)
        c(read("name"), st)
        if read("value") is not None:
            c(read("value"), st)

    def JSXExpressionContainer(node, st, c):
        read = _field_reader(node)
        expression = read("expression")
        c(expression, st, None if _kind(expression) == "JSXEmptyExpression" else "Expression")

    def JSXSpreadAttribute(node, st, c):
        read = _field_reader(node)
        c(read("argument"), st, "Expression")

    def JSXSpreadChild(node, st, c):
        read = _field_reader(node)
        c(read("expression"), st, "Expression")

    def JSXMemberExpression(node, st, c):
        read = _field_reader(node)
        c(read("object"), st)
        c(read("property"), st)

    def JSXNamespacedName(node, st, c):
        read = _field_reader(node)
        c(read("namespace"), st)
        c(read("name"), st)

    JSXIdentifier = JSXText = JSXEmptyExpression = JSXOpeningFragment = JSXClosingFragment = ignore


_DEFAULT_BASE_CLASS = Base
_DEFAULT_BASE_INIT = Base.__init__
_DEFAULT_BASE_GETITEM = Base.__getitem__

