"""Deterministic mass, centre-of-gravity, and inertia aggregation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from setuav_studio.plugins.core.derived_geometry import (
    DerivedComponentGeometry,
    derive_project_component_geometry,
)
from setuav_studio.project import ProjectDocument

from ..models import (
    ComponentMassProperties,
    InertiaTensor,
    MassProperties,
    Vector3,
    WeightBalanceResult,
)
from .base import WeightBalanceEngine, WeightBalanceError
from .spatial import Matrix3, TransformError, resolve_world_transforms

EXTENSION_ID = "org.setuav.weight-balance"
PHYSICAL_EXTENSION_ID = "org.setuav.core.physical"


class WeightBalanceSolver(WeightBalanceEngine):
    """Aggregate component mass properties in the SETUAV_BODY frame.

    Persisted component positions are millimetres and masses are grams. Solver
    results use metres, kilograms, and kg*m^2.
    """

    def evaluate(
        self,
        project: ProjectDocument,
    ) -> WeightBalanceResult:
        raw_components = project.data.get("components")
        components = (
            [item for item in raw_components if isinstance(item, dict)]
            if isinstance(raw_components, list)
            else []
        )
        by_id = {
            str(component["id"]): component
            for component in components
            if isinstance(component.get("id"), str)
        }
        if not by_id:
            raise WeightBalanceError("Project has no components to analyse")

        try:
            transforms = resolve_world_transforms(components)
        except TransformError as exc:
            raise WeightBalanceError(str(exc)) from exc

        result_components: list[ComponentMassProperties] = []
        warnings: list[str] = []
        derived = derive_project_component_geometry(list(by_id.values()))
        for component_id, component in by_id.items():
            effective = self._effective_component(component, by_id)
            if effective.get("type") == "org.setuav.core:control-surface":
                # Control surfaces are part of the parent lifting surface's
                # single mass item. Their geometry remains available to the
                # 2D/3D views, but they do not become separate WB masses.
                continue
            item = self._component_properties(
                component_id,
                effective,
                transforms[component_id].point_mm_to_m,
                derived.get(component_id),
                mirrored_frame=_mirrored_frame(effective, by_id),
            )
            if item is None:
                warnings.append(f"{component_id}: mass is missing; component excluded")
                continue
            result_components.append(item)
            warnings.extend(f"{component_id}: {message}" for message in item.warnings)

        if not result_components:
            raise WeightBalanceError("Project has no components with positive mass")

        total_mass = sum(item.mass_kg for item in result_components)
        if total_mass <= 0.0:
            raise WeightBalanceError("Total aircraft mass must be greater than zero")

        cg: Vector3 = tuple(
            sum(item.mass_kg * item.cg_body_m[axis] for item in result_components) / total_mass
            for axis in range(3)
        )  # type: ignore[assignment]

        inertia = _zero_matrix()
        for item in result_components:
            rotation = transforms[item.component_id].rotation
            local_matrix = item.inertia_local_kg_m2.as_matrix()
            body_matrix = _matmul(_matmul(rotation, local_matrix), _transpose(rotation))
            offset = tuple(item.cg_body_m[index] - cg[index] for index in range(3))
            inertia = _add_matrix(
                inertia,
                _add_matrix(body_matrix, _parallel_axis(item.mass_kg, offset)),
            )

        return WeightBalanceResult(
            total=MassProperties(
                mass_kg=total_mass,
                cg_body_m=cg,
                inertia_cg_kg_m2=InertiaTensor.from_matrix(inertia),
            ),
            components=result_components,
            warnings=warnings,
        )

    @staticmethod
    def _effective_component(
        component: dict[str, Any],
        by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        if component.get("kind") != "instance":
            return deepcopy(component)
        source = by_id.get(str(component.get("source") or ""))
        if source is None:
            return deepcopy(component)
        effective = deepcopy(source)
        for key in ("id", "name", "kind", "source", "parent", "attach_to", "derivation"):
            if key in component:
                effective[key] = deepcopy(component[key])
        if "mass" in component:
            effective["mass"] = component["mass"]
        overrides = component.get("parameter_overrides")
        if isinstance(overrides, dict):
            parameters = effective.setdefault("parameters", {})
            if isinstance(parameters, dict):
                _deep_merge(parameters, overrides)
        instance_extensions = component.get("extensions")
        if isinstance(instance_extensions, dict):
            target = effective.setdefault("extensions", {})
            if isinstance(target, dict):
                _deep_merge(target, instance_extensions)
        return effective

    def _component_properties(
        self,
        component_id: str,
        component: dict[str, Any],
        transform_point_mm: Any,
        derived: DerivedComponentGeometry | None = None,
        *,
        mirrored_frame: bool = False,
    ) -> ComponentMassProperties | None:
        parameters = component.get("parameters")
        parameters = parameters if isinstance(parameters, dict) else {}
        extensions = component.get("extensions")
        extensions = extensions if isinstance(extensions, dict) else {}
        wb_extension = extensions.get(EXTENSION_ID)
        wb_extension = wb_extension if isinstance(wb_extension, dict) else {}
        physical_extension = extensions.get(PHYSICAL_EXTENSION_ID)
        physical_extension = physical_extension if isinstance(physical_extension, dict) else {}
        physical_envelope = physical_extension.get("envelope")
        physical_envelope = physical_envelope if isinstance(physical_envelope, dict) else None

        component_warnings: list[str] = []
        root_mass = _optional_number(component.get("mass"))
        parameter_mass = _optional_number(parameters.get("mass"))
        if (
            root_mass is not None
            and parameter_mass is not None
            and abs(root_mass - parameter_mass) > 1e-6
        ):
            component_warnings.append(
                f"component.mass ({root_mass:g} g) overrides parameters.mass ({parameter_mass:g} g)"
            )

        mass_g = root_mass if root_mass is not None else parameter_mass
        requested_source = str(wb_extension.get("mass_source") or "")
        if derived is not None and (
            mass_g is None or mass_g <= 0.0 or requested_source == "derived"
        ):
            mass_g = derived.mass_g
            source = "derived"
        else:
            source = requested_source or ("declared" if mass_g is not None else "missing")
        if mass_g is None or mass_g <= 0.0:
            return None

        # A derived mass source also owns the default CG/inertia.  This is
        # important for control surfaces created with a placeholder
        # ``local_cg_mm: {0, 0, 0}``; that placeholder must not mask the
        # geometry-derived hinge-bay centre.
        cg_value = None if source == "derived" else wb_extension.get("local_cg_mm")
        has_declared_cg = isinstance(cg_value, dict)
        if not has_declared_cg and derived is not None:
            # Use the envelope centre for structural geometry.  A control
            # surface has its centre represented by a derived local transform
            # when its transform is implicit.
            if component.get("type") == "org.setuav.core:control-surface":
                transform_value = component.get("transform")
                has_transform_position = isinstance(transform_value, dict) and isinstance(
                    transform_value.get("position"), dict
                )
            else:
                has_transform_position = False
            if not has_transform_position:
                derived_position = derived.transform.get("position")
                if isinstance(derived_position, dict) and any(
                    _optional_number(derived_position.get(axis)) for axis in ("x", "y", "z")
                ):
                    cg_value = derived_position
                elif _envelope_has_size(derived.envelope):
                    envelope_offset = derived.envelope.get("offset_mm")
                    cg_value = envelope_offset if isinstance(envelope_offset, dict) else None
        if not has_declared_cg and cg_value is None and physical_envelope is not None:
            envelope_offset = physical_envelope.get("offset_mm")
            cg_value = envelope_offset if isinstance(envelope_offset, dict) else None
        cg_local_mm = _vector(cg_value)
        cg_body = transform_point_mm(cg_local_mm)

        geometry = parameters.get("geometry")
        geometry = geometry if isinstance(geometry, dict) else {}
        symmetry_mode = str(wb_extension.get("symmetry_mode") or "pair")
        if symmetry_mode == "pair" and (geometry.get("mirror") is True or mirrored_frame):
            # A mirrored lifting surface, and its attached control surfaces,
            # represent the complete left/right pair.  Their aggregate CG is
            # therefore on the aircraft centre plane even when the parent
            # component has a local attachment offset on Y.
            cg_body = (cg_body[0], 0.0, cg_body[2])

        inertia_value = None if source == "derived" else wb_extension.get("inertia_kg_m2")
        if inertia_value is None and source != "derived":
            inertia_value = parameters.get("inertia")
        inertia, has_declared_inertia = _inertia(inertia_value)
        envelope = (
            derived.envelope
            if derived is not None and _envelope_has_size(derived.envelope)
            else physical_envelope
        )
        if not has_declared_inertia:
            inertia, has_derived_inertia = _inertia_from_envelope(envelope, mass_g / 1000.0)
        else:
            has_derived_inertia = False

        # Transform-origin and point-mass fallbacks are intentional for the
        # built-in component types.  Keep the diagnostic for untyped/custom
        # components, where silently accepting an omitted mass model is more
        # likely to hide an incomplete definition.
        fallback_warning = not _is_builtin_component(component)
        if not has_declared_cg and source != "derived" and fallback_warning and cg_value is None:
            component_warnings.append("local CG not declared; transform origin used")
        if not has_declared_inertia and not has_derived_inertia and fallback_warning:
            component_warnings.append("intrinsic inertia not declared; treated as a point mass")

        quality = "declared" if has_declared_cg and has_declared_inertia else "approximate"
        return ComponentMassProperties(
            component_id=component_id,
            component_name=str(component.get("name") or component_id),
            component_type=str(component.get("type") or ""),
            mass_kg=mass_g / 1000.0,
            cg_local_m=tuple(value / 1000.0 for value in cg_local_mm),  # type: ignore[arg-type]
            cg_body_m=cg_body,
            inertia_local_kg_m2=inertia,
            source=source,
            quality=quality,
            warnings=tuple(component_warnings),
        )


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _vector(value: object) -> Vector3:
    data = value if isinstance(value, dict) else {}
    return tuple(_optional_number(data.get(axis)) or 0.0 for axis in ("x", "y", "z"))  # type: ignore[return-value]


def _inertia(value: object) -> tuple[InertiaTensor, bool]:
    if not isinstance(value, dict):
        return InertiaTensor(), False
    values = {
        key: _optional_number(value.get(key)) or 0.0
        for key in ("ixx", "iyy", "izz", "ixy", "ixz", "iyz")
    }
    return InertiaTensor(**values), True


def _inertia_from_envelope(value: object, mass_kg: float) -> tuple[InertiaTensor, bool]:
    """Estimate a solid-box inertia from a local physical envelope.

    The envelope is deliberately only an approximation.  It is still a more
    useful default than a zero tensor for payloads and equipment, and avoids
    requiring every component plugin to duplicate basic rigid-body math.
    """
    if not isinstance(value, dict):
        return InertiaTensor(), False
    size = value.get("size_mm")
    if not isinstance(size, dict):
        return InertiaTensor(), False
    dimensions = tuple(_optional_number(size.get(axis)) or 0.0 for axis in ("x", "y", "z"))
    if mass_kg <= 0.0 or any(dimension <= 0.0 for dimension in dimensions):
        return InertiaTensor(), False
    x_m, y_m, z_m = (dimension / 1000.0 for dimension in dimensions)
    return InertiaTensor(
        ixx=mass_kg * (y_m * y_m + z_m * z_m) / 12.0,
        iyy=mass_kg * (x_m * x_m + z_m * z_m) / 12.0,
        izz=mass_kg * (x_m * x_m + y_m * y_m) / 12.0,
    ), True


def _envelope_has_size(value: object) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("size_mm"), dict):
        return False
    return all(
        (_optional_number(value["size_mm"].get(axis)) or 0.0) > 0.0 for axis in ("x", "y", "z")
    )


def _is_builtin_component(component: dict[str, Any]) -> bool:
    component_type = component.get("type")
    return isinstance(component_type, str) and component_type.startswith("org.setuav.core:")


def _mirrored_frame(component: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> bool:
    """Return whether a component is evaluated as a symmetric pair."""
    parameters = component.get("parameters")
    geometry = parameters.get("geometry") if isinstance(parameters, dict) else None
    if isinstance(geometry, dict) and geometry.get("mirror") is True:
        return True
    parent_id = component.get("attach_to") or component.get("parent")
    parent = by_id.get(str(parent_id)) if isinstance(parent_id, str) else None
    if not isinstance(parent, dict):
        return False
    parent_parameters = parent.get("parameters")
    parent_geometry = (
        parent_parameters.get("geometry") if isinstance(parent_parameters, dict) else None
    )
    return isinstance(parent_geometry, dict) and parent_geometry.get("mirror") is True


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)


def _zero_matrix() -> Matrix3:
    return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def _transpose(matrix: Matrix3) -> Matrix3:
    return tuple(tuple(matrix[column][row] for column in range(3)) for row in range(3))


def _matmul(left: Matrix3, right: Matrix3) -> Matrix3:
    return tuple(
        tuple(
            sum(left[row][index] * right[index][column] for index in range(3))
            for column in range(3)
        )
        for row in range(3)
    )


def _add_matrix(left: Matrix3, right: Matrix3) -> Matrix3:
    return tuple(
        tuple(left[row][column] + right[row][column] for column in range(3)) for row in range(3)
    )


def _parallel_axis(mass_kg: float, offset_m: Vector3) -> Matrix3:
    dx, dy, dz = offset_m
    return (
        (mass_kg * (dy * dy + dz * dz), -mass_kg * dx * dy, -mass_kg * dx * dz),
        (-mass_kg * dx * dy, mass_kg * (dx * dx + dz * dz), -mass_kg * dy * dz),
        (-mass_kg * dx * dz, -mass_kg * dy * dz, mass_kg * (dx * dx + dy * dy)),
    )
