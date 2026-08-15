import argparse
import sys

from PySide6.QtWidgets import QApplication

from setuav_studio.plugin_system import PluginManager, StudioAPI
from setuav_studio.plugins.core import CorePlugin
from setuav_studio.plugins.geometry import GeometryPlugin
from setuav_studio.shell import MainWindow


def _parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="setuav-studio")
    parser.add_argument(
        "project",
        nargs="?",
        help="project folder, project.json, or .suav file to open",
    )
    return parser.parse_args(argv)


def main() -> int:
    arguments = _parse_arguments(sys.argv[1:])
    app = QApplication([sys.argv[0]])
    app.setOrganizationName("Setware")
    app.setApplicationName("Setuav Studio")

    api = StudioAPI()
    window = MainWindow(api)

    plugin_manager = PluginManager(api)
    plugin_manager.activate(CorePlugin())
    plugin_manager.activate(GeometryPlugin())

    window.restore_window_layout()
    if arguments.project:
        window.open_project(arguments.project)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
