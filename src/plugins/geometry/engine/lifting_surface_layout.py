"""Lifting-surface layout: the root and sections a wing is edited as, and its profiles.

A wing is a chain of sections from its root profile. Each section has a span, a sweep
measured on the sweep-location chord line, a dihedral, a twist increment and its tip
profile (chord and airfoil); a section's root profile is the tip of the section before it.
The profile stations that the geometry and aerodynamics read are always
built from this layout.

The planform of the whole wing (span, chords, area and the other driver values) and its
overall sweep, dihedral and twist are measured from the layout. A formula on one of them
changes the sections: span and chords proportionally, angles by the same amount on every
section, so cranks and kinks are kept.
"""

from __future__ import annotations

import math
from copy import deepcopy
from itertools import pairwise
from typing import Any

from setuav_studio.model.expression import get_expression

from .lifting_surface_driver_solver import (
    PLANFORM_PARAM_KEYS,
    compute_all_8_parameters,
    solve_8_parameter_driver,
)
from .lifting_surface_planform_engine import compute_planform_metrics

ANGLE_KEYS = ("sweep", "dihedral", "twist")
SECTION_ALIGNS = ("xz", "normal")
DEFAULT_ACTIVE_DRIVERS = ("span", "root_chord", "tip_chord")

# The order a wing's geometry is stored in: the wing-wide settings, the planform drivers,
# the layout from root to tip, the shaping of its airfoils and tip, and last the profile
# stations built from all of it.
GEOMETRY_KEY_ORDER = (
    "mirror",
    "sweep_location",
    "twist_location",
    "section_align",
    "planform",
    "root",
    "sections",
    "airfoil_shaping",
    "tip_treatment",
    "profiles",
)
_PLANFORM_KEY_ORDER = ("active_drivers", *PLANFORM_PARAM_KEYS, *ANGLE_KEYS)
_SECTION_KEY_ORDER = ("span", *ANGLE_KEYS, "tip")
_PROFILE_KEY_ORDER = ("chord", "airfoil")

# Span of a section appended at the tip relative to the current tip section, and its
# tip chord relative to the current tip chord.
_INSERTED_SPAN_RATIO = 0.8
_INSERTED_TIP_CHORD_RATIO = 0.7

# Changes below these are measurement noise, not edits to apply.
_LENGTH_TOLERANCE = 1e-6
_ANGLE_TOLERANCE = 1e-9


def build_profiles(
    root: dict[str, Any],
    sections: list[dict[str, Any]],
    sweep_location: float,
    section_align: str,
) -> list[dict[str, Any]]:
    """Profile stations of the wing, from its root along its sections.

    With ``section_align`` "normal" each station's airfoil plane is rolled to stand
    normal to the wing: by its section's dihedral at the root and tip, and by the
    mean of the two sections' dihedrals where they meet. With "xz" the airfoils
    stay parallel to the XZ plane.
    """
    if not sections:
        raise ValueError("A lifting surface needs at least one section")
    if section_align not in SECTION_ALIGNS:
        raise ValueError(f"Unknown lifting surface section alignment {section_align!r}")
    rolls = _station_rolls(sections) if section_align == "normal" else [0.0] * (len(sections) + 1)
    x = y = z = pitch = 0.0
    chord = _positive(root["chord"], "Root chord")
    profiles = [_profile(x, y, z, rolls[0], pitch, chord, root["airfoil"])]
    for number, section in enumerate(sections, start=1):
        span = _positive(section["span"], f"Section {number} span")
        tip_chord = _positive(section["tip"]["chord"], f"Section {number} tip chord")
        x += span * math.tan(math.radians(float(section["sweep"]))) - sweep_location * (
            tip_chord - chord
        )
        y += span
        z += span * math.tan(math.radians(float(section["dihedral"])))
        pitch += float(section["twist"])
        chord = tip_chord
        profiles.append(_profile(x, y, z, rolls[number], pitch, chord, section["tip"]["airfoil"]))
    return profiles


def _station_rolls(sections: list[dict[str, Any]]) -> list[float]:
    dihedrals = [float(section["dihedral"]) for section in sections]
    inner = [(a + b) / 2.0 for a, b in pairwise(dihedrals)]
    return [dihedrals[0], *inner, dihedrals[-1]]


def section_root(
    root: dict[str, Any], sections: list[dict[str, Any]], index: int
) -> dict[str, Any]:
    """The root profile (chord and airfoil) of section ``index``."""
    return root if index == 0 else sections[index - 1]["tip"]


def layout_planform(
    geometry: dict[str, Any], *, symmetric: bool, y_offset: float
) -> dict[str, float]:
    """The eight planform driver values and the overall angles of the wing."""
    # Rolling the airfoils does not change the planform.
    profiles = build_profiles(
        geometry["root"], geometry["sections"], geometry["sweep_location"], "xz"
    )
    metrics = compute_planform_metrics(
        profiles, geometry["sweep_location"], symmetric=symmetric, y_offset=y_offset
    )
    values = compute_all_8_parameters(
        metrics["span"],
        metrics["root_chord"],
        metrics["tip_chord"],
        is_symmetric=symmetric,
        y_offset=abs(y_offset),
    )
    values["sweep"] = metrics["sweep"]
    values["dihedral"] = metrics["dihedral"]
    values["twist"] = metrics["washout"]
    return values


def set_planform(
    geometry: dict[str, Any],
    targets: dict[str, float],
    *,
    symmetric: bool,
    y_offset: float,
) -> None:
    """Change the sections so the wing has the given planform driver values.

    The active drivers decide which values hold; the other drivers keep the current
    planform. The span is spread over the sections in proportion to their spans and the
    inner chords keep their place between the root and tip chords.
    """
    current = layout_planform(geometry, symmetric=symmetric, y_offset=y_offset)
    solved = solve_8_parameter_driver(
        geometry["planform"]["active_drivers"],
        {**current, **targets},
        current,
        is_symmetric=symmetric,
        y_offset=abs(y_offset),
    )
    panel_span = solved["span"] / 2.0 - abs(y_offset) if symmetric else solved["span"]
    _scale_spans(geometry["sections"], panel_span)
    _morph_chords(geometry["root"], geometry["sections"], solved["root_chord"], solved["tip_chord"])


def set_overall_angle(geometry: dict[str, Any], key: str, target: float) -> None:
    """Change the sections so the wing's root-to-tip ``key`` angle is ``target`` degrees.

    Sweep and dihedral move every section's slope by the same amount; twist adds the
    difference to the sections in proportion to their spans.
    """
    sections = geometry["sections"]
    total_span = sum(float(section["span"]) for section in sections)
    if key == "twist":
        delta = target - sum(float(section["twist"]) for section in sections)
        for section in sections:
            section["twist"] = float(section["twist"]) + delta * float(section["span"]) / total_span
        return
    if key not in ("sweep", "dihedral"):
        raise ValueError(f"Unknown lifting surface angle {key!r}")
    slope = sum(
        float(section["span"]) * math.tan(math.radians(float(section[key]))) for section in sections
    )
    delta = math.tan(math.radians(target)) - slope / total_span
    for section in sections:
        section[key] = math.degrees(math.atan(math.tan(math.radians(float(section[key]))) + delta))


def apply_wing_formulas(geometry: dict[str, Any], *, symmetric: bool, y_offset: float) -> None:
    """Carry the evaluated planform and angle formulas of the wing into its sections.

    A wing formula may not change a value that has its own formula on the root or a
    section; that would leave two formulas for one value.
    """
    planform = geometry["planform"]
    targets = {
        key: float(planform[key])
        for key in PLANFORM_PARAM_KEYS
        if get_expression(planform, key) is not None
    }
    if targets:
        before = _formula_values(geometry)
        set_planform(geometry, targets, symmetric=symmetric, y_offset=y_offset)
        _check_unchanged(before, geometry, ("span", "chord"), ", ".join(targets))
    for key in ANGLE_KEYS:
        if get_expression(planform, key) is None:
            continue
        before = _formula_values(geometry)
        set_overall_angle(geometry, key, float(planform[key]))
        _check_unchanged(before, geometry, (key,), key)


def derive_profiles(geometry: dict[str, Any], *, symmetric: bool, y_offset: float) -> None:
    """Apply the wing formulas and rebuild ``geometry["profiles"]`` from the layout.

    Nothing changes when the layout cannot be derived.
    """
    layout = {key: deepcopy(geometry[key]) for key in ("root", "sections", "planform")}
    layout["sweep_location"] = geometry["sweep_location"]
    apply_wing_formulas(layout, symmetric=symmetric, y_offset=y_offset)
    profiles = build_profiles(
        layout["root"], layout["sections"], layout["sweep_location"], geometry["section_align"]
    )
    _replace(geometry["root"], _ordered(layout["root"], _PROFILE_KEY_ORDER))
    for section, derived in zip(geometry["sections"], layout["sections"], strict=True):
        _replace(section["tip"], _ordered(derived["tip"], _PROFILE_KEY_ORDER))
        _replace(section, _ordered({**derived, "tip": section["tip"]}, _SECTION_KEY_ORDER))
    _replace(geometry["planform"], _ordered(geometry["planform"], _PLANFORM_KEY_ORDER))
    geometry["profiles"] = profiles
    _replace(geometry, _ordered(geometry, GEOMETRY_KEY_ORDER))


def split_section(root: dict[str, Any], sections: list[dict[str, Any]], index: int) -> None:
    """Split section ``index`` into two halves meeting at its mean chord."""
    section = sections[index]
    for key in ("span", "twist"):
        if get_expression(section, key) is not None:
            raise ValueError(
                f"Section {index + 1} {key} is a formula; remove it before splitting the section"
            )
    inner = deepcopy(section)
    inner["span"] = float(section["span"]) / 2.0
    inner["twist"] = float(section["twist"]) / 2.0
    base = section_root(root, sections, index)
    inner["tip"] = {
        "chord": (float(base["chord"]) + float(section["tip"]["chord"])) / 2.0,
        "airfoil": deepcopy(base["airfoil"]),
    }
    section["span"] = inner["span"]
    section["twist"] = inner["twist"]
    sections.insert(index, inner)


def append_section(sections: list[dict[str, Any]]) -> None:
    """Append a section at the tip, continuing the tip section's angles and airfoil."""
    last = sections[-1]
    sections.append(
        {
            "span": float(last["span"]) * _INSERTED_SPAN_RATIO,
            "sweep": float(last["sweep"]),
            "dihedral": float(last["dihedral"]),
            "twist": float(last["twist"]),
            "tip": {
                "chord": float(last["tip"]["chord"]) * _INSERTED_TIP_CHORD_RATIO,
                "airfoil": deepcopy(last["tip"]["airfoil"]),
            },
        }
    )


def delete_section(sections: list[dict[str, Any]], index: int) -> None:
    """Delete section ``index``; the sections after it move inboard."""
    if len(sections) == 1:
        raise ValueError("A lifting surface needs at least one section")
    del sections[index]


def _ordered(values: dict[str, Any], order: tuple[str, ...]) -> dict[str, Any]:
    """``values`` with the keys of ``order`` first, in that order, and formulas last."""
    rank = {key: index for index, key in enumerate(order)}
    return dict(
        sorted(
            values.items(),
            key=lambda item: (item[0] == "_expressions", rank.get(item[0], len(order))),
        )
    )


def _replace(target: dict[str, Any], values: dict[str, Any]) -> None:
    """Give ``target`` the contents of ``values``, keeping the dict others hold."""
    target.clear()
    target.update(values)


def _profile(
    x: float, y: float, z: float, roll: float, pitch: float, chord: float, airfoil: Any
) -> dict[str, Any]:
    return {
        "position": {"x": x, "y": y, "z": z},
        "chord": chord,
        "rotation": {"x": roll, "y": pitch, "z": 0.0},
        "airfoil": deepcopy(airfoil),
    }


def _positive(value: Any, label: str) -> float:
    number = float(value)
    if number <= 0.0:
        raise ValueError(f"{label} must be positive, got {number}")
    return number


def _scale_spans(sections: list[dict[str, Any]], panel_span: float) -> None:
    total = sum(float(section["span"]) for section in sections)
    if abs(panel_span - total) <= _LENGTH_TOLERANCE:
        return
    ratio = _positive(panel_span, "Wing panel span") / total
    for section in sections:
        section["span"] = float(section["span"]) * ratio


def _morph_chords(
    root: dict[str, Any], sections: list[dict[str, Any]], root_chord: float, tip_chord: float
) -> None:
    old_root = float(root["chord"])
    old_tip = float(sections[-1]["tip"]["chord"])
    if abs(old_root - root_chord) <= _LENGTH_TOLERANCE and abs(old_tip - tip_chord) <= (
        _LENGTH_TOLERANCE
    ):
        return
    old_delta = old_tip - old_root
    for section in sections[:-1]:
        chord = float(section["tip"]["chord"])
        if abs(old_delta) > _LENGTH_TOLERANCE:
            share = (chord - old_root) / old_delta
            section["tip"]["chord"] = root_chord + share * (tip_chord - root_chord)
        else:
            section["tip"]["chord"] = chord * root_chord / old_root
    root["chord"] = root_chord
    sections[-1]["tip"]["chord"] = tip_chord


def _formula_values(geometry: dict[str, Any]) -> dict[tuple[str, ...], tuple[str, float]]:
    """The root and section values that carry their own formula, with those values."""
    values: dict[tuple[str, ...], tuple[str, float]] = {}
    if get_expression(geometry["root"], "chord") is not None:
        values[("root", "chord")] = ("chord", float(geometry["root"]["chord"]))
    for number, section in enumerate(geometry["sections"], start=1):
        for key in ("span", *ANGLE_KEYS):
            if get_expression(section, key) is not None:
                values[(f"section {number}", key)] = (key, float(section[key]))
        if get_expression(section["tip"], "chord") is not None:
            values[(f"section {number} tip", "chord")] = ("chord", float(section["tip"]["chord"]))
    return values


def _check_unchanged(
    before: dict[tuple[str, ...], tuple[str, float]],
    geometry: dict[str, Any],
    kinds: tuple[str, ...],
    wing_value: str,
) -> None:
    after = _formula_values(geometry)
    tolerance = _ANGLE_TOLERANCE if kinds[0] in ANGLE_KEYS else _LENGTH_TOLERANCE
    for place, (kind, value) in before.items():
        if kind in kinds and abs(after[place][1] - value) > tolerance:
            raise ValueError(
                f"The wing {wing_value} formula would change the {place[0]} {place[1]} formula; "
                "keep the formula on only one of them"
            )
