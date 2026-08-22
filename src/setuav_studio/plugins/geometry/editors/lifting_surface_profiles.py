"""Compatibility shim for lifting surface sections."""

from __future__ import annotations

from .lifting_surface_sections import SectionsMixin

ProfilesMixin = SectionsMixin

__all__ = ["ProfilesMixin", "SectionsMixin"]