import math
import unittest
from pathlib import Path

from setuav_studio.geometry_data import GeometryData, LoftGeometry, Section
from setuav_studio.geometry_scene import build_project_geometry
from setuav_studio.plugins.geometry.fuselage_geometry import (
    SECTION_SAMPLES,
    build_fuselage_geometry,
    sample_profile,
)
from setuav_studio.plugins.geometry.lifting_surface_geometry import (
    build_lifting_surface_geometry,
    sample_airfoil,
)
from setuav_studio.plugins.geometry.propulsor_geometry import (
    build_propulsor_geometry,
)
from setuav_studio.plugins.viewer.mesh import build_loft_solid_vertices
from setuav_studio.project import ProjectDocument


class GeometryTests(unittest.TestCase):
    def test_all_fuselage_profiles_use_matching_samples(self) -> None:
        profiles = (
            {"type": "circle", "diameter": 100},
            {"type": "ellipse", "width": 120, "height": 80},
            {"type": "rectangle", "width": 120, "height": 80, "corner_radius": 10},
            {"type": "trapezoid", "top_width": 80, "bottom_width": 120, "height": 90, "corner_radius": 5},
            {"type": "triangle", "base_width": 100, "height": 90, "orientation": "down", "corner_radius": 4},
            {
                "type": "polygon",
                "vertices": [
                    {"y": 60, "z": 0, "radius": 5},
                    {"y": 0, "z": 50, "radius": 5},
                    {"y": -60, "z": 0, "radius": 5},
                    {"y": 0, "z": -50, "radius": 5},
                ],
            },
        )
        for profile in profiles:
            with self.subTest(profile=profile["type"]):
                points = sample_profile(profile)
                self.assertEqual(len(points), SECTION_SAMPLES)
                self.assertTrue(all(math.isfinite(value) for point in points for value in point))

    def test_fuselage_component_builds_one_loft_per_segment(self) -> None:
        component = {
            "id": "body",
            "parameters": {
                "geometry": {
                    "segments": [
                        {
                            "tag": "main",
                            "loft": {"method": "smooth"},
                            "sections": [
                                {"position": {"x": 0}, "profile": {"type": "circle", "diameter": 0}},
                                {"position": {"x": 500}, "profile": {"type": "ellipse", "width": 200, "height": 150}},
                                {"position": {"x": 1000}, "profile": {"type": "circle", "diameter": 0}},
                            ],
                        }
                    ]
                }
            },
        }
        lofts = build_fuselage_geometry(component)
        self.assertEqual(len(lofts), 1)
        self.assertEqual(len(lofts[0].sections), 3)

    def test_naca_wing_profiles_build_matching_loops(self) -> None:
        component = {
            "id": "wing-left",
            "parameters": {
                "geometry": {
                    "profiles": [
                        {"position": {"x": 0, "y": 0}, "chord": 250, "airfoil": "naca4412"},
                        {"position": {"x": 40, "y": -700}, "chord": 130, "airfoil": {"type": "naca", "code": "0012"}},
                    ]
                }
            },
        }
        lofts = build_lifting_surface_geometry(component)
        self.assertEqual(len(lofts), 1)
        self.assertEqual(len(lofts[0].sections[0].points), len(sample_airfoil("naca4412")))
        self.assertEqual(len(lofts[0].sections[0].points), len(lofts[0].sections[1].points))

    def test_mirror_instance_reflects_source_geometry(self) -> None:
        project = ProjectDocument(
            Path("project.json"),
            "json",
            {
                "components": [
                    {
                        "kind": "component",
                        "id": "wing-left",
                        "type": "example:wing",
                        "transform": {"position": {"x": 10}},
                    },
                    {
                        "kind": "instance",
                        "id": "wing-right",
                        "source": "wing-left",
                        "derivation": {"type": "mirror", "plane": "XZ"},
                    },
                ]
            },
        )

        def provider(_component):
            return (
                LoftGeometry(
                    "wing-left",
                    (
                        Section(((0, -1, 0), (0, -2, 0), (0, -1, 1))),
                        Section(((1, -1, 0), (1, -2, 0), (1, -1, 1))),
                    ),
                    subdivisions=0,
                ),
            )

        data = build_project_geometry(project, {"example:wing": provider})
        left = next(loft for loft in data.lofts if loft.component_id == "wing-left")
        right = next(loft for loft in data.lofts if loft.component_id == "wing-right")
        self.assertEqual(left.sections[0].points[0], (10.0, -1.0, 0.0))
        self.assertEqual(right.sections[0].points[0], (10.0, 1.0, 0.0))

    def test_solid_mesh_contains_triangle_vertices(self) -> None:
        data = GeometryData(
            (
                LoftGeometry(
                    "body",
                    (
                        Section(((0, 0, 0), (0, 1, 0), (0, 0, 1))),
                        Section(((1, 0, 0), (1, 1, 0), (1, 0, 1))),
                    ),
                    subdivisions=0,
                ),
            )
        )
        vertices = build_loft_solid_vertices(data)
        self.assertGreater(len(vertices), 0)
        self.assertEqual(len(vertices) % 9, 0)
        self.assertEqual((len(vertices) // 9) % 3, 0)

    def test_propulsor_builds_hub_and_blades(self) -> None:
        lofts = build_propulsor_geometry(
            {
                "id": "propeller",
                "parameters": {"diameter": 300, "blade_count": 3},
            }
        )
        self.assertEqual(len(lofts), 4)


if __name__ == "__main__":
    unittest.main()
