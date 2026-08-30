"""Status bar widget displaying real-time project constraint evaluation status."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from setuav_studio.plugins.core.constraints import ConstraintChecker, ConstraintResult
from setuav_studio.plugins.core.ui.constraints_dialog import ManageConstraintsDialog
from setuav_studio.ui.icons import get_icon
from setuav_studio.ui.theme import status_color

if TYPE_CHECKING:
    from setuav_studio_sdk import StudioAPI


class ConstraintStatusWidget(QWidget):
    """Status bar indicator for real-time constraint validation."""

    def __init__(self, api: StudioAPI, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._api = api
        self._checker = ConstraintChecker()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self.btn = QToolButton(self)
        self.btn.setAutoRaise(True)
        self.btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn.clicked.connect(self._open_dialog)
        layout.addWidget(self.btn)

        self._api.on_project_changed(self._on_project_updated)
        self._api.on_project_content_changed(self._on_project_updated)
        self.refresh()

    def _open_dialog(self) -> None:
        if self._api.current_project is None:
            return
        dlg = ManageConstraintsDialog(self._api, self._checker, self)
        dlg.exec()
        self.refresh()

    def _on_project_updated(self, _project=None) -> None:
        self.refresh()

    def refresh(self) -> None:
        """Re-evaluate all constraints and update badge appearance."""
        if self._api.current_project is None:
            self.btn.setText("Constraints")
            self.btn.setIcon(get_icon("settings"))
            self.btn.setToolTip("No active project")
            self.btn.setEnabled(False)
            return

        self.btn.setEnabled(True)
        project_data = self._api.current_project.data
        constraints = project_data.get("constraints", [])
        if not constraints:
            self.btn.setText("Constraints")
            self.btn.setIcon(get_icon("settings"))
            self.btn.setToolTip("No constraints configured (Click to add)")
            self.btn.setStyleSheet("")
            return

        results = self._checker.check_all(project_data)
        violations = [r for r in results if r.enabled and (not r.passed or r.error)]

        if not violations:
            self.btn.setText(f"✔ Constraints OK ({len(results)})")
            self.btn.setIcon(get_icon("success") if hasattr(get_icon, "__call__") else get_icon("settings"))
            self.btn.setStyleSheet(f"color: {status_color('success')}; font-weight: bold;")
            self.btn.setToolTip(f"All {len(results)} constraints satisfied.")
        else:
            errors = [v for v in violations if v.severity == "error" or v.error]
            warn_color = status_color("error") if errors else status_color("warning")
            self.btn.setText(f"⚠ {len(violations)} Violation{'s' if len(violations) > 1 else ''}")
            self.btn.setStyleSheet(f"color: {warn_color}; font-weight: bold;")

            tooltip_lines = ["<b>Constraint Violations:</b>"]
            for v in violations:
                msg = v.error or v.message or v.expression
                tooltip_lines.append(f"• <b>{v.name}</b>: {msg}")
            tooltip_lines.append("<br><i>Click to manage constraints</i>")
            self.btn.setToolTip("<br>".join(tooltip_lines))
