"""Điểm khởi động phần mềm quản lý cửa hàng trang sức BẢO TRÂN JEWELRY.

Cách chạy: mở dự án trong PyCharm và nhấn Run tệp này, hoặc chạy lệnh ``python main.py``.
Chương trình mở một cửa sổ ứng dụng desktop (PySide6); không dùng web server hay trình duyệt.
"""
import logging
import os
import sqlite3
import sys
import traceback
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))  # bảo đảm import được các gói của dự án dù chạy từ thư mục nào

os.environ.setdefault("QT_API", "pyside6")  # để Matplotlib dùng PySide6

log = logging.getLogger("baotran")


def setup_logging() -> None:
    """Ghi nhật ký ra Console của PyCharm (hiển thị tiếng Việt có dấu)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        datefmt="%H:%M:%S")


def check_dependencies() -> bool:
    missing = []
    for module, package in (("PySide6", "PySide6-Essentials"), ("matplotlib", "matplotlib"), ("PIL", "Pillow")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        print("=" * 72)
        print("THIẾU THƯ VIỆN:", ", ".join(missing))
        print("Hãy mở Terminal trong PyCharm (Alt+F12) và chạy lệnh:")
        print("    pip install -r requirements.txt")
        print("=" * 72)
        return False
    return True


def install_exception_hook() -> None:
    """Lỗi không lường trước được ghi ra Console và hiển thị hộp thoại, không làm đóng chương trình."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    def hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.error("Lỗi không mong muốn:\n%s", text)
        if QApplication.instance() is not None:
            box = QMessageBox(QMessageBox.Icon.Critical, "Lỗi không mong muốn",
                              "Đã xảy ra lỗi ngoài dự kiến. Chương trình vẫn tiếp tục hoạt động.\n"
                              "Chi tiết lỗi đã được ghi trong Console.")
            box.setDetailedText(text)
            box.exec()

    sys.excepthook = hook


def main() -> int:
    setup_logging()
    if not check_dependencies():
        return 1

    from PySide6.QtCore import QLocale, Qt
    from PySide6.QtGui import QFont, QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    import config
    from app_context import AppContext
    from database import Database
    from seed_data import seed_sample_data
    from ui.theme import ThemeManager
    from utils.image_utils import ensure_default_images

    if sys.platform == "win32":
        try:  # để Windows hiển thị đúng biểu tượng của ứng dụng trên thanh Taskbar
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BaoTran.Jewelry.Manager")
        except (AttributeError, OSError):
            pass

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(config.APP_VERSION)
    app.setStyle("Fusion")
    QLocale.setDefault(QLocale(QLocale.Language.Vietnamese, QLocale.Country.Vietnam))
    install_exception_hook()

    # 1. Ảnh mặc định/ảnh mẫu (tự vẽ bằng Pillow nếu thư mục assets/images chưa có)
    ensure_default_images()
    if config.LOGO_IMAGE.exists():
        app.setWindowIcon(QIcon(str(config.LOGO_IMAGE)))

    # 2. Kết nối SQLite, tạo bảng nếu chưa có, thêm dữ liệu mẫu đúng một lần
    db = Database(config.DB_PATH)
    try:
        db.initialize()
        if seed_sample_data(db):
            log.info("Lần chạy đầu tiên: đã thêm dữ liệu mẫu vào %s", config.DB_PATH.name)
    except sqlite3.Error as exc:
        log.exception("Không thể khởi tạo CSDL")
        QMessageBox.critical(None, "Lỗi cơ sở dữ liệu",
                             f"Không thể mở hoặc khởi tạo cơ sở dữ liệu SQLite:\n{config.DB_PATH}\n\n"
                             f"Chi tiết: {exc}\n\nHãy kiểm tra thư mục dự án có quyền ghi và tệp CSDL không bị "
                             "chương trình khác khóa.")
        return 1

    # 3. Dịch vụ nghiệp vụ + giao diện
    ctx = AppContext.create(db)
    theme = ThemeManager(app)
    font = QFont(theme.font_family)
    font.setPointSizeF(10)
    app.setFont(font)
    ctx.theme = theme
    theme.apply(ctx.settings.theme)

    from ui.main_window import MainWindow

    window = MainWindow(ctx)
    window.show_initial()
    log.info("Đã mở cửa sổ %s – CSDL: %s", config.APP_NAME, config.DB_PATH)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
