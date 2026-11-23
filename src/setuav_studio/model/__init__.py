"""Core Vehicle, System, Component, State, and Parameter Models (Pure Python)."""

from __future__ import annotations

from setuav_studio.model.atmosphere import Atmosphere
from setuav_studio.model.component import (
    Component,
    GenericComponent,
)
from setuav_studio.model.constraint import (
    ConstraintChecker,
    ConstraintResult,
)
from setuav_studio.model.environment import Environment
from setuav_studio.model.expression import (
    ExpressionEvaluationError,
    ExpressionEvaluator,
    get_expression,
    rewrite_project_expression_identifiers,
    rewrite_root_identifiers,
    set_expression,
)
from setuav_studio.model.mass import (
    ComponentMassProperties,
    InertiaTensor,
    MassProperties,
    Vector3,
)
from setuav_studio.model.parameter import (
    ParameterResolution,
    ParameterResolver,
)
from setuav_studio.model.scope import (
    DotDict,
    build_project_base_scope,
    build_universal_scope,
    build_universal_scope_with_diagnostics,
    to_dot_dict,
)
from setuav_studio.model.symbol import (
    ComponentSymbolMap,
    build_component_symbol_map,
    build_evaluation_context,
    create_model_for_component,
    get_available_symbols_metadata,
    slugify_identifier,
)
from setuav_studio.solver.base import SolverConfig

__all__ = [
    "Atmosphere",
    "Component",
    "ComponentMassProperties",
    "ComponentSymbolMap",
    "ConstraintChecker",
    "ConstraintResult",
    "DotDict",
    "Environment",
    "ExpressionEvaluationError",
    "ExpressionEvaluator",
    "GenericComponent",
    "InertiaTensor",
    "MassProperties",
    "ParameterResolution",
    "ParameterResolver",
    "SolverConfig",
    "Vector3",
    "build_component_symbol_map",
    "build_evaluation_context",
    "build_project_base_scope",
    "build_universal_scope",
    "build_universal_scope_with_diagnostics",
    "create_model_for_component",
    "get_available_symbols_metadata",
    "get_expression",
    "rewrite_project_expression_identifiers",
    "rewrite_root_identifiers",
    "set_expression",
    "slugify_identifier",
    "to_dot_dict",
]
