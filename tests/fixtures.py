"""One semantic traversal fixture for each concrete core ESTree handler."""


def node(node_type, **fields):
    return {"type": node_type, **fields}


def identifier(name="x"):
    return node("Identifier", name=name)


def literal(value=1):
    return node("Literal", value=value)


def empty():
    return node("EmptyStatement")


def block():
    return node("BlockStatement", body=[empty()])


def function(kind):
    return node(kind, id=identifier("f"), params=[identifier("a")], body=block(), expression=False)


def fixtures():
    attr = lambda: node("ImportAttribute", key=identifier("type"), value=literal("json"))
    prop = lambda: node("Property", key=literal("k"), value=literal(), computed=True)
    member = lambda: node("MemberExpression", object=identifier(), property=literal("k"), computed=True)
    method = lambda: node("MethodDefinition", key=literal("k"), value=function("FunctionExpression"), computed=True)
    classbody = lambda: node("ClassBody", body=[method(), node("PropertyDefinition", key=identifier("p"), value=literal(), computed=False),
        node("StaticBlock", body=[empty()])])
    values = [
        node("Program", body=[empty()]), block(), node("StaticBlock", body=[empty()]), empty(),
        node("ExpressionStatement", expression=literal()), node("ParenthesizedExpression", expression=literal()),
        node("ChainExpression", expression=member()), node("IfStatement", test=literal(), consequent=empty(), alternate=empty()),
        node("LabeledStatement", label=identifier(), body=empty()), node("BreakStatement", label=None),
        node("ContinueStatement", label=None), node("WithStatement", object=identifier(), body=empty()),
        node("SwitchStatement", discriminant=identifier(), cases=[node("SwitchCase", test=literal(), consequent=[empty()])]),
        node("SwitchCase", test=None, consequent=[empty()]), node("ReturnStatement", argument=literal()),
        node("YieldExpression", argument=literal(), delegate=True), node("AwaitExpression", argument=literal()),
        node("ThrowStatement", argument=literal()), node("SpreadElement", argument=identifier()),
        node("TryStatement", block=block(), handler=node("CatchClause", param=identifier(), body=block()), finalizer=block()),
        node("CatchClause", param=None, body=block()), node("WhileStatement", test=literal(), body=empty()),
        node("DoWhileStatement", test=literal(), body=empty()),
        node("ForStatement", init=node("VariableDeclaration", kind="let", declarations=[node("VariableDeclarator", id=identifier(), init=literal())]),
            test=literal(), update=node("UpdateExpression", argument=identifier(), operator="++", prefix=False), body=empty()),
        node("ForInStatement", left=member(), right=identifier(), body=empty()),
        node("ForOfStatement", left=node("VariableDeclaration", kind="const", declarations=[node("VariableDeclarator", id=identifier(), init=None)]),
            right=identifier(), body=empty(), **{"await": True}), node("DebuggerStatement"), function("FunctionDeclaration"),
        node("VariableDeclaration", kind="let", declarations=[node("VariableDeclarator", id=identifier(), init=literal())]),
        node("VariableDeclarator", id=identifier(), init=literal()), node("RestElement", argument=identifier()),
        node("ArrayPattern", elements=[identifier(), None, node("RestElement", argument=identifier())]),
        node("ObjectPattern", properties=[node("Property", key=literal("k"), computed=True,
            value=node("AssignmentPattern", left=identifier(), right=literal())), node("RestElement", argument=identifier())]),
        node("ThisExpression"), node("Super"), node("MetaProperty", meta=identifier("new"), property=identifier("target")),
        node("ArrayExpression", elements=[literal(), None, node("SpreadElement", argument=identifier())]),
        node("ObjectExpression", properties=[prop()]), function("FunctionExpression"),
        node("ArrowFunctionExpression", params=[identifier()], body=literal(), expression=True, **{"async": True}),
        node("SequenceExpression", expressions=[literal(), identifier()]),
        node("TemplateLiteral", quasis=[node("TemplateElement", value={"raw": "", "cooked": ""}, tail=False),
            node("TemplateElement", value={"raw": "", "cooked": ""}, tail=True)], expressions=[identifier()]),
        node("TemplateElement", value={"raw": "x", "cooked": "x"}, tail=True),
        node("UnaryExpression", argument=identifier(), operator="!", prefix=True),
        node("UpdateExpression", argument=identifier(), operator="++", prefix=True),
        node("BinaryExpression", left=identifier(), right=literal(), operator="+"),
        node("LogicalExpression", left=identifier(), right=literal(), operator="??"),
        node("AssignmentExpression", left=member(), right=literal(), operator="??="),
        node("AssignmentPattern", left=identifier(), right=literal()),
        node("ConditionalExpression", test=identifier(), consequent=literal(), alternate=literal()),
        node("NewExpression", callee=identifier(), arguments=[literal()]),
        node("CallExpression", callee=identifier(), arguments=[literal()]), member(),
        node("ExportNamedDeclaration", declaration=node("VariableDeclaration", kind="const", declarations=[node("VariableDeclarator", id=identifier(), init=literal())]),
            specifiers=[], source=None, attributes=[]),
        node("ExportDefaultDeclaration", declaration=literal(), source=None),
        node("ExportAllDeclaration", exported=identifier("ns"), source=literal("./x"), attributes=[attr()]),
        node("ImportDeclaration", source=literal("./x"), attributes=[attr()], specifiers=[
            node("ImportSpecifier", imported=identifier(), local=identifier()), node("ImportDefaultSpecifier", local=identifier()),
            node("ImportNamespaceSpecifier", local=identifier())]),
        node("ImportExpression", source=literal("./x"), options=node("ObjectExpression", properties=[prop()])), attr(),
        node("ImportSpecifier", imported=identifier(), local=identifier()), node("ImportDefaultSpecifier", local=identifier()),
        node("ImportNamespaceSpecifier", local=identifier()), identifier(), node("PrivateIdentifier", name="p"), literal(),
        node("TaggedTemplateExpression", tag=identifier(), quasi=node("TemplateLiteral", quasis=[node("TemplateElement", value={"raw": "", "cooked": ""}, tail=True)], expressions=[])),
        node("ClassDeclaration", id=identifier("C"), superClass=identifier("Parent"), body=classbody()),
        node("ClassExpression", id=None, superClass=None, body=classbody()), classbody(), method(),
        node("PropertyDefinition", key=literal("k"), value=literal(), computed=True), prop(),
    ]
    counter = 0
    def mark(value):
        nonlocal counter
        if isinstance(value, dict):
            if "type" in value:
                value["testId"] = counter
                counter += 1
            for child in list(value.values()):
                mark(child)
        elif isinstance(value, list):
            for child in value:
                mark(child)
    mark(values)
    return values
