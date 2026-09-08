"""Unit tests for the core Vehicle, System, Component, State, Environment, and Data models."""

from __future__ import annotations

import unittest

from setuav_studio.model import (
    Component,
    Data,
    Environment,
    GenericComponent,
    State,
    Vehicle,
)


class TestModelHierarchy(unittest.TestCase):
    def test_data_container_dot_and_dict_access(self) -> None:
        d = Data()
        d.alpha = 5.0
        d.sub = {"beta": 2.0}
        self.assertEqual(d.alpha, 5.0)
        self.assertEqual(d["alpha"], 5.0)
        self.assertIsInstance(d.sub, Data)
        self.assertEqual(d.sub.beta, 2.0)
        self.assertEqual(d["sub"]["beta"], 2.0)

        # Serialization
        as_dict = d.to_dict()
        self.assertEqual(as_dict, {"alpha": 5.0, "sub": {"beta": 2.0}})
        restored = Data.from_dict(as_dict)
        self.assertEqual(restored.sub.beta, 2.0)

    def test_isa_environment(self) -> None:
        # Sea level standard
        env_sl = Environment.isa(0.0)
        self.assertAlmostEqual(env_sl.temperature_k, 288.15, places=1)
        self.assertAlmostEqual(env_sl.pressure_pa, 101325.0, places=0)
        self.assertAlmostEqual(env_sl.density_kg_m3, 1.225, places=2)
        self.assertAlmostEqual(env_sl.speed_of_sound_mps, 340.29, places=1)

        # 1000m altitude
        env_1k = Environment.isa(1000.0)
        self.assertLess(env_1k.temperature_k, env_sl.temperature_k)
        self.assertLess(env_1k.pressure_pa, env_sl.pressure_pa)
        self.assertLess(env_1k.density_kg_m3, env_sl.density_kg_m3)

        # Serialization
        serialized = env_1k.to_dict()
        restored = Environment.from_dict(serialized)
        self.assertAlmostEqual(restored.density_kg_m3, env_1k.density_kg_m3, places=3)

    def test_minimal_state_model(self) -> None:
        env = Environment.isa(500.0)
        state = State(id="climb_state", name="Climb Phase", time_s=45.0, environment=env)

        # Plugins dynamically attach any variables directly via dot or dict
        state.airspeed = 22.5
        state.alpha = 4.2
        state.throttle = 0.85
        state.battery_voltage = 23.4
        state.custom_metric = {"sub_val": 100}

        self.assertEqual(state.airspeed, 22.5)
        self.assertEqual(state["alpha"], 4.2)
        self.assertEqual(state.throttle, 0.85)
        self.assertEqual(state.battery_voltage, 23.4)
        self.assertEqual(state.custom_metric.sub_val, 100)

        # Serialization
        data_dict = state.to_dict()
        restored = State.from_dict(data_dict)
        self.assertEqual(restored.id, "climb_state")
        self.assertEqual(restored.airspeed, 22.5)
        self.assertEqual(restored.battery_voltage, 23.4)
        self.assertAlmostEqual(restored.environment.altitude_m, 500.0)

    def test_component_model(self) -> None:
        comp = Component(
            {
                "id": "motor-1",
                "name": "Front Motor",
                "type": "org.setuav.core:motor",
                "mass": 0.25,
                "attach_to": "fuselage-main",
                "transform": {
                    "position": {"x": 1.2, "y": 0.0, "z": -0.1},
                    "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                },
                "parameters": {"kv": 920.0, "resistance": 0.045},
            }
        )
        self.assertEqual(comp.id, "motor-1")
        self.assertEqual(comp.parent_id, "fuselage-main")
        self.assertEqual(comp.mass, 0.25)
        self.assertEqual(comp.x, 1.2)
        self.assertEqual(comp.kv, 920.0)

        # Modifying position
        comp.y = 0.4
        self.assertEqual(comp.position["y"], 0.4)

    def test_generic_component_fallback(self) -> None:
        generic = GenericComponent({"id": "custom-part", "name": "Custom", "type": "custom"})
        self.assertEqual(generic.id, "custom-part")

    def test_system_and_vehicle_hierarchy(self) -> None:
        vehicle = Vehicle(id="skyhunter", name="SkyHunter UAV", type="fixed_wing")

        # Create subsystems
        aero_sys = vehicle.get_or_create_system("aerostructure", system_type="aerostructure")
        prop_sys = vehicle.get_or_create_system("propulsion", system_type="propulsion")

        wing = Component(
            {"id": "wing-main", "name": "Main Wing", "type": "org.setuav.core:lifting-surface"}
        )
        motor = Component({"id": "motor-1", "name": "Motor", "type": "org.setuav.core:motor"})

        aero_sys.add_component(wing)
        prop_sys.add_component(motor)

        # Queries
        self.assertEqual(len(vehicle.systems), 2)
        self.assertEqual(len(vehicle.all_components()), 2)
        self.assertIs(vehicle.get_component("wing-main"), wing)
        self.assertIs(vehicle.get_component("motor-1"), motor)
        self.assertIsNone(vehicle.get_component("non-existent"))

        # Serialization & roundtrip
        v_dict = vehicle.to_dict()
        restored_v = Vehicle.from_dict(v_dict)
        self.assertEqual(restored_v.name, "SkyHunter UAV")
        self.assertEqual(len(restored_v.systems), 2)
        self.assertEqual(len(restored_v.all_components()), 2)

    def test_vehicle_backward_compatibility_flat_components(self) -> None:
        flat_data = {
            "id": "legacy_uav",
            "name": "Legacy UAV",
            "components": [
                {"id": "c1", "name": "Wing", "type": "lifting-surface"},
                {"id": "c2", "name": "Fuselage", "type": "fuselage"},
            ],
        }
        vehicle = Vehicle.from_dict(flat_data)
        self.assertEqual(len(vehicle.all_components()), 2)
        self.assertEqual(vehicle.get_component("c1").name, "Wing")


if __name__ == "__main__":
    unittest.main()
