from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from setuav_studio.ui.icons import application_icon


def application_version() -> str:
    """Return the installed Setuav Studio version."""
    try:
        return distribution_version("setuav-studio")
    except PackageNotFoundError:
        return "development"


class AboutDialog(QDialog):
    """Display concise application, version, and license information."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aboutDialog")
        self.setWindowTitle("About")
        self.setWindowIcon(application_icon())
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(12)

        logo = QLabel(self)
        logo.setObjectName("aboutLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(application_icon().pixmap(128, 128))
        layout.addWidget(logo)

        title = QLabel("Setuav Studio", self)
        title.setObjectName("aboutTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = title.font()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        version = QLabel(f"Version {application_version()}", self)
        version.setObjectName("aboutVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        description = QLabel(
            "Plugin-based desktop application for parametric UAV design and analysis.",
            self,
        )
        description.setObjectName("aboutDescription")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        layout.addWidget(description)

        license_notice = QLabel(
            "Copyright © 2026 Setuav contributors\nLicensed under the MIT License.",
            self,
        )
        license_notice.setObjectName("aboutLicense")
        license_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(license_notice)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
