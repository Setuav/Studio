"""Visual primitives for 3D viewport overlays and annotations."""

from __future__ import annotations

from dataclasses import dataclass

from typing import Literal

Point3D = tuple[float, float, float]
ColorRGB = tuple[float, float, float]
ColorRGBA = tuple[float, float, float, float] | tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class BoxPrimitive:
    """A 3D axis-aligned or oriented bounding box."""

    center: Point3D
    size: Point3D  # (dx, dy, dz)
    color: ColorRGBA = (0.2, 0.6, 1.0, 0.4)
    rotation: Point3D = (0.0, 0.0, 0.0)  # roll, pitch, yaw in degrees
    wireframe: bool = True
    solid: bool = True


@dataclass(frozen=True, slots=True)
class CylinderPrimitive:
    """A 3D cylinder defined by two endpoints and a radius."""

    start: Point3D
    end: Point3D
    radius: float
    color: ColorRGBA = (0.2, 0.2, 0.2, 0.9)
    wireframe: bool = False
    solid: bool = True
    segments: int = 24


@dataclass(frozen=True, slots=True)
class PlanePrimitive:
    """A bounded flat plane or cut section in 3D space."""

    center: Point3D
    normal: Point3D = (1.0, 0.0, 0.0)
    width: float = 200.0
    height: float = 200.0
    color: ColorRGBA = (1.0, 0.5, 0.0, 0.4)
    wireframe: bool = True
    solid: bool = True


@dataclass(frozen=True, slots=True)
class RingPrimitive:
    """A circular outline wire loop."""

    center: Point3D
    normal: Point3D = (1.0, 0.0, 0.0)
    radius: float = 50.0
    color: ColorRGBA = (1.0, 0.5, 0.0, 1.0)
    segments: int = 36


@dataclass(frozen=True, slots=True)
class LineSegmentsPrimitive:
    """Arbitrary line segments in 3D space."""

    lines: tuple[tuple[Point3D, Point3D], ...]
    color: ColorRGBA = (1.0, 1.0, 1.0, 1.0)


@dataclass(frozen=True, slots=True)
class TrianglesPrimitive:
    """Arbitrary 3D triangles forming a solid surface or faceted mesh."""

    triangles: tuple[tuple[Point3D, Point3D, Point3D], ...]
    color: ColorRGBA = (0.7, 0.75, 0.8, 0.7)
    solid: bool = True


@dataclass(frozen=True, slots=True)
class LoftPrimitive:
    """Ordered closed 3D section loops forming a lofted visual body."""

    sections: tuple[tuple[Point3D, ...], ...]
    color: ColorRGBA = (1.0, 0.15, 0.15, 0.40)
    interpolation: Literal["linear", "smooth"] = "smooth"
    parameterization: Literal["uniform", "chord_length", "centripetal"] = "centripetal"
    station_spacing: float = 10.0
    closed_ends: bool = True
    wireframe: bool = True
    solid: bool = True


VisualPrimitive = (
    BoxPrimitive
    | CylinderPrimitive
    | PlanePrimitive
    | RingPrimitive
    | LineSegmentsPrimitive
    | TrianglesPrimitive
    | LoftPrimitive
)

