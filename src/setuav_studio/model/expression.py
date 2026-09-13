"""Expression evaluation engine for mathematical parameter relations."""

from __future__ import annotations

import ast
import math
import re
from typing import Any, Callable

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


def _get_dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        val = _get_dotted_name(node.value)
        if val:
            return f"{val}.{node.attr}"
    return None


def _is_standard_symbol_or_chain(name: str) -> bool:
    if name in STANDARD_SYMBOLS:
        return True
    return any(name.startswith(f"{f}.") for f in STANDARD_SYMBOLS)


class ExpressionEvaluator:
    """Evaluates mathematical expressions with variable substitution and error handling.

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

        symbols: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                name = node.id
                if not _is_standard_symbol_or_chain(name):
                    symbols.add(name)
            elif isinstance(node, ast.Attribute):
                dotted = _get_dotted_name(node)
                if dotted and not _is_standard_symbol_or_chain(dotted):
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


def rename_symbol_in_expression(
    expression: str,
    old_symbol: str,
    new_symbol: str,
) -> tuple[str, bool]:
    """Replace an identifier symbol or dotted symbol chain in a formula with a new symbol.

    Preserves formatting and validates syntax after substitution.
    """
    if not isinstance(expression, str) or not expression.strip():
        return expression, False
    old_clean = old_symbol.strip()
    new_clean = new_symbol.strip()
    if not old_clean or not new_clean or old_clean == new_clean:
        return expression, False

    pat = r"(?<![a-zA-Z0-9_.])" + re.escape(old_clean) + r"(?![a-zA-Z0-9_])"
    new_expr, n = re.subn(pat, new_clean, expression)
    if n > 0:
        clean = new_expr.lstrip("=").strip()
        try:
            ast.parse(clean, mode="eval")
            return new_expr, True
        except Exception:
            return expression, False
    return expression, False


def walk_expressions(
    obj: Any,
    callback: Callable[[str, str], str | None],
    path: str = "",
) -> int:
    """Recursively traverse a project dictionary and visit every expression string.

    Args:
        obj: Dictionary, list, or primitive to traverse.
        callback: Function receiving (expression_str, human_readable_location).
                  Should return the new expression string if modified, or None if unchanged.
        path: Dot-notated path for display / debugging.

    Returns:
        Total number of expressions modified by callback.
    """
    count = 0
    if isinstance(obj, dict):
        # 1. '_expressions' sub-dictionary
        if "_expressions" in obj and isinstance(obj["_expressions"], dict):
            for prop, expr in list(obj["_expressions"].items()):
                if isinstance(expr, str) and (
                    expr.strip().startswith("=")
                    or not expr.replace(".", "", 1).replace("-", "", 1).isdigit()
                ):
                    loc = f"{path} -> {prop}" if path else prop
                    res = callback(expr, loc)
                    if res is not None and res != expr:
                        obj["_expressions"][prop] = res
                        count += 1

        # 2. Iterate through dictionary items
        for k, v in list(obj.items()):
            if k == "_expressions":
                continue
            item_path = f"{path} -> {k}" if path else k
            if isinstance(v, str) and v.strip().startswith("="):
                res = callback(v, item_path)
                if res is not None and res != v:
                    obj[k] = res
                    count += 1
            elif isinstance(v, (dict, list)):
                sub_path = item_path
                if isinstance(v, dict) and ("name" in v or "id" in v):
                    name_tag = v.get("name") or v.get("id")
                    sub_path = f"{path} -> {name_tag}" if path else str(name_tag)
                count += walk_expressions(v, callback, sub_path)

    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            sub_path = f"{path}[{idx}]"
            if isinstance(item, dict) and ("name" in item or "id" in item):
                name_tag = item.get("name") or item.get("id")
                sub_path = f"{path} -> {name_tag}" if path else str(name_tag)
            if isinstance(item, (dict, list)):
                count += walk_expressions(item, callback, sub_path)

    return count


def rename_symbol_in_project(
    project_data: dict[str, Any],
    old_symbol: str,
    new_symbol: str,
) -> int:
    """Cascade rename a symbol (parameter or component identifier) across all expressions in the project.

    Returns the number of expressions updated.
    """
    if not isinstance(project_data, dict):
        return 0

    old_clean = old_symbol.replace("-", "_")
    new_clean = new_symbol.replace("-", "_")

    def _cb(expr: str, _loc: str) -> str | None:
        curr_expr = expr
        changed = False

        if old_symbol != old_clean:
            res_raw, ok_raw = rename_symbol_in_expression(curr_expr, old_symbol, new_clean)
            if ok_raw:
                curr_expr = res_raw
                changed = True

        res_clean, ok_clean = rename_symbol_in_expression(curr_expr, old_clean, new_clean)
        if ok_clean:
            curr_expr = res_clean
            changed = True

        return curr_expr if changed else None

    return walk_expressions(project_data, _cb)


def find_symbol_usages_in_project(
    project_data: dict[str, Any],
    symbol: str,
) -> list[tuple[str, str]]:
    """Scan the project for all expressions that reference the given parameter or component symbol.

    Returns:
        List of tuples: (human_readable_location, expression_string)
    """
    if not isinstance(project_data, dict) or not symbol.strip():
        return []

    evaluator = ExpressionEvaluator()
    clean_sym = symbol.strip().replace("-", "_")
    raw_sym = symbol.strip()
    usages: list[tuple[str, str]] = []

    def _inspect(expr: str, loc: str) -> str | None:
        try:
            symbols = evaluator.extract_symbols(expr)
        except Exception:
            symbols = set()

        is_used = False
        for s in symbols:
            parts = s.split(".")
            if clean_sym in parts or raw_sym in parts or s == clean_sym or s == raw_sym:
                is_used = True
                break
            if s.startswith(f"{clean_sym}.") or s.startswith(f"{clean_sym}_"):
                is_used = True
                break

        if is_used:
            usages.append((loc, expr))
        return None

    walk_expressions(project_data, _inspect)
    return usages

