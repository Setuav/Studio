"""Scene object representing a single entry in the 3D viewport scene graph."""

from __future__ import annotations

from dataclasses import dataclass, field

from setuav_studio_sdk.primitives import VisualPrimitive


@dataclass
class SceneObject:
    """A named, layered collection of visual primitives in the viewport.

    Each object has a unique ``object_id``, belongs to a ``layer``, carries an
    optional human-readable ``name``, and holds one or more SDK visual
    primitives that the renderer will draw.
    """

    object_id: str
    layer: str = "default"
    name: str = ""
    visible: bool = True
    primitives: list[VisualPrimitive] = field(default_factory=list)
