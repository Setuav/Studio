"""Propulsion System domain entity model."""

from __future__ import annotations

from setuav_studio.model import Component


class PropulsionSystemModel(Component):
    """Domain model for Propulsion System root component (org.setuav.core:propulsion-system)."""

    COMPONENT_TYPE = "org.setuav.core:propulsion-system"
