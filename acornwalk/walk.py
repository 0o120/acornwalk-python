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
from collections.abc import Mapping


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


def simple(node, visitors, baseVisitor=None, state=None, override=None):
    """Call selected visitors after walking children (postorder)."""
    visitor = _base(baseVisitor)
    def c(node, st, override=None):
        kind = override or node.type
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
        kind = override or node.type
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
        _dispatch(visitor, override or node.type)(node, st, c)
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
        kind = override or node.type
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
        kind = override or node.type
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


def findNodeAt(node, start, end, test=None, baseVisitor=None, state=None):
    """Find the innermost matching exact range; None is a wildcard."""
    visitor, test = _base(baseVisitor), makeTest(test)
    def c(node, st, override=None):
        kind = override or node.type
        if (start is None or node.start <= start) and (end is None or node.end >= end):
            _dispatch(visitor, kind)(node, st, c)
        if (start is None or node.start == start) and (end is None or node.end == end) and test(kind, node):
            raise _Found(node, st)
    try:
        c(node, state)
    except _Found as found:
        return found.result
    return None


def findNodeAround(node, pos, test=None, baseVisitor=None, state=None):
    """Find the innermost match containing pos, including end boundaries."""
    visitor, test = _base(baseVisitor), makeTest(test)
    def c(node, st, override=None):
        kind = override or node.type
        if node.start > pos or node.end < pos:
            return
        _dispatch(visitor, kind)(node, st, c)
        if test(kind, node):
            raise _Found(node, st)
    try:
        c(node, state)
    except _Found as found:
        return found.result
    return None


def findNodeAfter(node, pos, test=None, baseVisitor=None, state=None):
    """Find the first outermost match starting at or after pos."""
    visitor, test = _base(baseVisitor), makeTest(test)
    def c(node, st, override=None):
        if node.end < pos:
            return
        kind = override or node.type
        if node.start >= pos and test(kind, node):
            raise _Found(node, st)
        _dispatch(visitor, kind)(node, st, c)
    try:
        c(node, state)
    except _Found as found:
        return found.result
    return None


def findNodeBefore(node, pos, test=None, baseVisitor=None, state=None):
    """Find the closest preceding match; ties favor the outer node."""
    visitor, test = _base(baseVisitor), makeTest(test)
    best = None
    def c(node, st, override=None):
        nonlocal best
        if node.start > pos:
            return
        kind = override or node.type
        if node.end <= pos and (best is None or best.node.end < node.end) and test(kind, node):
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
        for stmt in node.body:
            c(stmt, st, "Statement")

    def BlockStatement(node, st, c):
        for stmt in node.body:
            c(stmt, st, "Statement")
    
    def StaticBlock(node, st, c):
        for stmt in node.body:
            c(stmt, st, "Statement")

    def Statement(node, st, c):
        return skipThrough(node, st, c)
        
    def EmptyStatement(node, st, c):
        return ignore(node, st, c)

    def ExpressionStatement(node, st, c):
        return c(node.expression, st, "Expression")
    
    def ParenthesizedExpression(node, st, c):
        return c(node.expression, st, "Expression")
    
    def ChainExpression(node, st, c):
        return c(node.expression, st, "Expression")
        
    def IfStatement(node, st, c):
        c(node.test, st, "Expression")
        c(node.consequent, st, "Statement")
        if node.alternate:
            c(node.alternate, st, "Statement")
    
    def LabeledStatement(node, st, c):
        return c(node.body, st, "Statement")
    
    def BreakStatement(node, st, c):
        return ignore(node, st, c)
    
    def ContinueStatement(node, st, c):
        return ignore(node, st, c)
    
    def WithStatement(node, st, c):
        c(node.object, st, "Expression")
        c(node.body, st, "Statement")

    def SwitchStatement(node, st, c):
        c(node.discriminant, st, "Expression")
        for cs in node.cases:
            c(cs, st)

    def SwitchCase(node, st, c):
        if node.test:
            c(node.test, st, "Expression")
        for cons in node.consequent:
            c(cons, st, "Statement")

    def ReturnStatement(node, st, c):
        if node.argument:
            c(node.argument, st, "Expression")

    def YieldExpression(node, st, c):
        if node.argument:
            c(node.argument, st, "Expression")

    def AwaitExpression(node, st, c):
        if node.argument:
            c(node.argument, st, "Expression")

    def ThrowStatement(node, st, c):
        return c(node.argument, st, "Expression")
    
    def SpreadElement(node, st, c):
        c(node.argument, st, "Expression")
    
    def TryStatement(node, st, c):
        c(node.block, st, "Statement")
        if node.handler:
            c(node.handler, st)
        if node.finalizer:
            c(node.finalizer, st, "Statement")
    
    def CatchClause(node, st, c):
        if node.param:
            c(node.param, st, "Pattern")
        c(node.body, st, "Statement")

    def WhileStatement(node, st, c):
        c(node.test, st, "Expression")
        c(node.body, st, "Statement")
    
    def DoWhileStatement(node, st, c):
        c(node.test, st, "Expression")
        c(node.body, st, "Statement")

    
    def ForStatement(node, st, c):
        if node.init:
            c(node.init, st, "ForInit")
        if node.test:
            c(node.test, st, "Expression")
        if node.update:
            c(node.update, st, "Expression")
        c(node.body, st, "Statement")
    
    def ForInStatement(node, st, c):
        c(node.left, st, "ForInit")
        c(node.right, st, "Expression")
        c(node.body, st, "Statement")
    
    def ForOfStatement(node, st, c):
        c(node.left, st, "ForInit")
        c(node.right, st, "Expression")
        c(node.body, st, "Statement")

    def ForInit(node, st, c):
        if node.type == "VariableDeclaration":
            c(node, st)
        else:
            c(node, st, "Expression")

    def DebuggerStatement(node, st, c):
        return ignore(node, st, c)

    def FunctionDeclaration(node, st, c):
        return c(node, st, "Function")

    def VariableDeclaration(node, st, c):
        for decl in node.declarations:
            c(decl, st)

    def VariableDeclarator(node, st, c):
        c(node.id, st, "Pattern")
        if node.init:
            c(node.init, st, "Expression")

    def Function(node, st, c):
        if node.id:
            c(node.id, st, "Pattern")
        for param in node.params:
            c(param, st, "Pattern")
        c(node.body, st, "Expression" if node.expression else "Statement")

    def Pattern(node, st, c):
        if node.type == "Identifier":
            c(node, st, "VariablePattern")
        elif node.type == "MemberExpression":
            c(node, st, "MemberPattern")
        else:
            c(node, st)

    def VariablePattern(node, st, c):
        return ignore(node, st, c)

    def MemberPattern(node, st, c):
        return skipThrough(node, st, c)

    def RestElement(node, st, c):
        return c(node.argument, st, "Pattern")

    def ArrayPattern(node, st, c):
        for elt in node.elements:
            if elt:
                c(elt, st, "Pattern")

    def ObjectPattern(node, st, c):
        for prop in node.properties:
            if prop.type == 'Property':
                if prop.computed:
                    c(prop.key, st, "Expression")
                c(prop.value, st, "Pattern")
            elif prop.type == "RestElement":
                c(prop.argument, st, "Pattern")

    def Expression(node, st, c):
        return skipThrough(node, st, c)

    def ThisExpression(node, st, c):
        return ignore(node, st, c)

    def Super(node, st, c):
        return ignore(node, st, c)

    def MetaProperty(node, st, c):
        return ignore(node, st, c)

    def ArrayExpression(node, st, c):
        for elt in node.elements:
            if elt:
                c(elt, st, "Expression")

    def ObjectExpression(node, st, c):
        for prop in node.properties:
            c(prop, st)

    def FunctionExpression(node, st, c):
        return c(node, st, "Function")

    def ArrowFunctionExpression(node, st, c):
        return c(node, st, "Function")

    def SequenceExpression(node, st, c):
        for expr in node.expressions:
            c(expr, st, "Expression")

    def TemplateLiteral(node, st, c):
        for quasi in node.quasis:
            c(quasi, st)
        for expr in node.expressions:
            c(expr, st, "Expression")

    def TemplateElement(node, st, c):
        return ignore(node, st, c)

    def UnaryExpression(node, st, c):
        c(node.argument, st, "Expression")

    def UpdateExpression(node, st, c):
        c(node.argument, st, "Expression")

    def BinaryExpression(node, st, c):
        c(node.left, st, "Expression")
        c(node.right, st, "Expression")

    def LogicalExpression(node, st, c):
        c(node.left, st, "Expression")
        c(node.right, st, "Expression")

    def AssignmentExpression(node, st, c):
        c(node.left, st, "Pattern")
        c(node.right, st, "Expression")

    def AssignmentPattern(node, st, c):
        c(node.left, st, "Pattern")
        c(node.right, st, "Expression")

    def ConditionalExpression(node, st, c):
        c(node.test, st, "Expression")
        c(node.consequent, st, "Expression")
        c(node.alternate, st, "Expression")

    def NewExpression(node, st, c):
        c(node.callee, st, "Expression")
        if node.arguments:
            for arg in node.arguments:
                c(arg, st, "Expression")

    def CallExpression(node, st, c):
        c(node.callee, st, "Expression")
        if node.arguments:
            for arg in node.arguments:
                c(arg, st, "Expression")

    def MemberExpression(node, st, c):
        c(node.object, st, "Expression")
        if node.computed:
            c(node.property, st, "Expression")

    def ExportNamedDeclaration(node, st, c):
        if node.declaration:
            c(node.declaration, st, "Statement" if (node.type == "ExportNamedDeclaration" or node.declaration.id) else "Expression")
        if node.source:
            c(node.source, st, "Expression")

    def ExportDefaultDeclaration(node, st, c):
        if node.declaration:
            c(node.declaration, st, "Statement" if (node.type == "ExportNamedDeclaration" or node.declaration.id) else "Expression")
        if node.source:
            c(node.source, st, "Expression")

    def ExportAllDeclaration(node, st, c):
        if node.exported:
            c(node.exported, st)
        c(node.source, st, "Expression")

    def ImportDeclaration(node, st, c):
        for spec in node.specifiers:
            c(spec, st)
        c(node.source, st, "Expression")

    def ImportExpression(node, st, c):
        c(node.source, st, "Expression")

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
        c(node.tag, st, "Expression")
        c(node.quasi, st, "Expression")

    def ClassDeclaration(node, st, c):
        return c(node, st, "Class")

    def ClassExpression(node, st, c):
        return c(node, st, "Class")

    def Class(node, st, c):
        if node.id:
            c(node.id, st, "Pattern")
        if node.superClass:
            c(node.superClass, st, "Expression")
        c(node.body, st)

    def ClassBody(node, st, c):
        for elt in node.body:
            c(elt, st)

    def MethodDefinition(node, st, c):
        if node.computed:
            c(node.key, st, "Expression")
        if node.value:
            c(node.value, st, "Expression")

    def PropertyDefinition(node, st, c):
        if node.computed:
            c(node.key, st, "Expression")
        if node.value:
            c(node.value, st, "Expression")

    def Property(node, st, c):
        if node.computed:
            c(node.key, st, "Expression")
        if node.value:
            c(node.value, st, "Expression")

