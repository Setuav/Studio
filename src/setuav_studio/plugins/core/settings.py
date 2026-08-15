from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QAbstractSpinBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)


@dataclass(frozen=True)
class StudioSettings:
    reopen_last_project: bool = False
    recent_project_limit: int = 10
    theme: str = "dark"
    font_size: int = 10

    @classmethod
    def load(cls) -> "StudioSettings":
        settings = QSettings()
        return cls(
            reopen_last_project=_as_bool(
                settings.value("general/reopen_last_project", False)
            ),
            recent_project_limit=int(
                settings.value("general/recent_project_limit", 10)
            ),
            theme=_theme_value(settings.value("appearance/theme", "dark")),
            font_size=_font_size_value(settings.value("appearance/font_size", 10)),
        )

    def save(self) -> None:
        settings = QSettings()
        settings.setValue("general/reopen_last_project", self.reopen_last_project)
        settings.setValue("general/recent_project_limit", self.recent_project_limit)
        settings.setValue("appearance/theme", self.theme)
        settings.setValue("appearance/font_size", self.font_size)
        settings.remove("appearance/style")


class SettingsDialog(QDialog):
    def __init__(self, values: StudioSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.reopen_check = QCheckBox("Reopen the last project at startup")
        self.reopen_check.setChecked(values.reopen_last_project)
        form.addRow(self.reopen_check)

        self.recent_limit_spin = QSpinBox()
        self.recent_limit_spin.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.recent_limit_spin.setRange(1, 20)
        self.recent_limit_spin.setValue(values.recent_project_limit)
        form.addRow("Recent projects:", self.recent_limit_spin)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")
        index = self.theme_combo.findData(values.theme)
        self.theme_combo.setCurrentIndex(max(0, index))
        form.addRow("Theme:", self.theme_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.font_size_spin.setRange(8, 18)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.setValue(values.font_size)
        form.addRow("UI font size:", self.font_size_spin)

        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> StudioSettings:
        return StudioSettings(
            reopen_last_project=self.reopen_check.isChecked(),
            recent_project_limit=self.recent_limit_spin.value(),
            theme=str(self.theme_combo.currentData()),
            font_size=self.font_size_spin.value(),
        )


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes"}


def _theme_value(value: object) -> str:
    theme = str(value).lower()
    return theme if theme in {"light", "dark"} else "dark"


def _font_size_value(value: object) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return 10
    return min(max(size, 8), 18)
