"""Renderer-neutral 2D scene primitives and project geometry adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Point2D = tuple[float, float]
ColorValue = str | tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class View2DPath:
    """A projected polyline or closed outline in scene coordinates."""

    id: str
    points: tuple[Point2D, ...]
    color: ColorValue = "#7f9bb5"
    width: float = 1.2
    closed: bool = False
    fill_alpha: int = 0
    layer: str = "geometry"
    tooltip: str = ""


@dataclass(frozen=True, slots=True)
class View2DMarker:
    """A selectable point/marker rendered above scene paths."""

    id: str
    position: Point2D
    label: str = ""
    tooltip: str = ""
    color: ColorValue = "#4c9aff"
    radius: float = 4.0
    symbol: str = "dot"
    layer: str = "markers"


@dataclass
class View2DScene:
    """A reusable projection scene assembled by domain plugins."""

    title: str = "2D View"
    x_label: str = "X"
    y_label: str = "Y"
    units: str = "mm"
    x_bounds: tuple[float, float] | None = None
    y_bounds: tuple[float, float] | None = None
    paths: list[View2DPath] = field(default_factory=list)
    markers: list[View2DMarker] = field(default_factory=list)
    legend: list[tuple[str, ColorValue]] = field(default_factory=list)

    def clear(self) -> None:
        self.paths.clear()
        self.markers.clear()
        self.legend.clear()

    def add_path(
        self,
        path_id: str,
        points: list[Point2D] | tuple[Point2D, ...],
        *,
        color: ColorValue = "#7f9bb5",
        width: float = 1.2,
        closed: bool = False,
        fill_alpha: int = 0,
        layer: str = "geometry",
        tooltip: str = "",
    ) -> View2DPath:
        path = View2DPath(
            id=path_id,
            points=tuple(points),
            color=color,
            width=width,
            closed=closed,
            fill_alpha=max(0, min(255, int(fill_alpha))),
            layer=layer,
            tooltip=tooltip,
        )
        if len(path.points) >= 2:
            self.paths.append(path)
        return path

    def add_marker(
        self,
        marker_id: str,
        position: Point2D,
        *,
        label: str = "",
        tooltip: str = "",
        color: ColorValue = "#4c9aff",
        radius: float = 4.0,
        symbol: str = "dot",
        layer: str = "markers",
    ) -> View2DMarker:
        marker = View2DMarker(
            id=marker_id,
            position=(float(position[0]), float(position[1])),
            label=label,
            tooltip=tooltip,
            color=color,
            radius=max(2.0, float(radius)),
            symbol=symbol,
            layer=layer,
        )
        self.markers.append(marker)
        return marker

    def add_legend(self, label: str, color: ColorValue) -> None:
        if label and not any(existing == label for existing, _ in self.legend):
            self.legend.append((label, color))

    def add_geometry(
        self,
        geometry_data: Any,
        *,
        axes: tuple[int, int] = (0, 1),
        color: ColorValue | None = None,
        width: float = 1.1,
        fill_alpha: int = 42,
        layer: str = "geometry",
    ) -> int:
        """Project the shared ``GeometryData`` into this scene.

        GeometryData is intentionally consumed through its renderer-neutral
        ``lofts``/``sections`` protocol. The 2D plugin therefore owns the
        projection of the aircraft geometry, while geometry-producing plugins
        only provide the source model through ``StudioAPI.build_geometry_data``.
        Coordinates remain in the project's millimetre body frame.
        """

        if geometry_data is None:
            return 0
        lofts = getattr(geometry_data, "lofts", ())
        count = 0
        for loft in lofts:
            component_id = str(getattr(loft, "component_id", "geometry"))
            path_color = color if color is not None else self._loft_color(loft)
            sections = getattr(loft, "sections", ())
            projected_points = [
                (float(point[axes[0]]), float(point[axes[1]]))
                for section in sections
                for point in getattr(section, "points", ())
                if len(point) > max(axes)
            ]
            # A single projected envelope is much easier to read than every
            # individual loft station. The source geometry remains available
            # in the 3D viewer; this view is intentionally a context outline.
            outline = _convex_hull(projected_points)
            if len(outline) >= 2:
                self.add_path(
                    f"{component_id}:envelope",
                    outline,
                    color=path_color,
                    width=width,
                    closed=len(outline) >= 3,
                    fill_alpha=fill_alpha,
                    layer=layer,
                    tooltip=component_id,
                )
                count += 1
            self.add_legend("Aircraft geometry", path_color)
        return count

    @staticmethod
    def _loft_color(loft: Any) -> tuple[float, float, float]:
        value = getattr(loft, "color", None)
        if isinstance(value, (tuple, list)) and len(value) >= 3:
            try:
                return (float(value[0]), float(value[1]), float(value[2]))
            except (TypeError, ValueError):
                pass
        return (0.42, 0.62, 0.76)


def _convex_hull(points: list[Point2D]) -> list[Point2D]:
    """Return a monotonic-chain hull for a projected geometry outline."""
    unique = sorted(set(points))
    if len(unique) <= 2:
        return unique

    def cross(origin: Point2D, first: Point2D, second: Point2D) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (
            second[0] - origin[0]
        )

    lower: list[Point2D] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[Point2D] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]
