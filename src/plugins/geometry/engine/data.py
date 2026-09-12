from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from setuav_studio_sdk.primitives import (
    BoxPrimitive,
    ColorRGB,
    ColorRGBA,
    CylinderPrimitive,
    LineSegmentsPrimitive,
    LoftPrimitive,
    PlanePrimitive,
    Point3D,
    RingPrimitive,
    TrianglesPrimitive,
    VisualPrimitive,
)


@dataclass(frozen=True, slots=True)
class Section:
    """A closed, ordered profile loop in three-dimensional space."""

    points: tuple[Point3D, ...]
    is_station: bool = True


@dataclass(frozen=True, slots=True)
class LoftGeometry:
    """Ordered section loops forming one lofted display object."""

    component_id: str
    sections: tuple[Section, ...]
    color: ColorRGB = (0.50, 0.77, 0.82)
    interpolation: Literal["linear", "smooth"] = "smooth"
    parameterization: Literal["uniform", "chord_length", "centripetal"] = "centripetal"
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
    """Renderer-neutral geometry passed to the OpenGL viewer."""

    lofts: tuple[LoftGeometry, ...] = ()
    envelopes: tuple[EnvelopeWireGeometry, ...] = ()
    primitives: tuple[VisualPrimitive, ...] = ()

    def points(self) -> Iterator[Point3D]:
        for loft in self.lofts:
            for section in loft.sections:
                yield from section.points
