"""Layer model representing a logical group of objects in the 3D viewport."""

from __future__ import annotations

from dataclasses import dataclass

# Layers the viewport itself provides: objects without a layer, and the CG markers.
DEFAULT_LAYER = "default"
MASS_LAYER = "mass"


@dataclass
class Layer:
    """A named layer grouping scene objects in the viewport.

    Attributes:
        layer_id: Unique identifier of the layer (e.g. 'geometry', 'manufacturing').
        name: Human-readable display name for the layer.
        visible: Whether objects in this layer are rendered.
    """

    layer_id: str
    name: str = ""
    visible: bool = True
