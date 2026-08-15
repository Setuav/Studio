import sys

from PySide6.QtWidgets import QApplication

from setuav_studio.shell import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
