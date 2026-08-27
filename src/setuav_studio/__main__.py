import argparse
import logging
import sys
from pathlib import Path


def _configure_logging(verbose: bool = False) -> None:
    from PySide6.QtCore import QStandardPaths

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
    internal_commands = parser.add_mutually_exclusive_group()
    internal_commands.add_argument(
        "--render-aero-3d",
        metavar="PAYLOAD",
        help=argparse.SUPPRESS,
    )
    internal_commands.add_argument(
        "--smoke-test-aero-3d",
        metavar="PAYLOAD",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def _run_internal_command(arguments: argparse.Namespace) -> int | None:
    payload_path = arguments.render_aero_3d or arguments.smoke_test_aero_3d
    if payload_path is None:
        return None

    from setuav_studio.plugins.aerodynamics.aero_3d_tool import render_native_snapshot

    render_native_snapshot(payload_path, show=arguments.render_aero_3d is not None)
    return 0


def _configure_opengl() -> None:
    """Configure one conservative shared format for Qt and VTK viewers."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QSurfaceFormat
    from PySide6.QtWidgets import QApplication

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
    internal_result = _run_internal_command(arguments)
    if internal_result is not None:
        return internal_result

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from setuav_studio.plugin_system import PluginManager, StudioAPI
    from setuav_studio.plugins.core import CorePlugin
    from setuav_studio.plugins.core.settings import StudioSettings
    from setuav_studio.shell import MainWindow
    from setuav_studio.ui.icons import application_icon
    from setuav_studio.ui.log_buffer import install_log_buffer
    from setuav_studio.ui.theme import apply_theme

    _configure_logging(arguments.verbose)
    install_log_buffer(logging.DEBUG if arguments.verbose else logging.INFO)
    logging.getLogger(__name__).info("Setuav Studio starting")
    _configure_opengl()
    app = QApplication([sys.argv[0]])
    app.setOrganizationName("Setware")
    app.setApplicationName("Setuav Studio")
    app.setWindowIcon(application_icon())
    app.setQuitOnLastWindowClosed(True)
    settings = StudioSettings.load()
    apply_theme(app, settings.theme_mode)

    api = StudioAPI()
    window = MainWindow(api)

    plugin_manager = PluginManager(api)
    window.bind_plugin_manager(plugin_manager)
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
        if arguments.smoke_test:
            return 1

    # Restore the top-level geometry before showing, but defer dock/workspace
    # restoration until the platform has created and exposed the native
    # window. VTK and QOpenGLWidget surfaces are unreliable before that point.
    window.restore_window_geometry()
    window.show()

    def finish_startup() -> None:
        window.restore_workspace_layout()
        if arguments.smoke_test:
            QTimer.singleShot(100, app.quit)
        elif arguments.project:
            window.open_project(arguments.project)
        elif settings.reopen_last_project:
            window.open_last_project()

    QTimer.singleShot(0, finish_startup)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
