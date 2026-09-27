"""Unit tests for parametric expressions, dependency resolution, constraints, and universal scopes."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from setuav_studio.model.constraint import ConstraintChecker
from setuav_studio.model.expression import (
    ExpressionEvaluationError,
    ExpressionEvaluator,
)
from setuav_studio.model.parameter import (
    CircularDependencyError,
    ParameterResolver,
)
from setuav_studio.model.scope import DotDict, to_dot_dict
from setuav_studio.model.symbol import get_available_symbols_metadata
from setuav_studio.project.document import create_project

# ==============================================================================
# 1. ExpressionEvaluator Tests
# ==============================================================================


def test_is_expression() -> None:
    evaluator = ExpressionEvaluator()
    assert evaluator.is_expression("= 2 + 2")
    assert evaluator.is_expression("=sqrt(16)")
    assert not evaluator.is_expression("2 + 2")
    assert not evaluator.is_expression(123)
    assert not evaluator.is_expression(None)


def test_strip_prefix() -> None:
    evaluator = ExpressionEvaluator()
    assert evaluator.strip_prefix("= 2 + 2") == "2 + 2"
    assert evaluator.strip_prefix("=sqrt(16)") == "sqrt(16)"
    assert evaluator.strip_prefix("100") == "100"


def test_basic_arithmetic() -> None:
    evaluator = ExpressionEvaluator()
    assert evaluator.evaluate("= 2 + 3 * 4") == 14
    assert math.isclose(evaluator.evaluate("= 10 / 4"), 2.5)
    assert evaluator.evaluate("= 2 ** 3") == 8


def test_built_in_math_functions_and_constants() -> None:
    evaluator = ExpressionEvaluator()
    assert math.isclose(evaluator.evaluate("= sqrt(16)"), 4.0)
    assert math.isclose(evaluator.evaluate("= sin(pi / 2)"), 1.0)
    assert math.isclose(evaluator.evaluate("= cos(0)"), 1.0)
    assert math.isclose(evaluator.evaluate("= g"), 9.80665)
    assert math.isclose(evaluator.evaluate("= radians(180)"), math.pi)


def test_variables_substitution() -> None:
    evaluator = ExpressionEvaluator()
    vars_dict = {"aspect_ratio": 8.0, "wing_area": 2.0}
    res = evaluator.evaluate("= sqrt(aspect_ratio * wing_area)", vars_dict)
    assert math.isclose(res, 4.0)


def test_extract_symbols() -> None:
    evaluator = ExpressionEvaluator()
    symbols = evaluator.extract_symbols("= sqrt(aspect_ratio * wing_area) + pi + sin(alpha)")
    assert symbols == {"aspect_ratio", "wing_area", "alpha"}


def test_syntax_validation() -> None:
    evaluator = ExpressionEvaluator()
    assert evaluator.validate("= 2 + 2") == []
    assert evaluator.validate("") == ["Expression cannot be empty."]
    errors = evaluator.validate("= 2 +")
    assert len(errors) > 0


def test_evaluation_error_on_unknown_variable() -> None:
    evaluator = ExpressionEvaluator()
    with pytest.raises(ExpressionEvaluationError):
        evaluator.evaluate("= unknown_variable * 2")


# ==============================================================================
# 2. ParameterResolver & Dependency Graph Tests
# ==============================================================================


def test_resolve_scalars_only() -> None:
    resolver = ParameterResolver()
    params = {"aspect_ratio": 8.5, "wing_area": 0.85, "name": "TestWing"}
    resolved = resolver.resolve_all(params)
    assert resolved == params


def test_resolve_derived_parameters() -> None:
    resolver = ParameterResolver()
    params = {
        "aspect_ratio": 8.0,
        "wing_area": 2.0,
        "wing_span": "= sqrt(aspect_ratio * wing_area)",
        "mean_chord": "= wing_area / wing_span",
    }
    resolved = resolver.resolve_all(params)
    assert math.isclose(resolved["aspect_ratio"], 8.0)
    assert math.isclose(resolved["wing_area"], 2.0)
    assert math.isclose(resolved["wing_span"], 4.0)
    assert math.isclose(resolved["mean_chord"], 0.5)


def test_evaluation_order() -> None:
    resolver = ParameterResolver()
    params = {
        "c": "= b * 2",
        "a": 10,
        "b": "= a + 5",
    }
    order = resolver.get_evaluation_order(params)
    assert order == ["a", "b", "c"]
    resolved = resolver.resolve_all(params)
    assert resolved == {"a": 10, "b": 15, "c": 30}


def test_detect_circular_dependency() -> None:
    resolver = ParameterResolver()
    params = {
        "a": "= b + 1",
        "b": "= a + 1",
    }
    cycles = resolver.detect_cycles(params)
    assert len(cycles) > 0
    with pytest.raises(CircularDependencyError):
        resolver.resolve_all(params)


def test_get_dependents() -> None:
    resolver = ParameterResolver()
    params = {
        "a": 10,
        "b": "= a * 2",
        "c": "= b + 5",
        "d": 20,
    }
    deps_of_a = resolver.get_dependents(params, "a")
    assert deps_of_a == {"b", "c"}
    assert resolver.get_dependents(params, "d") == set()


def test_evaluate_component_parameters() -> None:
    resolver = ParameterResolver()
    project_params = {
        "aspect_ratio": 8.0,
        "wing_area": 2.0,
        "wing_span": "= sqrt(aspect_ratio * wing_area)",
    }
    resolved_project = resolver.resolve_all(project_params)

    component_params = {
        "geometry": {
            "span": "= wing_span * 1000",
            "profiles": [
                {"chord": "= wing_span / 4 * 1000", "position": 0.0},
                {"chord": 200.0, "position": 1.0},
            ],
        },
        "name": "Main Wing",
    }

    evaluated = resolver.evaluate_component_parameters(component_params, resolved_project)
    assert evaluated["name"] == "Main Wing"
    assert math.isclose(evaluated["geometry"]["span"], 4000.0)
    assert math.isclose(evaluated["geometry"]["profiles"][0]["chord"], 1000.0)
    assert evaluated["geometry"]["profiles"][1]["chord"] == 200.0


# ==============================================================================
# 3. Design Constraints Checker Tests
# ==============================================================================


def test_evaluate_constraints() -> None:
    checker = ConstraintChecker()
    project_data = {
        "parameters": {
            "aspect_ratio": 8.0,
            "wing_area": 2.0,
            "mtow": 50.0,
        },
        "constraints": [
            {
                "id": "c1",
                "name": "Wing Loading Limit",
                "expression": "mtow / wing_area <= 30",
                "severity": "warning",
                "enabled": True,
            },
            {
                "id": "c2",
                "name": "Aspect Ratio Minimum",
                "expression": "aspect_ratio >= 6.0",
                "severity": "error",
                "enabled": True,
            },
            {
                "id": "c3",
                "name": "Disabled Rule",
                "expression": "mtow < 10",
                "enabled": False,
            },
        ],
    }
    results = checker.check_all(project_data)
    assert len(results) == 3

    # c1: 50 / 2 = 25 <= 30 -> True
    assert results[0].passed
    assert results[0].id == "c1"
    assert math.isclose(results[0].resolved_values.get("mtow", 0.0), 50.0)

    # c2: 8.0 >= 6.0 -> True
    assert results[1].passed

    # c3: disabled -> passed=True, enabled=False
    assert results[2].passed
    assert not results[2].enabled


def test_violated_constraint() -> None:
    checker = ConstraintChecker()
    project_data = {
        "parameters": {
            "aspect_ratio": 8.0,
            "wing_area": 2.0,
            "mtow": 80.0,
        },
        "constraints": [
            {
                "id": "c1",
                "name": "Wing Loading Limit",
                "expression": "mtow / wing_area <= 30",
                "enabled": True,
            }
        ],
    }
    results = checker.check_all(project_data)
    assert not results[0].passed
    assert "Wing Loading Limit" in results[0].name


def test_constraint_syntax_or_unknown_variable() -> None:
    checker = ConstraintChecker()
    bad_constraint = {
        "id": "bad",
        "name": "Bad Expression",
        "expression": "unknown_var > 10",
        "enabled": True,
    }
    res = checker.check_constraint(bad_constraint, {"parameters": {}})
    assert not res.passed
    assert res.error is not None


# ==============================================================================
# 4. Universal Hierarchical Scope Tests
# ==============================================================================


def test_dot_dict_primitives_and_wrappers() -> None:
    assert to_dot_dict(42) == 42
    assert to_dot_dict(3.14) == 3.14
    assert to_dot_dict("hello") == "hello"
    assert to_dot_dict(None) is None

    d = to_dot_dict({"foo": {"bar": 100}})
    assert isinstance(d, DotDict)
    assert d.foo.bar == 100
    assert d["foo"]["bar"] == 100


def test_hierarchical_json_scope_access(tmp_path: Path) -> None:
    evaluator = ExpressionEvaluator()
    proj = create_project(tmp_path / "test.suav")
    proj.data["parameters"] = {
        "b_ref": 2000.0,
        "c_ref": 200.0,
    }
    proj.data["components"] = [
        {
            "id": "main-wing",
            "name": "Main Wing",
            "type": "org.setuav.core:lifting-surface",
            "parameters": {
                "mass": 350.0,
                "geometry": {
                    "span": 2000.0,
                },
            },
        },
        {
            "id": "battery",
            "name": "LiPo Battery",
            "mass": 500.0,
            "parameters": {
                "capacity_mah": 5000.0,
            },
        },
    ]

    scope = proj.get_scope()
    assert scope is not None

    # Access parameters directly
    assert math.isclose(evaluator.evaluate("=b_ref / 2", scope), 1000.0)

    # Access components via dotted path
    assert math.isclose(
        evaluator.evaluate("=main_wing.parameters.mass + battery.mass", scope), 850.0
    )

    # Symbol metadata completion
    symbols = get_available_symbols_metadata(proj)
    constant_keys = [c["key"] for c in symbols.get("constants", [])]
    component_ids = [c["id"] for c in symbols.get("components", [])]
    assert "b_ref" in constant_keys
    assert "c_ref" in constant_keys
    assert "main_wing" in component_ids
    assert "battery" in component_ids
