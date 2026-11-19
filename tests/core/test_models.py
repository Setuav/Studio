"""Unit tests for core Environment, InertiaTensor, and Component models."""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from setuav_studio.api.contributions import ParameterField
from setuav_studio.model import (
    Component,
    Environment,
    GenericComponent,
    InertiaTensor,
)

# ==============================================================================
# 1. Environment Tests
# ==============================================================================


def test_environment_isa_sea_level() -> None:
    env = Environment.isa(0.0)
    assert math.isclose(env.altitude_m, 0.0, abs_tol=1e-6)
    assert math.isclose(env.temperature_k, 288.15, rel_tol=1e-4)
    assert math.isclose(env.pressure_pa, 101325.0, rel_tol=1e-4)
    assert math.isclose(env.density_kg_m3, 1.225, rel_tol=1e-3)
    assert math.isclose(env.speed_of_sound_mps, 340.294, rel_tol=1e-3)


def test_environment_isa_altitude_decay() -> None:
    env_sl = Environment.isa(0.0)
    env_5k = Environment.isa(5000.0)

    assert env_5k.altitude_m == 5000.0
    assert env_5k.temperature_k < env_sl.temperature_k
    assert env_5k.pressure_pa < env_sl.pressure_pa
    assert env_5k.density_kg_m3 < env_sl.density_kg_m3


def test_environment_serialization_roundtrip() -> None:
    env = Environment(
        altitude_m=2000.0,
        temperature_k=275.15,
        pressure_pa=79500.0,
        density_kg_m3=1.006,
        speed_of_sound_mps=332.5,
    )
    raw = env.to_dict()
    restored = Environment.from_dict(raw)

    assert math.isclose(restored.altitude_m, 2000.0)
    assert math.isclose(restored.temperature_k, 275.15)
    assert math.isclose(restored.pressure_pa, 79500.0)
    assert math.isclose(restored.density_kg_m3, 1.006)
    assert math.isclose(restored.speed_of_sound_mps, 332.5)


# ==============================================================================
# 2. InertiaTensor Tests
# ==============================================================================


def test_inertia_tensor_matrix_representation() -> None:
    tensor = InertiaTensor(ixx=0.10, iyy=0.20, izz=0.30, ixy=0.01, ixz=0.02, iyz=0.03)
    mat = tensor.as_matrix()

    # Diagonal: positive moments
    assert math.isclose(mat[0][0], 0.10)
    assert math.isclose(mat[1][1], 0.20)
    assert math.isclose(mat[2][2], 0.30)

    # Off-diagonal: negative products of inertia
    assert math.isclose(mat[0][1], -0.01)
    assert math.isclose(mat[1][0], -0.01)
    assert math.isclose(mat[0][2], -0.02)
    assert math.isclose(mat[2][0], -0.02)
    assert math.isclose(mat[1][2], -0.03)
    assert math.isclose(mat[2][1], -0.03)


def test_inertia_tensor_roundtrip_conversions() -> None:
    mat = [
        [0.5, -0.05, -0.02],
        [-0.05, 0.8, -0.01],
        [-0.02, -0.01, 1.2],
    ]
    tensor = InertiaTensor.from_matrix(mat)
    assert math.isclose(tensor.ixx, 0.5)
    assert math.isclose(tensor.iyy, 0.8)
    assert math.isclose(tensor.izz, 1.2)
    assert math.isclose(tensor.ixy, 0.05)
    assert math.isclose(tensor.ixz, 0.02)
    assert math.isclose(tensor.iyz, 0.01)

    d = tensor.to_dict()
    from_dict_tensor = InertiaTensor.from_dict(d)
    assert math.isclose(from_dict_tensor.ixx, 0.5)
    assert math.isclose(from_dict_tensor.iyy, 0.8)
    assert math.isclose(from_dict_tensor.izz, 1.2)


# ==============================================================================
# 3. Component Core Lifecycle & Properties
# ==============================================================================


def test_component_init_and_identity() -> None:
    comp = Component(id="motor-1", name="Main Motor", type="org.setuav.core:propulsor")
    assert comp.id == "motor-1"
    assert comp.name == "Main Motor"
    assert comp.type == "org.setuav.core:propulsor"
    assert comp.component_type == "org.setuav.core:propulsor"
    assert comp.attach_to is None

    # Name falls back to ID if not specified
    comp2 = Component(id="servo-1")
    assert comp2.name == "servo-1"

    # Setters update internal raw data
    comp2.name = "Elevator Servo"
    assert comp2.name == "Elevator Servo"
    assert comp2.raw_data["name"] == "Elevator Servo"


def test_component_attach_to_property() -> None:
    comp = Component(id="wing", attach_to="fuselage")
    assert comp.attach_to == "fuselage"
    assert comp.raw_data["attach_to"] == "fuselage"

    comp.attach_to = "center_box"
    assert comp.attach_to == "center_box"

    # Attaching to the vehicle clears the key
    comp.attach_to = None
    assert comp.attach_to is None
    assert "attach_to" not in comp.raw_data


def test_component_spatial_transform_and_coordinates() -> None:
    comp = Component(
        {
            "id": "comp-1",
            "transform": {
                "position": {"x": 100.0, "y": 200.0, "z": -50.0},
                "rotation": {"roll": 5.0, "pitch": -2.0, "yaw": 10.0},
            },
        }
    )
    assert math.isclose(comp.x, 100.0)
    assert math.isclose(comp.y, 200.0)
    assert math.isclose(comp.z, -50.0)
    assert math.isclose(comp.roll, 5.0)
    assert math.isclose(comp.pitch, -2.0)
    assert math.isclose(comp.yaw, 10.0)

    # Coordinate setters
    comp.x = 150.0
    comp.y = 250.0
    comp.z = 0.0
    assert math.isclose(comp.position["x"], 150.0)
    assert math.isclose(comp.position["y"], 250.0)
    assert math.isclose(comp.position["z"], 0.0)


def test_component_mass_and_inertia_properties() -> None:
    comp = Component(
        {
            "id": "battery",
            "mass": 350.0,
            "local_cg_mm": {"x": 20.0, "y": 0.0, "z": -5.0},
            "inertia_kg_m2": {"ixx": 0.005, "iyy": 0.01, "izz": 0.012},
        }
    )
    assert math.isclose(comp.mass, 350.0)
    assert math.isclose(comp.local_cg["x"], 20.0)
    assert math.isclose(comp.local_cg["z"], -5.0)
    assert math.isclose(comp.inertia["iyy"], 0.01)

    # Inertia tensor conversion
    assert isinstance(comp.inertia_tensor, InertiaTensor)
    assert math.isclose(comp.inertia_tensor.izz, 0.012)

    # Modifying local CG updates raw_data
    comp.local_cg = {"x": 25.0, "y": 2.0, "z": -5.0}
    assert math.isclose(comp.raw_data["local_cg_mm"]["x"], 25.0)
    assert math.isclose(comp.raw_data["local_cg_mm"]["y"], 2.0)


def test_component_rejects_subscript_indexing() -> None:
    comp = Component(id="test_comp")
    with pytest.raises(TypeError):
        _ = cast(Any, comp)["id"]


# ==============================================================================
# 4. Parameters and Dynamic Attribute Routing
# ==============================================================================


def test_component_parameters_and_attributes() -> None:
    comp = Component(
        {
            "id": "esc-1",
            "parameters": {
                "max_current": 60.0,
                "bec_voltage": 5.0,
                "geometry": {"fin_count": 8},
            },
        }
    )
    comp.parameters["max_current"] = 80.0

    # __getattr__ parameter routing
    assert comp.max_current == 80.0
    assert comp.bec_voltage == 5.0
    # Nested geometry parameter routing
    assert comp.fin_count == 8

    # Non-existent attribute raises AttributeError
    with pytest.raises(AttributeError):
        _ = comp.non_existent_attribute


def test_component_sections_and_profiles_routing() -> None:
    comp = Component(
        {
            "id": "wing",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {"chord": 300.0, "airfoil": "NACA0012"},
                        {"chord": 150.0, "airfoil": "NACA0010"},
                    ]
                }
            },
        }
    )
    assert len(comp.sections) == 2
    assert math.isclose(comp.sections[0].chord, 300.0)
    assert comp.sections[0].airfoil == "NACA0012"

    # Index shortcut routing: comp.section_0, comp.section_1
    assert comp.section_0.airfoil == "NACA0012"
    assert math.isclose(comp.section_1.chord, 150.0)


# ==============================================================================
# 5. ParameterField Descriptors & Custom Subclasses
# ==============================================================================


class PropellerModel(Component):
    COMPONENT_TYPE = "org.setuav.propulsion:propeller"

    diameter = ParameterField(label="Diameter", unit="in", default=10.0)
    blade_pitch = ParameterField(label="Pitch", unit="in", default=4.5)
    blades = ParameterField(label="Blades", default=2)


def test_component_subclass_with_parameter_fields() -> None:
    # 1. Defaults populated automatically
    prop = PropellerModel(id="prop-1")
    assert prop.type == "org.setuav.propulsion:propeller"
    assert math.isclose(prop.diameter, 10.0)
    assert math.isclose(prop.blade_pitch, 4.5)
    assert prop.blades == 2

    # 2. Overridden via constructor
    prop_custom = PropellerModel(id="prop-2", diameter=12.0, blade_pitch=6.0, blades=3)
    assert math.isclose(prop_custom.diameter, 12.0)
    assert math.isclose(prop_custom.blade_pitch, 6.0)
    assert prop_custom.blades == 3

    # 3. Field descriptors reflection
    fields = PropellerModel.get_fields()
    field_keys = [f.key for f in fields]
    assert "diameter" in field_keys
    assert "blade_pitch" in field_keys
    assert "blades" in field_keys


def test_generic_component_fallback() -> None:
    gen = GenericComponent(id="sensor_payload", name="Camera", type="custom_type")
    assert isinstance(gen, Component)
    assert gen.id == "sensor_payload"
    assert gen.name == "Camera"
    assert gen.type == "custom_type"


# ==============================================================================
# 6. Attachment with Transform Preservation
# ==============================================================================


def test_component_attach_keeps_its_place() -> None:
    comp_a = {
        "id": "target_a",
        "transform": {
            "position": {"x": 100.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
    }
    comp_b = {
        "id": "child_b",
        "attach_to": "target_a",
        "transform": {
            "position": {"x": 50.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
    }
    project_data = {"components": [comp_a, comp_b]}

    model_b = Component(comp_b)
    # Attach to the vehicle, keeping the vehicle-frame position 100 + 50 = 150
    model_b.attach(None, project_data, preserve_world_transform=True)
    assert model_b.attach_to is None
    assert math.isclose(model_b.x, 150.0, rel_tol=1e-5)
