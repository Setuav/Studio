"""Electronic Speed Controller (ESC) component property editor."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from plugins.electrical_propulsion.models.esc import ESCModel
from setuav_studio.api import StudioAPI
from setuav_studio.ui.editor.component import BaseComponentEditor


class EscEditor(BaseComponentEditor):
    """Property editor for ESCs and motor controllers (org.setuav.core:esc)."""

    FIELDS = ESCModel.get_scalar_fields()

    def __init__(
        self, api: StudioAPI, component: dict[str, Any], parent: QWidget | None = None
    ) -> None:
        super().__init__(api, component, parameter_fields=self.FIELDS, parent=parent)
