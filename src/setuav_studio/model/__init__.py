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
    build_universal_scope,
    to_dot_dict,
)
from setuav_studio.model.symbol import (
    build_evaluation_context,
    create_model_for_component,
    get_available_symbols_metadata,
)
from setuav_studio.solver.base import SolverConfig

__all__ = [
    "Atmosphere",
    "Component",
    "ComponentMassProperties",
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
    "build_evaluation_context",
    "build_universal_scope",
    "create_model_for_component",
    "get_available_symbols_metadata",
    "get_expression",
    "set_expression",
    "to_dot_dict",
]
