from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal


Point3D = tuple[float, float, float]
ColorRGB = tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class Section:
    """A closed, ordered profile loop in three-dimensional space."""

    points: tuple[Point3D, ...]


@dataclass(frozen=True, slots=True)
class LoftGeometry:
    """Ordered section loops forming one lofted display object."""

    component_id: str
    sections: tuple[Section, ...]
    color: ColorRGB = (0.50, 0.77, 0.82)
    interpolation: Literal["linear", "smooth"] = "smooth"
    station_spacing: float = 10.0
    closed_ends: bool = True


@dataclass(frozen=True, slots=True)
class GeometryData:
    """Renderer-neutral geometry passed to the OpenGL viewer."""

    lofts: tuple[LoftGeometry, ...] = ()

    def points(self) -> Iterator[Point3D]:
        for loft in self.lofts:
            for section in loft.sections:
                yield from section.points
