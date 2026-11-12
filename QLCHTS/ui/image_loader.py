"""Nạp ảnh sản phẩm cho giao diện: ảnh cục bộ, ảnh từ URL (tải nền) và ảnh mặc định khi lỗi."""
import logging

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap

import config
from utils.image_utils import download_image, is_url, resolve_image_file
from ui.widgets import run_in_background

log = logging.getLogger(__name__)


class ImageLoader(QObject):
    """Bộ nạp ảnh dùng chung, có bộ nhớ đệm; ảnh lỗi/thiếu được thay bằng ảnh mặc định."""

    image_ready = Signal(str)  # phát ra khi một ảnh URL vừa tải xong
    _instance: "ImageLoader | None" = None

    def __init__(self):
        super().__init__()
        self._cache: dict[tuple, QPixmap] = {}
        self._pending: set[str] = set()
        self._failed: set[str] = set()

    @classmethod
    def instance(cls) -> "ImageLoader":
        if cls._instance is None:
            cls._instance = ImageLoader()
        return cls._instance

    def pixmap(self, source: str, width: int, height: int, radius: int = 12) -> QPixmap:
        source = (source or "").strip()
        key = (source, width, height, radius)
        if key in self._cache:
            return self._cache[key]
        path = resolve_image_file(source)
        if path is None and is_url(source):
            self.request(source)
        original = QPixmap(str(path)) if path else QPixmap()
        is_default = original.isNull()
        if is_default:
            original = QPixmap(str(config.DEFAULT_IMAGE))
        result = self._cover(original, width, height, radius)
        # Không lưu đệm ảnh mặc định của URL đang tải để lần sau hiển thị ảnh thật
        if not (is_default and is_url(source) and source not in self._failed):
            self._cache[key] = result
        return result

    def request(self, url: str) -> None:
        if url in self._pending or url in self._failed:
            return
        self._pending.add(url)
        run_in_background(self._download, url, on_success=self._on_downloaded)

    @staticmethod
    def _download(url: str) -> tuple[str, bool, str]:
        try:
            download_image(url)
            return url, True, ""
        except Exception as exc:  # noqa: BLE001 – mất mạng, URL sai... không được làm dừng chương trình
            return url, False, str(exc)

    def _on_downloaded(self, result) -> None:
        url, ok, message = result
        self._pending.discard(url)
        if not ok:
            self._failed.add(url)
            log.warning("Không tải được ảnh %s: %s", url, message)
        self._cache = {k: v for k, v in self._cache.items() if k[0] != url}
        self.image_ready.emit(url)

    def forget(self, source: str) -> None:
        """Xóa ảnh khỏi bộ nhớ đệm (khi người dùng đổi ảnh sản phẩm)."""
        self._failed.discard(source)
        self._cache = {k: v for k, v in self._cache.items() if k[0] != source}

    @staticmethod
    def _cover(original: QPixmap, width: int, height: int, radius: int) -> QPixmap:
        """Cắt ảnh vừa khung (kiểu 'cover') và bo góc."""
        ratio = 2.0  # vẽ ở độ phân giải gấp đôi cho màn hình HiDPI
        target = QPixmap(int(width * ratio), int(height * ratio))
        target.fill(Qt.GlobalColor.transparent)
        if original.isNull():
            return target
        scaled = original.scaled(target.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
        x = (scaled.width() - target.width()) // 2
        y = (scaled.height() - target.height()) // 2
        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, target.width(), target.height()), radius * ratio, radius * ratio)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled, x, y, target.width(), target.height())
        painter.end()
        target.setDevicePixelRatio(ratio)
        return target
