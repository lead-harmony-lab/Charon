from unittest.mock import patch

import pytest

from charon.tools.math import safe_eval_math


class TestSafeEvalMath:
    @pytest.mark.parametrize("expression, expected", [
        # Basic arithmetic
        ("2 + 2", 4),
        ("10.5 - 3.2", 7.3),
        ("4 * 5", 20),
        ("10 / 4", 2.5),

        # Advanced operators
        ("10 // 3", 3),
        ("10 % 3", 1),
        ("2 ** 3", 8),

        # Test replacement of ^ with **
        ("2 ^ 3", 8),
        ("2 ^ 3 ^ 2", 512),  # Right-associative exponentiation (2 ** (3 ** 2))

        # Unary operators
        ("-5", -5),
        ("+5", 5),
        ("-(3 + 2)", -5),
        ("5 + -3", 2),

        # Complex nested expressions and whitespace
        ("(5 + 5) * 2 / 10", 2.0),
        ("  2 + 2  ", 4),
    ])
    def test_safe_eval_math_success(self, expression, expected):
        """Test valid mathematical expressions that should be evaluated successfully."""
        result = safe_eval_math(expression)
        assert result == pytest.approx(expected)

    @pytest.mark.parametrize("expression", [
        # Syntax Errors and Math Errors
        ("1 / 0"),  # ZeroDivisionError
        ("2 + "),  # SyntaxError
        ("2 * * 3"),  # SyntaxError

        # Disallowed AST Nodes (Names, Attributes, Calls)
        ("x + 2"),  # Variables (ast.Name is not in allowed_nodes)
        ("math.pi"),  # (ast.Attribute and ast.Name are not allowed)
        ("abs(-5)"),  # Function calls (ast.Call is not allowed)

        # Malicious code injection attempts
        ("__import__('os').system('ls')"),
        ("eval('2 + 2')"),
        ("exec('a=2')"),

        # Non-numeric valid AST nodes
        ("'hello'"),  # Parses as ast.Constant, but returns a string (fails int/float check)
        ("True"),  # Parses as ast.Constant (rejected at AST level)
        ("[1, 2 + 3]"),  # Lists (ast.List is not allowed)
        ("{'a': 1}"),  # Dictionaries (ast.Dict is not allowed)
    ])
    def test_safe_eval_math_invalid_and_unsafe(self, expression):
        """Test invalid, unsafe, or unsupported expressions which should safely return None."""
        assert safe_eval_math(expression) is None

    def test_safe_eval_math_boolean_result_guard(self):
        """Triggers line 43 by mocking eval to return a boolean value."""
        with patch("charon.tools.math.eval", return_value=True):
            assert safe_eval_math("1 + 1") is None
