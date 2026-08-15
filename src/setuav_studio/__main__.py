import sys

from PySide6.QtWidgets import QApplication

from setuav_studio.plugins import PluginManager, StudioAPI
from setuav_studio.project_plugin import ProjectPlugin
from setuav_studio.shell import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    api = StudioAPI()
    window = MainWindow(api)

    plugin_manager = PluginManager(api)
    plugin_manager.activate(ProjectPlugin())

    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
