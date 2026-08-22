import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from setuav_studio.plugin_system import PluginManager, StudioAPI
from setuav_studio.ui.log_buffer import install_log_buffer
from setuav_studio.plugins.core import CorePlugin
from setuav_studio.plugins.core.settings import StudioSettings
from setuav_studio.ui.theme import apply_theme
from setuav_studio.shell import MainWindow


def _configure_logging(verbose: bool = False) -> None:
    log_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "setuav-studio.log"

    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)


def _parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="setuav-studio")
    parser.add_argument(
        "project",
        nargs="?",
        help="project folder, project.json, or .suav file to open",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable debug-level logging",
    )
    return parser.parse_args(argv)


def _configure_opengl() -> None:
    """Configure one conservative shared format for Qt and VTK viewers."""
    QApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts,
        True,
    )
    surface_format = QSurfaceFormat()
    surface_format.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    surface_format.setVersion(3, 3)
    surface_format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    surface_format.setDepthBufferSize(24)
    surface_format.setStencilBufferSize(8)
    surface_format.setSamples(0)
    surface_format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    QSurfaceFormat.setDefaultFormat(surface_format)


def main() -> int:
    arguments = _parse_arguments(sys.argv[1:])
    _configure_logging(arguments.verbose)
    install_log_buffer(logging.DEBUG if arguments.verbose else logging.INFO)
    logging.getLogger(__name__).info("Setuav Studio starting")
    _configure_opengl()
    app = QApplication([sys.argv[0]])
    app.setOrganizationName("Setware")
    app.setApplicationName("Setuav Studio")
    app.setQuitOnLastWindowClosed(True)
    settings = StudioSettings.load()
    apply_theme(app, settings.theme_mode)

    api = StudioAPI()
    window = MainWindow(api)

    plugin_manager = PluginManager(api)
    plugin_manager.activate(CorePlugin())
    plugin_issues = plugin_manager.discover()
    if plugin_issues:
        logger = logging.getLogger(__name__)
        for issue in plugin_issues:
            logger.warning("Plugin load issue (%s): %s", issue.source, issue.message)
        window.statusBar().showMessage(
            "Plugin load issues: "
            + "; ".join(f"{issue.source}: {issue.message}" for issue in plugin_issues)
        )

    window.restore_window_layout()
    if arguments.project:
        window.open_project(arguments.project)
    elif settings.reopen_last_project:
        window.open_last_project()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
