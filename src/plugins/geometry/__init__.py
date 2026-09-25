"""Geometry Plugin package."""

from . import editors, engine
from .plugin import GeometryPlugin
from .scene_controller import GeometrySceneController

PLUGIN = GeometryPlugin()

MountFrame = engine.mount.MountFrame
MountTarget = engine.mount.MountTarget


def get_geometry(project: object = None) -> object:
    """Return geometry data for *project*, or the current project if omitted.

    Returns an empty GeometryData when the geometry plugin is inactive or no
    project is open.  Safe to call from other plugins via an optional import::

        try:
            from plugins.geometry import get_geometry
        except ImportError:
            get_geometry = None
    """
    return PLUGIN.get_geometry(project)


def get_mount_targets(project: object = None) -> list[object]:
    """Return available geometry mount targets for *project*."""
    return PLUGIN.get_mount_targets(project)


def compute_mount_point(
    project: object = None,
    target_id: str = "",
    position: str = "front",
    offset: dict[str, float] | None = None,
    orientation: dict[str, float] | None = None,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Compute local 3D mount point and orientation for a target."""
    return PLUGIN.compute_mount_point(project, target_id, position, offset, orientation)


def check_propeller_clearance(
    project: object = None,
    target_id: str = "",
    position: str = "front",
    offset: dict[str, float] | None = None,
    orientation: dict[str, float] | None = None,
    propeller_diameter: float = 250.0,
) -> dict[str, object]:
    """Check propeller clearance against project geometry."""
    return PLUGIN.check_propeller_clearance(
        project,
        target_id=target_id,
        position=position,
        offset=offset,
        orientation=orientation,
        propeller_diameter=propeller_diameter,
    )


def get_clearance_circle(
    mount_point: tuple[float, float, float],
    orientation: tuple[float, float, float],
    propeller_diameter: float,
    num_points: int = 36,
) -> tuple[tuple[float, float, float], ...]:
    """Generate 3D points representing the propeller clearance circle."""
    return PLUGIN.get_clearance_circle(
        mount_point=mount_point,
        orientation=orientation,
        propeller_diameter=propeller_diameter,
        num_points=num_points,
    )


__all__ = [
    "PLUGIN",
    "GeometryPlugin",
    "GeometrySceneController",
    "MountFrame",
    "MountTarget",
    "check_propeller_clearance",
    "compute_mount_point",
    "editors",
    "engine",
    "get_clearance_circle",
    "get_geometry",
    "get_mount_targets",
]
