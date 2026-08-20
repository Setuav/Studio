from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)


@dataclass(frozen=True)
class StudioSettings:
    reopen_last_project: bool = False
    recent_project_limit: int = 10
    pythrust_data_dir: str = ""

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
            pythrust_data_dir=str(
                settings.value("propulsion/pythrust_data_dir", "")
            ),
        )

    def save(self) -> None:
        settings = QSettings()
        settings.setValue("general/reopen_last_project", self.reopen_last_project)
        settings.setValue("general/recent_project_limit", self.recent_project_limit)
        settings.setValue("propulsion/pythrust_data_dir", self.pythrust_data_dir)
        settings.remove("appearance/theme")
        settings.remove("appearance/font_size")
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

        self.pythrust_dir_edit = QLineEdit(values.pythrust_data_dir)
        self.pythrust_dir_edit.setPlaceholderText(
            "Bundled with the pythrust package; or set PYTHRUST_DATA_DIR"
        )
        form.addRow("PyThrust data directory:", self.pythrust_dir_edit)

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
            pythrust_data_dir=self.pythrust_dir_edit.text().strip(),
        )


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes"}