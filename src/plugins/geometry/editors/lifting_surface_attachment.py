"""Attachment and symmetry handling for the Lifting Surface Editor."""

from __future__ import annotations


class AttachmentMixin:
    """Component attachment and symmetry handling for lifting surfaces."""

    def _update_mirror(self, is_mirrored: bool) -> None:
        if getattr(self, "_loading", False):
            return

        def change() -> None:
            if is_mirrored:
                self._geometry()["mirror"] = True
            else:
                self._geometry().pop("mirror", None)

        self._edit_component("Toggle bilateral wing mirror", change)
        if hasattr(self, "_refresh_planform_table"):
            self._refresh_planform_table()

    def _update_attach_to(self, new_parent: str | None) -> None:
        if getattr(self, "_loading", False):
            return

        def change() -> None:
            self._component["attach_to"] = new_parent

        self._edit_component("Change component attach_to", change)
