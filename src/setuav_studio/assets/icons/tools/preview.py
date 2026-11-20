"""Render icons from ``iso.py`` into a PNG to look at them before writing.

    python preview.py OUT.png NAME [NAME ...]

Each icon is drawn large and at the 16, 20 and 24 px sizes the application uses,
on the dark theme background, without writing any SVG.
"""

import argparse
import importlib.util
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


def _load_generator():
    spec = importlib.util.spec_from_file_location("iso", Path(__file__).with_name("iso.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


iso = _load_generator()
_LARGE, _CELL, _ROW = 160, 200, 230


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("names", nargs="+")
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    image = QImage(_CELL * len(args.names), _ROW, QImage.Format.Format_ARGB32)
    image.fill(QColor("#242424"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for index, name in enumerate(args.names):
        renderer = QSvgRenderer(QByteArray(iso.ICONS[name]().svg().encode()))
        x = index * _CELL + (_CELL - _LARGE) // 2
        renderer.render(painter, QRectF(x, 8, _LARGE, _LARGE))
        for offset, size in ((0, 16), (40, 20), (84, 24)):
            renderer.render(painter, QRectF(x + offset, 176, size, size))
        painter.setPen(QColor("#e0e0e0"))
        painter.setFont(QFont("Sans", 8))
        painter.drawText(QRectF(index * _CELL, 206, _CELL, 20), Qt.AlignmentFlag.AlignHCenter, name)
    painter.end()
    image.save(str(args.out))
    del app


if __name__ == "__main__":
    main()
