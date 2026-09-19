"""Layer model representing a logical group of objects in the 3D viewport."""

from __future__ import annotations

from dataclasses import dataclass


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
