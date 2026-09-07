"""Airframe geometry generator for aircraft concept presets.

Transforms high-level design constants into fully instantiated 3D parametric
CAD components (fuselage, lifting surfaces, empennage, assembly) ready for
the SetUAV Studio project document and 3D OpenGL viewport.
"""

from __future__ import annotations

import math
import re
from typing import Any

from ..engine.fuselage_geometry import create_default_section

_FUSELAGE_TYPE = "org.setuav.core:fuselage"
_LIFTING_SURFACE_TYPE = "org.setuav.core:lifting-surface"
_STRUCTURAL_SYSTEM_TYPE = "org.setuav.core:structural-system"


def _clean_airfoil(name: str) -> str:
    """Normalize airfoil name to NACA 4-digit or standard token."""
    digits = re.sub(r"[^\d]", "", name)
    if len(digits) >= 4:
        return digits[:4]
    name_clean = name.lower().replace(" ", "").replace("-", "")
    if "clark" in name_clean:
        return "2412"  # robust NACA fallback for 3D viewer
    if "mh45" in name_clean:
        return "2412"
    return "2412"


def _build_pod_boom_fuselage(config: dict[str, Any]) -> dict[str, Any]:
    length = float(config.get("fuselage_length_mm", 850.0))
    diameter = float(config.get("fuselage_diameter_mm", 130.0))
    nose_len = float(config.get("nose_length_mm", 220.0))
    tail_len = float(config.get("tail_length_mm", 450.0))

    pod_end = max(length - tail_len, nose_len + 150.0)
    boom_start = pod_end + 20.0

    sections = [
        # Nose tip
        create_default_section(0.0, "circle"),
        # Nose curve
        create_default_section(nose_len * 0.4, "ellipse"),
        # Cockpit / max station
        create_default_section(nose_len, "ellipse"),
        # Mid-body / wing saddle
        create_default_section(min(nose_len + 200.0, pod_end - 40.0), "ellipse"),
        # Pod aft taper (pusher motor cowl)
        create_default_section(pod_end, "circle"),
        # Slender tubular tail boom
        create_default_section(boom_start, "circle"),
        # Boom end / tail mounting station
        create_default_section(length, "circle"),
    ]

    # Diameter / ellipse sizing
    sections[0]["profile"]["diameter"] = 24.0
    sections[1]["profile"]["width"] = diameter * 0.8
    sections[1]["profile"]["height"] = diameter * 0.9
    sections[2]["profile"]["width"] = diameter
    sections[2]["profile"]["height"] = diameter * 1.1
    sections[3]["profile"]["width"] = diameter * 0.95
    sections[3]["profile"]["height"] = diameter * 1.05
    sections[4]["profile"]["diameter"] = diameter * 0.5
    sections[5]["profile"]["diameter"] = 26.0
    sections[6]["profile"]["diameter"] = 22.0

    return {
        "kind": "component",
        "id": "fuselage",
        "name": "Fuselage (Pod & Boom)",
        "type": _FUSELAGE_TYPE,
        "parent": None,
        "mass": 420.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "cylinder",
            "size_mm": {"x": length, "y": diameter, "z": diameter},
            "offset_mm": {"x": length / 2.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "geometry": {
                "segments": [
                    {
                        "tag": "main",
                        "loft": {
                            "method": "smooth",
                            "parameterization": "centripetal",
                            "profile_correspondence": "cardinal_quadrants",
                        },
                        "sections": sections,
                    }
                ]
            }
        },
    }


def _build_monocoque_fuselage(config: dict[str, Any]) -> dict[str, Any]:
    length = float(config.get("fuselage_length_mm", 1050.0))
    diameter = float(config.get("fuselage_diameter_mm", 115.0))
    nose_len = float(config.get("nose_length_mm", 250.0))

    sections = [
        # Spinner / nose tip
        create_default_section(0.0, "circle"),
        # Cowling blend
        create_default_section(nose_len * 0.4, "ellipse"),
        # Cabin max section
        create_default_section(nose_len, "ellipse"),
        # Mid cabin
        create_default_section(nose_len + 280.0, "ellipse"),
        # Aft cabin taper
        create_default_section(length - 250.0, "ellipse"),
        # Tail cone
        create_default_section(length, "circle"),
    ]

    sections[0]["profile"]["diameter"] = 40.0
    sections[1]["profile"]["width"] = diameter * 0.85
    sections[1]["profile"]["height"] = diameter * 0.95
    sections[2]["profile"]["width"] = diameter
    sections[2]["profile"]["height"] = diameter * 1.2
    sections[3]["profile"]["width"] = diameter * 0.95
    sections[3]["profile"]["height"] = diameter * 1.1
    sections[4]["profile"]["width"] = diameter * 0.55
    sections[4]["profile"]["height"] = diameter * 0.75
    sections[5]["profile"]["diameter"] = 25.0

    return {
        "kind": "component",
        "id": "fuselage",
        "name": "Fuselage (Monocoque)",
        "type": _FUSELAGE_TYPE,
        "parent": None,
        "mass": 480.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "cylinder",
            "size_mm": {"x": length, "y": diameter, "z": diameter},
            "offset_mm": {"x": length / 2.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "geometry": {
                "segments": [
                    {
                        "tag": "main",
                        "loft": {
                            "method": "smooth",
                            "parameterization": "centripetal",
                            "profile_correspondence": "cardinal_quadrants",
                        },
                        "sections": sections,
                    }
                ]
            }
        },
    }


def _build_center_pod_fuselage(config: dict[str, Any]) -> dict[str, Any]:
    length = float(config.get("fuselage_length_mm", 750.0))
    diameter = float(config.get("fuselage_diameter_mm", 140.0))
    nose_len = float(config.get("nose_length_mm", 220.0))

    sections = [
        create_default_section(0.0, "circle"),
        create_default_section(nose_len * 0.45, "ellipse"),
        create_default_section(nose_len, "ellipse"),
        create_default_section(min(nose_len + 240.0, length - 120.0), "ellipse"),
        create_default_section(length - 50.0, "circle"),
        create_default_section(length, "circle"),
    ]

    sections[0]["profile"]["diameter"] = 32.0
    sections[1]["profile"]["width"] = diameter * 0.85
    sections[1]["profile"]["height"] = diameter * 0.95
    sections[2]["profile"]["width"] = diameter
    sections[2]["profile"]["height"] = diameter * 1.15
    sections[3]["profile"]["width"] = diameter * 0.95
    sections[3]["profile"]["height"] = diameter * 1.05
    sections[4]["profile"]["diameter"] = diameter * 0.65
    sections[5]["profile"]["diameter"] = 45.0

    return {
        "kind": "component",
        "id": "fuselage",
        "name": "Center Fuselage Pod",
        "type": _FUSELAGE_TYPE,
        "parent": None,
        "mass": 390.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "cylinder",
            "size_mm": {"x": length, "y": diameter, "z": diameter},
            "offset_mm": {"x": length / 2.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "geometry": {
                "segments": [
                    {
                        "tag": "main",
                        "loft": {
                            "method": "smooth",
                            "parameterization": "centripetal",
                            "profile_correspondence": "cardinal_quadrants",
                        },
                        "sections": sections,
                    }
                ]
            }
        },
    }


def _build_blended_center_fuselage(config: dict[str, Any]) -> dict[str, Any]:
    length = float(config.get("fuselage_length_mm", 350.0))
    diameter = float(config.get("fuselage_diameter_mm", 120.0))
    nose_len = float(config.get("nose_length_mm", 120.0))

    sections = [
        create_default_section(0.0, "circle"),
        create_default_section(nose_len * 0.5, "ellipse"),
        create_default_section(nose_len, "ellipse"),
        create_default_section(length - 50.0, "ellipse"),
        create_default_section(length, "circle"),
    ]

    sections[0]["profile"]["diameter"] = 28.0
    sections[1]["profile"]["width"] = diameter * 0.8
    sections[1]["profile"]["height"] = diameter * 0.55
    sections[2]["profile"]["width"] = diameter
    sections[2]["profile"]["height"] = diameter * 0.65
    sections[3]["profile"]["width"] = diameter * 0.7
    sections[3]["profile"]["height"] = diameter * 0.45
    sections[4]["profile"]["diameter"] = 38.0

    return {
        "kind": "component",
        "id": "fuselage",
        "name": "Blended Center Body",
        "type": _FUSELAGE_TYPE,
        "parent": None,
        "mass": 220.0,
        "transform": {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": length, "y": diameter, "z": diameter * 0.65},
            "offset_mm": {"x": length / 2.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "geometry": {
                "segments": [
                    {
                        "tag": "main",
                        "loft": {
                            "method": "smooth",
                            "parameterization": "centripetal",
                            "profile_correspondence": "cardinal_quadrants",
                        },
                        "sections": sections,
                    }
                ]
            }
        },
    }


def build_fuselage_component(config: dict[str, Any]) -> dict[str, Any]:
    """Generate the primary fuselage component matching the concept architecture."""
    style = str(config.get("fuselage_style", "Pod & Boom"))
    if "Center Pod" in style:
        return _build_center_pod_fuselage(config)
    if "Pod" in style:
        return _build_pod_boom_fuselage(config)
    if "Blended" in style:
        return _build_blended_center_fuselage(config)
    return _build_monocoque_fuselage(config)


def build_main_wing_component(config: dict[str, Any]) -> dict[str, Any]:
    """Generate the parametric main lifting surface."""
    span = float(config.get("wingspan_mm", 1400.0))
    root_chord = float(config.get("wing_root_chord_mm", 210.0))
    tip_chord = float(config.get("wing_tip_chord_mm", 130.0))
    sweep_deg = float(config.get("wing_sweep_deg", 2.0))
    dihedral_deg = float(config.get("wing_dihedral_deg", 2.0))
    airfoil = _clean_airfoil(str(config.get("wing_airfoil", "NACA 2412")))
    position_style = str(config.get("wing_position", "High-Wing"))
    nose_len = float(config.get("nose_length_mm", 220.0))
    fuse_diam = float(config.get("fuselage_diameter_mm", 130.0))

    semi_span = span / 2.0
    rad_sweep = math.radians(sweep_deg)
    rad_dihedral = math.radians(dihedral_deg)

    tip_x = semi_span * math.tan(rad_sweep)
    tip_z = semi_span * math.tan(rad_dihedral)

    # Vertical mount position based on placement
    if "High" in position_style:
        z_mount = fuse_diam * 0.48
    elif "Low" in position_style:
        z_mount = -fuse_diam * 0.35
    else:
        z_mount = 0.0

    x_mount = nose_len + 30.0 if "Blended" not in config.get("fuselage_style", "") else 50.0

    profiles = [
        {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "chord": root_chord,
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "airfoil": airfoil,
        },
        {
            "position": {"x": round(tip_x, 1), "y": round(semi_span, 1), "z": round(tip_z, 1)},
            "chord": tip_chord,
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "airfoil": airfoil,
        },
    ]

    return {
        "kind": "component",
        "id": "main-wing",
        "name": "Main Wing",
        "type": _LIFTING_SURFACE_TYPE,
        "attach_to": "fuselage",
        "mass": 350.0,
        "transform": {
            "position": {"x": x_mount, "y": 0.0, "z": z_mount},
            "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        },
        "envelope": {
            "shape": "box",
            "size_mm": {"x": root_chord, "y": span, "z": 35.0},
            "offset_mm": {"x": root_chord / 2.0, "y": 0.0, "z": 0.0},
        },
        "parameters": {
            "geometry": {
                "mirror": True,
                "symmetric": True,
                "profiles": profiles,
                "tip_treatment": {"type": "flat"},
            }
        },
    }


def build_tail_components(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate the tail empennage surfaces according to concept architecture."""
    tail_type = str(config.get("tail_type", "V-Tail"))
    tail_span = float(config.get("tail_span_mm", 380.0))
    root_chord = float(config.get("tail_root_chord_mm", 120.0))
    tip_chord = float(config.get("tail_tip_chord_mm", 80.0))
    v_angle = float(config.get("tail_v_angle_deg", 110.0))
    fin_height = float(config.get("tail_height_mm", 160.0))
    airfoil = _clean_airfoil(str(config.get("tail_airfoil", "NACA 0012")))
    fuse_length = float(config.get("fuselage_length_mm", 850.0))
    fuse_diam = float(config.get("fuselage_diameter_mm", 130.0))
    nose_len = float(config.get("nose_length_mm", 220.0))
    tail_arm = float(config.get("tail_arm_mm", 520.0))

    components: list[dict[str, Any]] = []

    if tail_type in ("V-Tail", "Inverted V-Tail"):
        semi_span = tail_span / 2.0
        is_inverted = tail_type == "Inverted V-Tail"
        roll_angle = (180.0 - v_angle) / 2.0 if not is_inverted else -(180.0 - v_angle) / 2.0
        x_tail = fuse_length - root_chord - 10.0

        components.append(
            {
                "kind": "component",
                "id": "v-tail",
                "name": "V-Tail Empennage",
                "type": _LIFTING_SURFACE_TYPE,
                "attach_to": "fuselage",
                "mass": 90.0,
                "transform": {
                    "position": {"x": x_tail, "y": 0.0, "z": 12.0 if not is_inverted else -12.0},
                    "rotation": {"roll": roll_angle, "pitch": 0.0, "yaw": 0.0},
                },
                "envelope": {
                    "shape": "box",
                    "size_mm": {"x": root_chord, "y": tail_span, "z": 18.0},
                    "offset_mm": {"x": root_chord / 2.0, "y": 0.0, "z": 0.0},
                },
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "symmetric": True,
                        "profiles": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "chord": root_chord,
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "airfoil": airfoil,
                            },
                            {
                                "position": {"x": 20.0, "y": semi_span, "z": 0.0},
                                "chord": tip_chord,
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "airfoil": airfoil,
                            },
                        ],
                    }
                },
            }
        )

    elif tail_type in ("Conventional", "T-Tail"):
        semi_span = tail_span / 2.0
        is_t_tail = tail_type == "T-Tail"
        x_tail = fuse_length - root_chord - 20.0

        # Horizontal Tail
        ht_z = fin_height if is_t_tail else 15.0
        components.append(
            {
                "kind": "component",
                "id": "horizontal-tail",
                "name": "Horizontal Tail",
                "type": _LIFTING_SURFACE_TYPE,
                "attach_to": "fuselage",
                "mass": 65.0,
                "transform": {
                    "position": {"x": x_tail, "y": 0.0, "z": ht_z},
                    "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                },
                "envelope": {
                    "shape": "box",
                    "size_mm": {"x": root_chord, "y": tail_span, "z": 15.0},
                    "offset_mm": {"x": root_chord / 2.0, "y": 0.0, "z": 0.0},
                },
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "symmetric": True,
                        "profiles": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "chord": root_chord,
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "airfoil": airfoil,
                            },
                            {
                                "position": {"x": 15.0, "y": semi_span, "z": 0.0},
                                "chord": tip_chord,
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "airfoil": airfoil,
                            },
                        ],
                    }
                },
            }
        )

        # Vertical Tail
        components.append(
            {
                "kind": "component",
                "id": "vertical-tail",
                "name": "Vertical Tail",
                "type": _LIFTING_SURFACE_TYPE,
                "attach_to": "fuselage",
                "mass": 45.0,
                "transform": {
                    "position": {"x": x_tail - 30.0, "y": 0.0, "z": 15.0},
                    "rotation": {"roll": 90.0, "pitch": 0.0, "yaw": 0.0},
                },
                "envelope": {
                    "shape": "box",
                    "size_mm": {"x": root_chord * 1.2, "y": 15.0, "z": fin_height},
                    "offset_mm": {"x": root_chord * 0.6, "y": 0.0, "z": fin_height / 2.0},
                },
                "parameters": {
                    "geometry": {
                        "mirror": False,
                        "symmetric": False,
                        "profiles": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "chord": root_chord * 1.25,
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "airfoil": airfoil,
                            },
                            {
                                "position": {"x": 35.0, "y": fin_height, "z": 0.0},
                                "chord": tip_chord,
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "airfoil": airfoil,
                            },
                        ],
                    }
                },
            }
        )

    elif tail_type == "Twin Boom":
        boom_y = tail_span / 2.0
        x_boom_end = nose_len + tail_arm
        x_tail = x_boom_end - root_chord

        # Twin Carbon Booms
        for side, y_pos in (("right", boom_y), ("left", -boom_y)):
            boom_sections = [
                create_default_section(0.0, "circle"),
                create_default_section(tail_arm, "circle"),
            ]
            boom_sections[0]["profile"]["diameter"] = 28.0
            boom_sections[1]["profile"]["diameter"] = 22.0
            components.append(
                {
                    "kind": "component",
                    "id": f"boom-{side}",
                    "name": f"Tail Boom ({side.title()})",
                    "type": _FUSELAGE_TYPE,
                    "parent": "main-wing",
                    "mass": 75.0,
                    "transform": {
                        "position": {"x": nose_len + 30.0, "y": y_pos, "z": fuse_diam * 0.45},
                        "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    },
                    "envelope": {
                        "shape": "cylinder",
                        "size_mm": {"x": tail_arm, "y": 25.0, "z": 25.0},
                        "offset_mm": {"x": tail_arm / 2.0, "y": 0.0, "z": 0.0},
                    },
                    "parameters": {
                        "geometry": {
                            "segments": [
                                {
                                    "tag": "main",
                                    "loft": {"method": "linear", "parameterization": "uniform"},
                                    "sections": boom_sections,
                                }
                            ]
                        }
                    },
                }
            )

        # Horizontal Stabilizer bridging the two booms
        components.append(
            {
                "kind": "component",
                "id": "horizontal-tail",
                "name": "Horizontal Stabilizer",
                "type": _LIFTING_SURFACE_TYPE,
                "attach_to": "fuselage",
                "mass": 70.0,
                "transform": {
                    "position": {"x": x_tail, "y": 0.0, "z": fuse_diam * 0.45},
                    "rotation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                },
                "envelope": {
                    "shape": "box",
                    "size_mm": {"x": root_chord, "y": tail_span, "z": 15.0},
                    "offset_mm": {"x": root_chord / 2.0, "y": 0.0, "z": 0.0},
                },
                "parameters": {
                    "geometry": {
                        "mirror": True,
                        "symmetric": True,
                        "profiles": [
                            {
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "chord": root_chord,
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "airfoil": airfoil,
                            },
                            {
                                "position": {"x": 0.0, "y": boom_y, "z": 0.0},
                                "chord": root_chord,
                                "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                "airfoil": airfoil,
                            },
                        ],
                    }
                },
            }
        )

        # Twin Vertical Fins
        for side, y_pos in (("right", boom_y), ("left", -boom_y)):
            components.append(
                {
                    "kind": "component",
                    "id": f"fin-{side}",
                    "name": f"Vertical Fin ({side.title()})",
                    "type": _LIFTING_SURFACE_TYPE,
                    "attach_to": "fuselage",
                    "mass": 35.0,
                    "transform": {
                        "position": {"x": x_tail - 20.0, "y": y_pos, "z": fuse_diam * 0.45},
                        "rotation": {"roll": 90.0, "pitch": 0.0, "yaw": 0.0},
                    },
                    "envelope": {
                        "shape": "box",
                        "size_mm": {"x": root_chord, "y": 15.0, "z": fin_height},
                        "offset_mm": {"x": root_chord / 2.0, "y": 0.0, "z": fin_height / 2.0},
                    },
                    "parameters": {
                        "geometry": {
                            "mirror": False,
                            "symmetric": False,
                            "profiles": [
                                {
                                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "chord": root_chord * 1.1,
                                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "airfoil": airfoil,
                                },
                                {
                                    "position": {"x": 20.0, "y": fin_height, "z": 0.0},
                                    "chord": tip_chord,
                                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "airfoil": airfoil,
                                },
                            ],
                        }
                    },
                }
            )

    elif tail_type == "Winglets Only":
        # Flying Wing Winglets at Wing Tips
        span = float(config.get("wingspan_mm", 1200.0))
        semi_span = span / 2.0
        sweep_deg = float(config.get("wing_sweep_deg", 18.0))
        tip_x = 50.0 + semi_span * math.tan(math.radians(sweep_deg))

        for side, y_pos in (("right", semi_span), ("left", -semi_span)):
            components.append(
                {
                    "kind": "component",
                    "id": f"winglet-{side}",
                    "name": f"Winglet ({side.title()})",
                    "type": _LIFTING_SURFACE_TYPE,
                    "attach_to": "main-wing",
                    "mass": 30.0,
                    "transform": {
                        "position": {"x": round(tip_x, 1), "y": y_pos, "z": 0.0},
                        "rotation": {"roll": 90.0, "pitch": 0.0, "yaw": 0.0},
                    },
                    "envelope": {
                        "shape": "box",
                        "size_mm": {"x": root_chord, "y": 12.0, "z": fin_height},
                        "offset_mm": {"x": root_chord / 2.0, "y": 0.0, "z": fin_height / 2.0},
                    },
                    "parameters": {
                        "geometry": {
                            "mirror": False,
                            "symmetric": False,
                            "profiles": [
                                {
                                    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "chord": root_chord,
                                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "airfoil": airfoil,
                                },
                                {
                                    "position": {"x": 25.0, "y": fin_height, "z": 0.0},
                                    "chord": tip_chord,
                                    "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "airfoil": airfoil,
                                },
                            ],
                        }
                    },
                }
            )

    return components


def generate_airframe_components(config: dict[str, Any]) -> dict[str, Any]:
    """Generate complete airframe CAD structure bundle for a concept preset."""
    fuselage = build_fuselage_component(config)
    main_wing = build_main_wing_component(config)
    tails = build_tail_components(config)

    all_components = [fuselage, main_wing, *tails]
    member_ids = [str(c["id"]) for c in all_components]

    title = str(config.get("concept_title", "Aircraft Concept"))
    assembly = {
        "kind": "assembly",
        "id": "airframe-structure",
        "name": f"{title} Structure",
        "type": _STRUCTURAL_SYSTEM_TYPE,
        "members": member_ids,
    }

    parameters = {
        "concept_architecture": title,
        "wingspan": {"value": float(config.get("wingspan_mm", 1400.0)), "unit": "mm"},
        "wing_root_chord": {"value": float(config.get("wing_root_chord_mm", 210.0)), "unit": "mm"},
        "wing_tip_chord": {"value": float(config.get("wing_tip_chord_mm", 130.0)), "unit": "mm"},
        "fuselage_length": {"value": float(config.get("fuselage_length_mm", 850.0)), "unit": "mm"},
        "fuselage_diameter": {"value": float(config.get("fuselage_diameter_mm", 130.0)), "unit": "mm"},
    }

    return {
        "components": all_components,
        "assemblies": [assembly],
        "parameters": parameters,
    }


__all__ = [
    "build_fuselage_component",
    "build_main_wing_component",
    "build_tail_components",
    "generate_airframe_components",
]
