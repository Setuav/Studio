"""Geometric data structures and containers for the 3D viewport."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from .primitives import (
    FeatureWire,
    Point3D,
    VisualPrimitive,
)


@dataclass(frozen=True, slots=True)
class Section:
    """A closed, ordered profile loop in three-dimensional space."""

    points: tuple[Point3D, ...]
    is_station: bool = True


@dataclass(frozen=True, slots=True)
class LoftGeometry:
    """Ordered section loops forming one lofted display object.

    ``component_id`` names the loft; ``owner_id`` is the project component it
    draws (empty for a loft drawn for a bare primitive). ``feature_wire`` is how
    the feature wireframe outlines it: every section ring, only the end rings, or
    the chord lines of a tip cap.
    """

    component_id: str
    sections: tuple[Section, ...]
    owner_id: str = ""
    feature_wire: FeatureWire = "sections"
    interpolation: Literal["linear", "smooth"] = "smooth"
    station_spacing: float = 10.0
    closed_ends: bool = True
    hinge_points: tuple[Point3D, ...] = ()


@dataclass(frozen=True, slots=True)
class EnvelopeWireGeometry:
    """Wireframe line segments for a component envelope in world coordinates."""

    component_id: str
    lines: tuple[tuple[Point3D, Point3D], ...] = ()


@dataclass(frozen=True, slots=True)
class GeometryData:
    """Renderer-neutral geometry container passed to the OpenGL viewer."""

    lofts: tuple[LoftGeometry, ...] = ()
    envelopes: tuple[EnvelopeWireGeometry, ...] = ()
    primitives: tuple[VisualPrimitive, ...] = ()

    def points(self) -> Iterator[Point3D]:
        for loft in self.lofts:
            for section in loft.sections:
                yield from section.points
