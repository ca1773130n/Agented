"""Safe AST-based expression evaluator for workflow conditional nodes.

Parses Python-like expressions and evaluates them against a context dict
without using eval(), exec(), or compile() with exec mode.
"""

import ast
import operator

SAFE_COMPARE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

SAFE_BOOL_OPS = {
    ast.And: all,
    ast.Or: any,
}


def _resolve_name(name: str, context: dict) -> None:
    """Resolve a top-level name from the context dict."""
    if name in context:
        return context[name]
    raise ValueError(f"Undefined variable: '{name}'")


def _resolve_attribute(node: ast.Attribute, context: dict) -> None:
    """Resolve dot-notation attribute access on the context dict.

    E.g., pr.lines_changed -> context["pr"]["lines_changed"]
    """
    # Build the chain of attributes
    parts = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    else:
        raise ValueError(f"Unsupported attribute base: {ast.dump(current)}")

    # Reverse to get root-first order
    parts.reverse()

    # Walk into the context dict
    value = context
    for part in parts:
        if isinstance(value, dict):
            if part not in value:
                raise ValueError(f"Key not found: '{part}' in context path")
            value = value[part]
        else:
            raise ValueError(f"Cannot access attribute '{part}' on non-dict value")

    return value


def _eval_node(node, context: dict) -> None:
    """Recursively evaluate an AST node against a context dict.

    Only allows safe operations: comparisons, boolean ops, unary not,
    attribute access, name lookups, constants, and subscripts.
    """
    if isinstance(node, ast.Constant):
        return node.value

    elif isinstance(node, ast.Name):
        return _resolve_name(node.id, context)

    elif isinstance(node, ast.Attribute):
        return _resolve_attribute(node, context)

    elif isinstance(node, ast.Subscript):
        value = _eval_node(node.value, context)
        if isinstance(node.slice, ast.Constant):
            key = node.slice.value
        elif isinstance(node.slice, ast.Name):
            key = _resolve_name(node.slice.id, context)
        else:
            raise ValueError(f"Unsupported subscript slice: {ast.dump(node.slice)}")
        if isinstance(value, dict):
            return value[key]
        elif isinstance(value, (list, tuple)):
            return value[key]
        raise ValueError(f"Cannot subscript type: {type(value).__name__}")

    elif isinstance(node, ast.Compare):
        left = _eval_node(node.left, context)
        for op, comparator in zip(node.ops, node.comparators):
            op_func = SAFE_COMPARE_OPS.get(type(op))
            if op_func is None:
                raise ValueError(f"Unsupported comparison operator: {ast.dump(op)}")
            right = _eval_node(comparator, context)
            if not op_func(left, right):
                return False
            left = right
        return True

    elif isinstance(node, ast.BoolOp):
        op_func = SAFE_BOOL_OPS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported boolean operator: {ast.dump(node.op)}")
        return op_func(_eval_node(v, context) for v in node.values)

    elif isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return not _eval_node(node.operand, context)
        raise ValueError(f"Unsupported unary operator: {ast.dump(node.op)}")

    elif isinstance(node, ast.List):
        return [_eval_node(elt, context) for elt in node.elts]

    elif isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt, context) for elt in node.elts)

    else:
        raise ValueError(f"Unsupported expression node: {ast.dump(node)}")


def evaluate_condition(expression: str, context: dict) -> bool:
    """Evaluate a condition expression against a sandboxed context dict.

    Uses Python's ast module to parse the expression and walk the AST,
    only allowing safe operations. Does NOT use eval(), exec(), or compile()
    with exec mode.

    Args:
        expression: A Python-like condition expression string.
        context: A dict of variables available for evaluation.

    Returns:
        Boolean result of the expression evaluation.

    Raises:
        ValueError: If the expression contains unsupported AST nodes.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e}") from e

    return bool(_eval_node(tree.body, context))
