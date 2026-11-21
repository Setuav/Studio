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
        layer_id: Unique identifier of the layer (e.g. 'geometry', 'structures').
        name: Human-readable display name for the layer.
        visible: Whether objects in this layer are rendered.
        on_top: Whether the layer's overlay lines are drawn over the model, so a
            marker inside it (such as the center of gravity) stays visible.
    """

    layer_id: str
    name: str = ""
    visible: bool = True
    on_top: bool = False
