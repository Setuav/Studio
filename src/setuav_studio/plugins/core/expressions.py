"""Expression evaluation engine for mathematical parameter relations."""

from __future__ import annotations

import ast
import math
from typing import Any

from asteval import Interpreter


class ExpressionEvaluationError(Exception):
    """Raised when expression evaluation fails."""


STANDARD_SYMBOLS: dict[str, Any] = {
    # Constants
    "pi": math.pi,
    "e": math.e,
    "g": 9.80665,
    # Trigonometry
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "radians": math.radians,
    "degrees": math.degrees,
    # Powers / Logs
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "log10": math.log10,
    "pow": pow,
    # Rounding / Basic math
    "abs": abs,
    "min": min,
    "max": max,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
}


class ExpressionEvaluator:
    """Evaluates mathematical expressions safely using asteval.

    Expressions start with '=' (e.g. '= sqrt(aspect_ratio * wing_area)').
    Standard math functions (sin, cos, sqrt, etc.) and constants (pi, e, g)
    are built-in.
    """

    def __init__(self) -> None:
        self._aeval = Interpreter(
            usersyms=dict(STANDARD_SYMBOLS),
            use_numpy=False,
            minimal=True,
            no_print=True,
            readonly_symbols=set(STANDARD_SYMBOLS.keys()),
        )

    @staticmethod
    def is_expression(value: Any) -> bool:
        """Check if a value represents a formula/expression starting with '='."""
        return isinstance(value, str) and value.strip().startswith("=")

    @staticmethod
    def strip_prefix(expression: str) -> str:
        """Remove leading '=' from expression string."""
        trimmed = expression.strip()
        if trimmed.startswith("="):
            return trimmed[1:].strip()
        return trimmed

    def extract_symbols(self, expression: str) -> set[str]:
        """Extract all variable identifier names and dotted attribute chains used in the expression.

        Standard functions and constants (such as 'sin', 'pi') are excluded.
        """
        raw_expr = self.strip_prefix(expression)
        if not raw_expr:
            return set()

        try:
            tree = ast.parse(raw_expr, mode="eval")
        except SyntaxError:
            return set()

        def _get_dotted_name(node: ast.AST) -> str | None:
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                val = _get_dotted_name(node.value)
                if val:
                    return f"{val}.{node.attr}"
            return None

        symbols: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                name = node.id
                if name not in STANDARD_SYMBOLS:
                    symbols.add(name)
            elif isinstance(node, ast.Attribute):
                dotted = _get_dotted_name(node)
                if dotted and not any(dotted.startswith(f"{f}.") for f in STANDARD_SYMBOLS):
                    symbols.add(dotted)
        return symbols

    def validate(self, expression: str) -> list[str]:
        """Validate expression syntax and return a list of error messages.

        Returns an empty list if the expression is syntactically valid.
        """
        raw_expr = self.strip_prefix(expression)
        if not raw_expr:
            return ["Expression cannot be empty."]

        try:
            ast.parse(raw_expr, mode="eval")
        except SyntaxError as exc:
            return [f"Syntax error at line {exc.lineno}, offset {exc.offset}: {exc.msg}"]

        return []

    def evaluate(self, expression: str, variables: dict[str, Any] | None = None) -> Any:
        """Evaluate an expression given a dictionary of variable values.

        Raises:
            ExpressionEvaluationError: If evaluation fails or syntax is invalid.
        """
        raw_expr = self.strip_prefix(expression)
        if not raw_expr:
            raise ExpressionEvaluationError("Expression is empty.")

        errors = self.validate(raw_expr)
        if errors:
            raise ExpressionEvaluationError("; ".join(errors))

        # Clear interpreter error state and set context variables
        self._aeval.error = []
        user_vars = variables or {}
        for var_name, var_val in user_vars.items():
            self._aeval.symtable[var_name] = var_val

        try:
            result = self._aeval(raw_expr)
            if self._aeval.error:
                err_msgs = [str(err.get_error()) for err in self._aeval.error]
                raise ExpressionEvaluationError("; ".join(err_msgs))
            return result
        except Exception as exc:
            if isinstance(exc, ExpressionEvaluationError):
                raise
            raise ExpressionEvaluationError(f"Failed to evaluate '{raw_expr}': {exc}") from exc
        finally:
            # Clean up user variables from interpreter symbol table
            for var_name in user_vars:
                self._aeval.symtable.pop(var_name, None)
