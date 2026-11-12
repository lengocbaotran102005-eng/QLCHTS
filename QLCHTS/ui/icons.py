"""Nạp biểu tượng SVG trong ``assets/icons`` và tô màu theo giao diện sáng/tối."""
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

import config


@lru_cache(maxsize=None)
def _svg_source(name: str) -> str:
    path = config.ICONS_DIR / f"{name}.svg"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""  # thiếu tệp icon -> trả về icon trống, không làm dừng chương trình


def icon_pixmap(name: str, color: str, size: int = 48) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    source = _svg_source(name)
    if not source:
        return pixmap
    renderer = QSvgRenderer(QByteArray(source.replace("currentColor", color).encode("utf-8")))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


_icon_cache: dict[tuple, QIcon] = {}


def make_icon(name: str, color: str, checked_color: str | None = None) -> QIcon:
    """Tạo QIcon từ SVG; ``checked_color`` dùng cho trạng thái được chọn (nút điều hướng)."""
    key = (name, color, checked_color)
    if key not in _icon_cache:
        icon = QIcon()
        icon.addPixmap(icon_pixmap(name, color), QIcon.Mode.Normal, QIcon.State.Off)
        if checked_color:
            icon.addPixmap(icon_pixmap(name, checked_color), QIcon.Mode.Normal, QIcon.State.On)
            icon.addPixmap(icon_pixmap(name, checked_color), QIcon.Mode.Active, QIcon.State.On)
        _icon_cache[key] = icon
    return _icon_cache[key]
