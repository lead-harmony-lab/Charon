"""
charon/tools/math.py
System Version: v0.1.0 | File Revision: 1.0.0

Module: Safe AST Mathematical Evaluation Tools.
"""

import ast
import math
from typing import Optional, Union


def safe_eval_math(expr: str) -> Optional[Union[int, float]]:
    """Safely evaluates pure arithmetic expressions using Python AST parsing."""
    try:
        clean_expr = expr.replace("^", "**").strip()
        node = ast.parse(clean_expr, mode="eval")

        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Constant,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.FloorDiv,
            ast.Mod,
            ast.Pow,
            ast.USub,
            ast.UAdd,
        )

        for subnode in ast.walk(node):
            if not isinstance(subnode, allowed_nodes):
                return None
            # Explicitly reject boolean constants during AST traversal
            if isinstance(subnode, ast.Constant) and isinstance(subnode.value, bool):
                return None

        code = compile(node, "<string>", "eval")
        result = eval(code, {"__builtins__": None, "math": math}, {})

        # Python evaluates isinstance(True, int) as True.
        # We must explicitly exclude bools before checking for int/float.
        if isinstance(result, bool):
            return None

        if isinstance(result, (int, float)):
            return result
    except Exception:
        return None
    return None
