"""Workflow DAG validation service (API-09).

Enhanced validation that checks for cycles, missing node references,
invalid/dangerous condition expressions, and unreachable nodes.
Returns detailed, descriptive error messages.
"""

import ast
import graphlib
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Dangerous constructs that must be rejected in condition expressions
DANGEROUS_NAMES = frozenset(
    {
        "import",
        "exec",
        "eval",
        "__builtins__",
        "__import__",
        "globals",
        "locals",
        "compile",
        "getattr",
        "setattr",
        "delattr",
        "open",
        "breakpoint",
        "exit",
        "quit",
    }
)


def validate_workflow_dag(graph_data: dict) -> Tuple[bool, List[str]]:
    """Validate a workflow DAG for correctness.

    Checks:
    1. Cycle detection via TopologicalSorter
    2. Missing node references in edges
    3. Invalid/dangerous condition expressions in conditional nodes
    4. Unreachable nodes (warnings only, do not reject)

    Args:
        graph_data: Dict with "nodes" and "edges" keys.

    Returns:
        Tuple of (is_valid, error_messages). Warnings are prefixed with "WARNING:".
    """
    errors: List[str] = []
    warnings: List[str] = []

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    if not nodes:
        return False, ["Graph must have at least one node"]

    # Build node ID set and node lookup
    node_ids = set()
    node_map = {}
    for node in nodes:
        node_id = node.get("id")
        if not node_id:
            errors.append("Each node must have an 'id' field")
            continue
        node_ids.add(node_id)
        node_map[node_id] = node

    if errors:
        return False, errors

    # Check 2: Missing node references in edges
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and source not in node_ids:
            errors.append(
                f"Edge references missing node '{source}': "
                f"no node with this ID exists in the workflow"
            )
        if target and target not in node_ids:
            errors.append(
                f"Edge references missing node '{target}': "
                f"no node with this ID exists in the workflow"
            )

    # Don't attempt cycle detection if edges reference missing nodes
    if errors:
        return False, errors

    # Check 1: Cycle detection
    deps = {node_id: set() for node_id in node_ids}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            deps[target].add(source)

    try:
        ts = graphlib.TopologicalSorter(deps)
        ts.prepare()
    except graphlib.CycleError as e:
        # Extract cycle from the error args
        # CycleError args[0] is a message string, args[1] is the cycle list
        cycle_nodes = []
        if e.args and len(e.args) > 1:
            cycle_nodes = list(e.args[1])
        if cycle_nodes:
            # Format: node-A -> node-B -> node-C -> node-A
            cycle_str = " -> ".join(cycle_nodes)
            errors.append(f"Cycle detected: {cycle_str}")
        else:
            errors.append(f"Graph contains a cycle: {e}")

    # Check 3: Invalid condition expressions
    for node in nodes:
        node_type = node.get("type", "")
        condition = node.get("condition") or node.get("data", {}).get("condition")
        if condition and node_type in ("condition", "branch", "conditional"):
            node_id = node.get("id", "unknown")
            # Check for dangerous constructs first
            if _has_dangerous_constructs(condition):
                errors.append(
                    f"Invalid condition expression in node '{node_id}': "
                    f"expression contains forbidden constructs"
                )
                continue
            # Validate syntax with ast.parse
            try:
                ast.parse(condition, mode="eval")
            except SyntaxError as se:
                col = se.offset or 0
                errors.append(
                    f"Invalid condition expression in node '{node_id}': SyntaxError at column {col}"
                )

    # Check 4: Unreachable nodes (warn only)
    nodes_with_incoming = set()
    nodes_with_outgoing = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source:
            nodes_with_outgoing.add(source)
        if target:
            nodes_with_incoming.add(target)

    for node_id in node_ids:
        if node_id not in nodes_with_incoming and node_id not in nodes_with_outgoing:
            if len(node_ids) > 1:  # Only warn if there are multiple nodes
                warnings.append(
                    f"WARNING: Node '{node_id}' is isolated (no incoming or outgoing edges)"
                )

    all_messages = errors + warnings
    is_valid = len(errors) == 0

    return is_valid, all_messages


def _has_dangerous_constructs(expression: str) -> bool:
    """Check if an expression contains dangerous constructs.

    Uses AST parsing to detect forbidden names/calls rather than simple
    string matching, to avoid false positives on substrings.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        # Will be caught by the syntax check above
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in DANGEROUS_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return True
        # Check for __import__ style calls
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in DANGEROUS_NAMES:
                return True
            if isinstance(func, ast.Attribute) and func.attr in DANGEROUS_NAMES:
                return True

    return False
