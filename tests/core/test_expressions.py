"""Unit tests for parametric expressions, dependency resolution, constraints, and universal scopes."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from setuav_studio.model.constraint import ConstraintChecker
from setuav_studio.model.expression import (
    ExpressionEvaluationError,
    ExpressionEvaluator,
    get_expression,
    set_expression,
)
from setuav_studio.model.parameter import (
    ParameterResolver,
)
from setuav_studio.model.scope import DotDict, to_dot_dict
from setuav_studio.model.symbol import get_available_symbols_metadata
from setuav_studio.project.document import (
    ProjectDocument,
    create_project,
    open_project,
    save_project,
)
from setuav_studio.project.evaluator import recompute_project_expressions

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


def test_evaluate_preserves_standard_symbols_when_shadowed() -> None:
    evaluator = ExpressionEvaluator()
    # User variable 'e' (e.g. Oswald efficiency) or 'g' shadows a built-in constant.
    assert math.isclose(evaluator.evaluate("= e * 2 + g", {"e": 0.85, "g": 2.0}), 3.7)
    # Subsequent evaluations on the same evaluator must still see built-in e and g.
    assert math.isclose(evaluator.evaluate("= e"), math.e)
    assert math.isclose(evaluator.evaluate("= g"), 9.80665)


# ==============================================================================
# 2. ParameterResolver & Dependency Graph Tests
# ==============================================================================


def test_resolve_scalars_only() -> None:
    resolver = ParameterResolver()
    params = {"aspect_ratio": 8.5, "wing_area": 0.85, "name": "TestWing"}
    resolution = resolver.resolve_all(params)
    assert resolution.values == params
    assert resolution.diagnostics == []


def test_resolve_derived_parameters() -> None:
    resolver = ParameterResolver()
    params = {
        "aspect_ratio": 8.0,
        "wing_area": 2.0,
        "wing_span": "= sqrt(aspect_ratio * wing_area)",
        "mean_chord": "= wing_area / wing_span",
    }
    resolved = resolver.resolve_all(params).values
    assert math.isclose(resolved["aspect_ratio"], 8.0)
    assert math.isclose(resolved["wing_area"], 2.0)
    assert math.isclose(resolved["wing_span"], 4.0)
    assert math.isclose(resolved["mean_chord"], 0.5)


def test_resolve_all_follows_dependencies() -> None:
    resolver = ParameterResolver()
    params = {
        "c": "= b * 2",
        "a": 10,
        "b": "= a + 5",
    }
    assert resolver.resolve_all(params).values == {"a": 10, "b": 15, "c": 30}


def test_detect_circular_dependency() -> None:
    resolver = ParameterResolver()
    params = {
        "a": "= b + 1",
        "b": "= a + 1",
    }
    cycles = resolver.detect_cycles(params)
    assert len(cycles) > 0


def test_resolve_all_reports_cycles_and_dependents() -> None:
    resolver = ParameterResolver()
    params = {
        "a": "= b + 1",
        "b": "= a + 1",
        "c": "= a * 2",
        "d": 4.0,
    }
    resolution = resolver.resolve_all(params)
    assert resolution.values == {"d": 4.0}
    messages = {d["path"]: d["message"] for d in resolution.diagnostics}
    assert messages["parameters.a"].startswith("Circular dependency")
    assert messages["parameters.b"].startswith("Circular dependency")
    assert messages["parameters.c"] == "Depends on invalid parameter 'a'"


def test_resolve_all_reports_failed_expression() -> None:
    resolver = ParameterResolver()
    params = {"bad": "= missing + 1", "uses_bad": "= bad * 2", "ok": "= 2 * 3"}
    resolution = resolver.resolve_all(params)
    assert resolution.values == {"ok": 6}
    assert [d["path"] for d in resolution.diagnostics] == [
        "parameters.bad",
        "parameters.uses_bad",
    ]
    assert resolution.diagnostics[0]["expression"] == "= missing + 1"


def test_evaluate_component_parameters(tmp_path: Path) -> None:
    proj = ProjectDocument(
        tmp_path / "test.json",
        "json",
        {
            "parameters": {
                "aspect_ratio": 8.0,
                "wing_area": 2.0,
                "wing_span": "= sqrt(aspect_ratio * wing_area)",
            },
            "components": [
                {
                    "id": "main-wing",
                    "name": "Main Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "parameters": {
                        "geometry": {
                            "span": 0.0,
                            "_expressions": {"span": "= wing_span * 1000"},
                            "profiles": [
                                {
                                    "chord": 0.0,
                                    "_expressions": {"chord": "= wing_span / 4 * 1000"},
                                    "position": 0.0,
                                },
                                {"chord": 200.0, "position": 1.0},
                            ],
                        },
                        "name": "Main Wing",
                    },
                }
            ],
        },
    )

    diagnostics = recompute_project_expressions(proj)
    assert diagnostics == []
    comp = proj.data["components"][0]
    geom = comp["parameters"]["geometry"]
    assert math.isclose(geom["span"], 4000.0)
    assert math.isclose(geom["profiles"][0]["chord"], 1000.0)
    assert geom["profiles"][1]["chord"] == 200.0


def test_evaluate_component_extensions_and_solver_configs(tmp_path: Path) -> None:
    proj = ProjectDocument(
        tmp_path / "test.json",
        "json",
        {
            "parameters": {"rod": 8.0, "cruise": 18.0},
            "components": [
                {
                    "id": "fuselage",
                    "type": "org.setuav.core:fuselage",
                    "parameters": {},
                    "extensions": {
                        "com.example.plugin": {
                            "spar": {"diameter": 0.0, "_expressions": {"diameter": "=rod + 2"}}
                        }
                    },
                }
            ],
            "solver_configs": {
                "cfg": {"parameters": {"airspeed": 0.0, "_expressions": {"airspeed": "=cruise"}}}
            },
        },
    )

    assert recompute_project_expressions(proj) == []
    extension = proj.data["components"][0]["extensions"]["com.example.plugin"]
    assert extension["spar"]["diameter"] == 10.0
    assert proj.data["solver_configs"]["cfg"]["parameters"]["airspeed"] == 18.0


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


def test_constraint_variables_map_to_project_numbers() -> None:
    checker = ConstraintChecker()
    project_data = {"parameters": {}, "limits": {"mass": 2.5, "label": "light"}}

    def constraint(path: str) -> dict[str, object]:
        return {
            "id": "c",
            "name": "Mass",
            "expression": "m < 3",
            "variables": {"m": path},
        }

    assert checker.check_constraint(constraint("limits.mass"), project_data).passed
    missing = checker.check_constraint(constraint("limits.weight"), project_data)
    assert not missing.passed
    assert "Variable 'm'" in missing.message
    text = checker.check_constraint(constraint("limits.label"), project_data)
    assert not text.passed
    assert "is not a number" in text.message


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
            "mass": 350.0,
            "parameters": {
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
    assert math.isclose(evaluator.evaluate("=main_wing.mass + battery.mass", scope), 850.0)

    # Symbol metadata completion
    symbols = get_available_symbols_metadata(proj)
    constant_keys = [c["key"] for c in symbols.get("constants", [])]
    component_ids = [c["id"] for c in symbols.get("components", [])]
    assert "b_ref" in constant_keys
    assert "c_ref" in constant_keys
    assert "main_wing" in component_ids
    assert "battery" in component_ids


def test_component_referencing_expression_evaluates_and_readers_use_stored_values(
    tmp_path: Path,
) -> None:
    from plugins.geometry.engine.scene import build_project_geometry

    proj = ProjectDocument(
        tmp_path / "component_ref.json",
        "json",
        {
            "parameters": {"wing_mass_base": 400.0},
            "components": [
                {
                    "id": "main-wing",
                    "name": "Main Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "mass": 120.0,
                    "_expressions": {"mass": "= wing_mass_base"},
                },
                {
                    "id": "ballast",
                    "name": "Ballast",
                    "type": "org.setuav.core:point-mass",
                    "mass": 10.0,
                    "_expressions": {"mass": "= main_wing.mass * 0.1"},
                },
            ],
        },
    )

    # Readers must read stored values directly without re-evaluating component expressions.
    scope_before = proj.get_scope()
    assert math.isclose(scope_before["ballast"].mass, 10.0)
    scene_before = build_project_geometry(proj, {})
    assert scene_before is not None

    diagnostics = recompute_project_expressions(proj)
    assert diagnostics == []
    assert math.isclose(proj.data["components"][0]["mass"], 400.0)
    assert math.isclose(proj.data["components"][1]["mass"], 40.0)

    scope_after = proj.get_scope()
    assert math.isclose(scope_after["ballast"].mass, 40.0)


def test_recompute_invalid_expression_produces_diagnostic_and_preserves_value(
    tmp_path: Path,
) -> None:
    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.editor import BaseComponentEditor
    from setuav_studio.ui.widget.table import ExpressionPropertyCell
    from tests._common import get_qapp

    get_qapp()
    proj = ProjectDocument(
        tmp_path / "invalid_expr.json",
        "json",
        {
            "components": [
                {
                    "id": "main-wing",
                    "name": "Main Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "mass": 250.0,
                    "_expressions": {"mass": "= missing_symbol * 2"},
                    "parameters": {
                        "geometry": {
                            "span": 1200.0,
                            "_expressions": {"span": "= unknown_var + 10"},
                        }
                    },
                }
            ]
        },
    )

    statuses: list[tuple[str, str, int]] = []
    api = StudioAPI()
    api._host.bind_status_handler(lambda msg, lvl, ms: statuses.append((msg, lvl, ms)))
    api._host.set_project(proj)

    diagnostics = api.recompute_project_expressions()
    assert len(diagnostics) == 2
    by_path = {d["path"]: d for d in diagnostics}
    assert by_path["mass"]["component_id"] == "main-wing"
    assert by_path["mass"]["expression"] == "= missing_symbol * 2"
    assert "missing_symbol" in by_path["mass"]["message"]
    assert by_path["parameters.geometry.span"]["expression"] == "= unknown_var + 10"

    # Last valid values remain untouched.
    assert math.isclose(proj.data["components"][0]["mass"], 250.0)
    assert math.isclose(proj.data["components"][0]["parameters"]["geometry"]["span"], 1200.0)

    # Diagnostic surfaced via API and status bar.
    assert api.expression_diagnostics == diagnostics
    assert any(lvl == "error" and "main-wing.mass" in msg for msg, lvl, _ in statuses)

    # Editor marks erroneous cell.
    editor = BaseComponentEditor(api, proj.data["components"][0])
    mass_cell = editor.general_table.cellWidget(2, 1)
    assert isinstance(mass_cell, ExpressionPropertyCell)
    assert mass_cell._has_error
    assert mass_cell.line_edit.text().startswith("#REF!")
    editor.deleteLater()


def test_invalid_global_parameter_is_reported_not_raised(tmp_path: Path) -> None:
    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input
    from tests._common import get_qapp

    get_qapp()
    project_file = tmp_path / "project.json"
    project_file.write_text(
        json.dumps(
            {
                "format_version": "1.0",
                "name": "Bad Global",
                "parameters": {"bad": "= missing_global_var + 1", "k": 0.5},
                "components": [
                    {"id": "a", "type": "x", "mass": 3.0, "_expressions": {"mass": "= bad * 2"}},
                    {"id": "b", "type": "x", "mass": 1.0, "_expressions": {"mass": "= k * 10"}},
                ],
            }
        ),
        encoding="utf-8",
    )
    proj = open_project(project_file)

    paths = [(d["component_id"], d["path"]) for d in proj.expression_diagnostics]
    assert paths == [("", "parameters.bad"), ("a", "mass")]
    assert proj.data["components"][0]["mass"] == 3.0
    assert proj.data["components"][1]["mass"] == 5.0

    save_project(proj)
    assert json.loads(project_file.read_text(encoding="utf-8"))["parameters"]["bad"] == (
        "= missing_global_var + 1"
    )

    api = StudioAPI()
    api._host.set_project(proj)
    assert evaluate_table_cell_input("5.0", api) == (5.0, None)
    assert evaluate_table_cell_input("= k * 4", api) == (2.0, "= k * 4")


def test_get_and_set_expression_helper() -> None:
    node: dict[str, object] = {"span": 1000.0}
    assert get_expression(node, "span") is None
    assert get_expression(None, "span") is None

    set_expression(node, "span", "  = b_ref * 1000 ")
    assert node["_expressions"] == {"span": "= b_ref * 1000"}
    assert get_expression(node, "span") == "= b_ref * 1000"

    set_expression(node, "chord", "= 200")
    set_expression(node, "dihedral", "wing_dihedral * 2")
    assert get_expression(node, "dihedral") == "=wing_dihedral * 2"

    set_expression(node, "span", None)
    assert get_expression(node, "span") is None
    assert node["_expressions"] == {"chord": "= 200", "dihedral": "=wing_dihedral * 2"}

    set_expression(node, "chord", "   ")
    set_expression(node, "dihedral", "")
    assert "_expressions" not in node
    assert get_expression(node, "chord") is None


def test_single_expression_detection_and_scientific_notation(tmp_path: Path) -> None:
    from setuav_studio.api import StudioAPI
    from setuav_studio.model.expression import (
        evaluate_numeric_input,
        normalize_equation_input,
    )
    from setuav_studio.ui.editor import BaseComponentEditor
    from setuav_studio.ui.editor.parameter import ParameterPropertyEditor
    from setuav_studio.ui.widget.spinbox import evaluate_table_cell_input
    from setuav_studio.ui.widget.table import ExpressionPropertyCell
    from tests._common import get_qapp

    get_qapp()

    # Scientific notation is parsed as a float, never as an expression.
    num_val, expr = evaluate_numeric_input("1e-3")
    assert math.isclose(num_val, 0.001)
    assert expr is None
    with pytest.raises(ValueError):
        evaluate_numeric_input("not_a_number")

    assert normalize_equation_input("1e-3") == "1e-3"
    assert normalize_equation_input("-5.5") == "-5.5"
    assert normalize_equation_input("b_ref * 2") == "=b_ref * 2"

    proj = ProjectDocument(
        tmp_path / "sci.json",
        "json",
        {
            "parameters": {"k": 1.0},
            "components": [
                {
                    "id": "wing-1",
                    "type": "org.setuav.core:lifting-surface",
                    "mass": 25.0,
                    "parameters": {},
                }
            ],
        },
    )
    statuses: list[tuple[str, str, int]] = []
    api = StudioAPI()
    api._host.bind_status_handler(lambda msg, lvl, ms: statuses.append((msg, lvl, ms)))
    api._host.set_project(proj)

    editor = BaseComponentEditor(api, proj.data["components"][0])
    mass_cell = editor._property_cell(editor.general_table, "mass")
    assert isinstance(mass_cell, ExpressionPropertyCell)
    assert not mass_cell._is_formula("1e-3")
    assert not mass_cell._is_formula("not_a_number")
    assert mass_cell._is_formula("=k * 2")

    assert evaluate_table_cell_input("1e-3", api, cell=mass_cell, label="Mass") == (0.001, None)
    editor._on_mass_changed("1e-3")
    assert math.isclose(proj.data["components"][0]["mass"], 0.001)
    assert get_expression(proj.data["components"][0], "mass") is None

    # Non-'=' non-float text produces a field error and preserves stored value.
    editor._on_mass_changed("bad_text")
    assert mass_cell._has_error
    assert math.isclose(proj.data["components"][0]["mass"], 0.001)
    assert get_expression(proj.data["components"][0], "mass") is None
    assert any(lvl == "error" for _, lvl, _ in statuses)
    editor.deleteLater()

    # ParameterPropertyEditor follows the same rule for global parameters.
    param_editor = ParameterPropertyEditor(api, {"key": "k"})
    param_editor._on_value_expression_changed("1e-3")
    assert math.isclose(proj.data["parameters"]["k"], 0.001)
    param_editor._on_value_expression_changed("bad_text")
    val_cell = param_editor._property_cell(param_editor.general_table, "value")
    assert isinstance(val_cell, ExpressionPropertyCell)
    assert val_cell._has_error
    assert math.isclose(proj.data["parameters"]["k"], 0.001)
    param_editor.deleteLater()


def test_recompute_reports_component_expression_cycle(tmp_path: Path) -> None:
    proj = ProjectDocument(
        tmp_path / "cycle.json",
        "json",
        {
            "parameters": {},
            "components": [
                {"id": "a", "type": "x", "mass": 1.0, "_expressions": {"mass": "= b.mass + 1"}},
                {"id": "b", "type": "x", "mass": 1.0, "_expressions": {"mass": "= a.mass + 1"}},
                {"id": "c", "type": "x", "mass": 0.0, "_expressions": {"mass": "= 2 * 3"}},
            ],
        },
    )
    diagnostics = recompute_project_expressions(proj)

    cycle = {
        (d["component_id"], d["path"]) for d in diagnostics if d["message"].startswith("Circular")
    }
    assert cycle == {("a", "mass"), ("b", "mass")}
    assert [c["mass"] for c in proj.data["components"]] == [1.0, 1.0, 6.0]
    assert proj.expression_diagnostics == diagnostics


def test_recompute_settles_long_chain_within_one_component(tmp_path: Path) -> None:
    proj = ProjectDocument(
        tmp_path / "chain.json",
        "json",
        {
            "parameters": {},
            "components": [
                {
                    "id": "a",
                    "type": "x",
                    "mass": 0.0,
                    "transform": {
                        "position": {
                            "x": 0.0,
                            "y": 0.0,
                            "z": 1.0,
                            "_expressions": {
                                "x": "= a.transform.position.y + 1",
                                "y": "= a.transform.position.z + 1",
                            },
                        }
                    },
                }
            ],
        },
    )
    assert recompute_project_expressions(proj) == []
    position = proj.data["components"][0]["transform"]["position"]
    assert (position["x"], position["y"]) == (3.0, 2.0)


def test_recompute_rejects_non_finite_expression_without_false_cycle(tmp_path: Path) -> None:
    proj = ProjectDocument(
        tmp_path / "nonfinite.json",
        "json",
        {
            "parameters": {},
            "components": [
                {
                    "id": "a",
                    "type": "x",
                    "mass": 5.0,
                    "_expressions": {"mass": "= 1e308 * 10"},
                }
            ],
        },
    )
    diagnostics = recompute_project_expressions(proj)
    assert len(diagnostics) == 1
    assert "finite" in diagnostics[0]["message"].lower()
    assert proj.data["components"][0]["mass"] == 5.0


def test_parameter_and_constraint_editors_follow_undo(tmp_path: Path) -> None:
    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.editor.constraint import (
        ConstraintExpressionCell,
        ConstraintPropertyEditor,
    )
    from setuav_studio.ui.editor.parameter import ParameterPropertyEditor
    from tests._common import get_qapp

    get_qapp()
    proj = ProjectDocument(
        tmp_path / "undo_editors.json",
        "json",
        {
            "parameters": {"k": 10.0, "other": 20.0},
            "constraints": [
                {
                    "id": "c1",
                    "name": "Min K",
                    "expression": "k >= 5",
                    "severity": "warning",
                    "enabled": True,
                }
            ],
            "components": [],
        },
    )
    api = StudioAPI()
    api._host.set_project(proj)

    param_editor = ParameterPropertyEditor(api, {"key": "k"})
    param_editor._on_value_expression_changed("25.0")
    assert proj.data["parameters"]["k"] == 25.0
    api.undo()
    assert proj.data["parameters"]["k"] == 10.0
    val_cell = param_editor._property_cell(param_editor.general_table, "value")
    assert val_cell is not None
    assert val_cell.value() == 10.0

    # Renaming onto an existing key must not overwrite it.
    name_item = param_editor.general_table.item(0, 1)
    assert name_item is not None
    name_item.setText("other")
    assert proj.data["parameters"]["other"] == 20.0
    assert "k" in proj.data["parameters"]
    param_editor.deleteLater()

    const_editor = ConstraintPropertyEditor(api, {"id": "c1"})
    const_editor._on_expression_changed("k >= 15")
    assert proj.data["constraints"][0]["expression"] == "k >= 15"
    api.undo()
    assert proj.data["constraints"][0]["expression"] == "k >= 5"
    expr_widget = const_editor.general_table.cellWidget(1, 1)
    assert isinstance(expr_widget, ConstraintExpressionCell)
    assert expr_widget.text() == "k >= 5"
    const_editor.deleteLater()


def test_parameter_rename_updates_selection_and_follows_undo_redo(tmp_path: Path) -> None:
    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.editor.parameter import ParameterPropertyEditor
    from setuav_studio.ui.panels.properties import PropertiesPanel
    from setuav_studio.ui.shell.native_registrations import register_native_kind_editors
    from tests._common import get_qapp

    get_qapp()
    proj = ProjectDocument(
        tmp_path / "rename_param.json",
        "json",
        {"parameters": {"k": 10.0}, "components": []},
    )
    api = StudioAPI()
    register_native_kind_editors(api)
    api._host.set_project(proj)

    panel = PropertiesPanel(api)
    initial_sel = {"kind": "parameter", "id": "param_k", "key": "k", "value": 10.0}
    api.set_selection(initial_sel)
    editor = panel._current_widget
    assert isinstance(editor, ParameterPropertyEditor)

    # Empty name restores original parameter name without modifying project data.
    name_item = editor.general_table.item(0, 1)
    assert name_item is not None
    name_item.setText("   ")
    assert name_item.text() == "k"
    assert "k" in proj.data["parameters"]

    # Valid rename updates project data, active selection, and supports undo/redo.
    name_item.setText("k_renamed")
    assert "k_renamed" in proj.data["parameters"]
    assert "k" not in proj.data["parameters"]
    assert api.current_selection is not None
    assert api.current_selection.get("id") == "param_k_renamed"
    assert api.current_selection.get("key") == "k_renamed"

    api.undo()
    assert "k" in proj.data["parameters"]
    assert "k_renamed" not in proj.data["parameters"]
    assert api.current_selection is not None
    assert api.current_selection.get("key") == "k"
    current_editor = panel._current_widget
    assert isinstance(current_editor, ParameterPropertyEditor)
    restored_name = current_editor.general_table.item(0, 1)
    assert restored_name is not None
    assert restored_name.text() == "k"

    api.redo()
    assert "k_renamed" in proj.data["parameters"]
    assert api.current_selection is not None
    assert api.current_selection.get("key") == "k_renamed"
    panel.deleteLater()


def test_parameter_stores_quantity_without_display_unit_and_formats_live(tmp_path: Path) -> None:
    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.editor.parameter import ParameterPropertyEditor
    from setuav_studio.ui.panels.project_explorer import ProjectExplorer
    from setuav_studio.units import get_unit_manager
    from tests._common import get_qapp

    get_qapp()
    um = get_unit_manager()
    um.set_active_preset("imperial")
    try:
        proj = ProjectDocument(
            tmp_path / "param_units.json",
            "json",
            {
                "parameters": {
                    "span": 254.0,
                    "legacy_len": {"value": 254.0, "unit": "mm"},
                },
                "components": [],
            },
        )
        api = StudioAPI()
        api._host.set_project(proj)

        editor = ParameterPropertyEditor(api, {"key": "span"})
        editor._on_quantity_changed("length")
        assert proj.data["parameters"]["span"] == {"value": 254.0, "quantity": "length"}
        assert "unit" not in proj.data["parameters"]["span"]

        # Editing in imperial writes base mm and omits the transient display unit symbol.
        editor._on_value_expression_changed("508.0")
        assert proj.data["parameters"]["span"] == {"value": 508.0, "quantity": "length"}
        assert editor._property_text(editor.general_table, 3) == "in"
        assert editor._property_text(editor.general_table, 4) == "20.0 in"
        editor.deleteLater()

        # Legacy entries with only "unit" resolve their quantity and show active display units.
        legacy_editor = ParameterPropertyEditor(api, {"key": "legacy_len"})
        assert legacy_editor._current_quantity == "length"
        assert legacy_editor._property_text(legacy_editor.general_table, 3) == "in"
        assert legacy_editor._property_text(legacy_editor.general_table, 4) == "10.0 in"
        legacy_editor.deleteLater()

        # Formula metadata exposes base-unit symbol matching the evaluated scope value.
        meta = get_available_symbols_metadata(proj, api=api)
        by_key = {c["key"]: c for c in meta["constants"]}
        assert by_key["span"]["value"] == 508.0
        assert by_key["span"]["unit"] == "mm"
        assert by_key["legacy_len"]["unit"] == "mm"

        # Project Explorer tooltip formats constants in the active display unit and tracks changes.
        tree = ProjectExplorer(api)
        span_item = tree._item_map["param_span"]
        assert "20.0 in" in span_item.toolTip(0)
        um.set_active_preset("si")
        um.units_changed.emit()
        span_item = tree._item_map["param_span"]
        assert "508.0 mm" in span_item.toolTip(0)
        tree.deleteLater()
    finally:
        um.set_active_preset("si")


def test_expression_cell_preserves_raw_float_precision_across_unit_switches() -> None:
    from PySide6.QtWidgets import QTableWidget

    from setuav_studio.ui.widget.spinbox import set_table_spinbox
    from setuav_studio.units import get_unit_manager
    from tests._common import get_qapp

    get_qapp()
    um = get_unit_manager()
    um.set_active_preset("si")
    changes: list[str] = []
    try:
        table = QTableWidget(1, 1)
        exact_mm = 123.45678
        cell = set_table_spinbox(
            table,
            0,
            0,
            exact_mm,
            quantity="length",
            decimals=2,
            on_changed=lambda v: changes.append(v),
            api=None,
        )

        # Idle display rounds visually, while stored float keeps full precision.
        assert cell.line_edit.text() == "123.46"
        assert cell.value() == pytest.approx(exact_mm)
        assert cell.stored_expression() is None

        # Switching units converts from full-precision base value without drift
        # (123.45678 / 25.4 = 4.860503..., whereas pre-rounded 123.46 / 25.4 would be 4.8606).
        um.set_active_preset("imperial")
        um.units_changed.emit()
        assert cell.value() == pytest.approx(exact_mm)
        assert cell.line_edit.text() == "4.8605"

        um.set_active_preset("si")
        um.units_changed.emit()
        assert cell.value() == pytest.approx(exact_mm)
        assert cell.line_edit.text() == "123.46"

        # Focusing in and out without editing must not emit a change or truncate precision.
        cell._on_focus_in()
        cell._on_focus_out()
        assert changes == []
        assert cell.value() == pytest.approx(exact_mm)
        table.deleteLater()
    finally:
        um.set_active_preset("si")


def test_expression_cell_shows_base_unit_badge_while_editing_formula(tmp_path: Path) -> None:
    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.dialog.expression_dialog import AdvancedExpressionDialog
    from setuav_studio.ui.widget.table import ExpressionPropertyCell
    from setuav_studio.units import get_unit_manager
    from tests._common import get_qapp

    get_qapp()
    um = get_unit_manager()
    um.set_active_preset("imperial")
    try:
        proj = ProjectDocument(
            tmp_path / "formula_badge.json",
            "json",
            {"parameters": {"span": {"value": 254.0, "quantity": "length"}}, "components": []},
        )
        api = StudioAPI()
        api._host.set_project(proj)

        cell = ExpressionPropertyCell(
            initial_value="= span",
            api=api,
            quantity="length",
            decimals=2,
        )

        # Idle display converts base mm (254) to active display unit (10 in).
        assert cell.line_edit.text() == "10.0"
        assert cell.unit_label.text() == "in"
        assert cell.unit_label.toolTip() == ""

        # Focusing into a formula switches the badge to the base unit (mm) with tooltip.
        cell._on_focus_in()
        assert cell.line_edit.text() == "= span"
        assert cell.unit_label.text() == "mm"
        assert "mm" in cell.unit_label.toolTip()

        # Deleting '=' returns to plain-number display unit entry; re-typing '=' switches back to base unit.
        cell.line_edit.setText("10")
        assert cell.unit_label.text() == "in"
        assert cell.unit_label.toolTip() == ""

        cell.line_edit.setText("= span * 2")
        assert cell.unit_label.text() == "mm"
        assert "mm" in cell.unit_label.toolTip()

        # Focusing out restores the active display unit badge with converted evaluated value.
        cell._on_focus_out()
        assert cell.unit_label.text() == "in"
        assert cell.line_edit.text() == "20.0"
        cell.deleteLater()

        # AdvancedExpressionDialog shows the target base unit on the numeric result preview.
        dlg = AdvancedExpressionDialog(api, initial_expression="= span", result_unit="mm")
        assert "254 mm" in dlg.preview_label.text()
        dlg.deleteLater()
    finally:
        um.set_active_preset("si")


def test_global_parameters_share_universal_scope_and_hyphen_aliases(tmp_path: Path) -> None:
    from setuav_studio.api import StudioAPI
    from setuav_studio.ui.editor.parameter import ParameterPropertyEditor
    from tests._common import get_qapp

    get_qapp()
    proj = ProjectDocument(
        tmp_path / "unified_scope.json",
        "json",
        {
            "parameters": {
                "wing-span": 2000.0,
                "half_span": "= wing_span / 2",
                "wing_mass_ratio": "= main_wing.mass / total_mass",
            },
            "components": [
                {
                    "id": "main-wing",
                    "name": "Main Wing",
                    "type": "org.setuav.core:lifting-surface",
                    "mass": 400.0,
                },
                {
                    "id": "battery",
                    "name": "Battery",
                    "type": "org.setuav.core:battery",
                    "mass": 300.0,
                },
                {
                    "id": "battery-2",
                    "name": "Battery Copy",
                    "kind": "instance",
                    "source": "battery",
                },
                {
                    "id": "ballast",
                    "name": "Ballast",
                    "type": "org.setuav.core:point-mass",
                    "mass": 0.0,
                    "_expressions": {"mass": "= half_span / 10"},
                },
            ],
        },
    )
    api = StudioAPI()
    api._host.set_project(proj)

    # Instance battery-2 contributes 300 g just like mass_balance.py:
    # main-wing (400) + battery (300) + battery-2 (300) + ballast (100) = 1100 g.
    scope = proj.get_scope(api=api)
    assert math.isclose(scope["half_span"], 1000.0)
    assert math.isclose(proj.data["components"][3]["mass"], 100.0)
    assert math.isclose(scope["total_mass"], 1100.0)
    assert math.isclose(scope["total_mass"], proj.mass_properties.mass_kg * 1000.0, rel_tol=1e-6)
    assert math.isclose(scope["wing_mass_ratio"], 400.0 / 1100.0)
    assert api.expression_diagnostics == []

    # ParameterPropertyEditor accepts component & total_mass formulas cleanly.
    editor = ParameterPropertyEditor(api, {"key": "wing_mass_ratio"})
    editor._on_value_expression_changed("= main_wing.mass / total_mass")
    assert proj.data["parameters"]["wing_mass_ratio"] == "= main_wing.mass / total_mass"
    assert not editor._property_cell(editor.general_table, "value")._has_error  # type: ignore[union-attr]
    editor.deleteLater()

    # Parameter <-> component cycle is detected and rolled back.
    proj.data["parameters"]["loop_p"] = "= ballast.mass + 1"
    proj.data["components"][3]["_expressions"]["mass"] = "= loop_p + 1"
    before_mass = proj.data["components"][3]["mass"]
    diagnostics = recompute_project_expressions(proj, api=api)
    assert any("Circular" in d["message"] for d in diagnostics)
    assert proj.data["components"][3]["mass"] == before_mass
