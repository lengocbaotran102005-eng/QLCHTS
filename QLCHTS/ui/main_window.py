"""Cửa sổ chính: thanh điều hướng bên trái, thanh tiêu đề và vùng nội dung các phân hệ."""
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import config
from ui.customers_page import CustomersPage
from ui.dashboard_page import DashboardPage
from ui.inventory_page import InventoryPage
from ui.invoices_page import InvoicesPage
from ui.pos_page import PosPage
from ui.products_page import ProductsPage
from ui.reports_page import ReportsPage
from ui.settings_page import SettingsPage
from ui.widgets import ask_confirm, handle_exception, theme

# (khóa, tên hiển thị, icon, lớp trang, nhóm)
NAVIGATION = [
    ("dashboard", "Tổng quan", "dashboard", DashboardPage, "TỔNG QUAN"),
    ("pos", "Bán hàng POS", "cart", PosPage, "BÁN HÀNG"),
    ("invoices", "Lịch sử giao dịch", "receipt", InvoicesPage, "BÁN HÀNG"),
    ("products", "Quản lý sản phẩm", "gem", ProductsPage, "QUẢN LÝ"),
    ("inventory", "Quản lý kho hàng", "package", InventoryPage, "QUẢN LÝ"),
    ("customers", "Quản lý khách hàng", "users", CustomersPage, "QUẢN LÝ"),
    ("reports", "Báo cáo thống kê", "chart", ReportsPage, "BÁO CÁO & HỆ THỐNG"),
    ("settings", "Cài đặt hệ thống", "settings", SettingsPage, "BÁO CÁO & HỆ THỐNG"),
]

WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        ctx.notify = self.show_status
        ctx.navigate = self.navigate
        self.setWindowTitle(config.APP_TITLE)
        if config.LOGO_IMAGE.exists():
            self.setWindowIcon(QIcon(str(config.LOGO_IMAGE)))
        self.setMinimumSize(1100, 660)
        self._fit_to_screen()

        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, QPushButton] = {}

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        content = QWidget()
        content.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_header())
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageStack")
        content_layout.addWidget(self.stack, 1)
        layout.addWidget(content, 1)
        self.setCentralWidget(central)

        for key, _label, _icon, page_class, _group in NAVIGATION:
            page = page_class(ctx)
            self.pages[key] = page
            self.stack.addWidget(page)

        self.statusBar().showMessage(f"Đã kết nối CSDL SQLite: {ctx.db.db_path}")
        self._setup_shortcuts()
        theme().theme_changed.connect(self._on_theme_changed)
        self._update_clock()
        self._clock = QTimer(self, interval=20_000)
        self._clock.timeout.connect(self._update_clock)
        self._clock.start()
        self.navigate("dashboard")

    # ------------------------------------------------------------------ dựng giao diện
    def _fit_to_screen(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1440, 880)
            return
        area = screen.availableGeometry()
        width, height = min(1480, area.width() - 40), min(920, area.height() - 40)
        self.resize(max(width, 1100), max(height, 660))
        self.move(area.x() + (area.width() - self.width()) // 2, area.y() + (area.height() - self.height()) // 2)
        self._start_maximized = area.width() < 1440 or area.height() < 860

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(248)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(3)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setFixedSize(44, 44)
        pixmap = QPixmap(str(config.LOGO_IMAGE))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(QSize(88, 88), Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
            logo.setScaledContents(True)
        names = QVBoxLayout()
        names.setSpacing(0)
        title = QLabel("BẢO TRÂN")
        title.setObjectName("BrandName")
        font = QFont(theme().serif_family)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        font.setPointSizeF(15)
        font.setBold(True)
        title.setFont(font)
        tagline = QLabel("JEWELRY • VÀNG BẠC ĐÁ QUÝ")
        tagline.setObjectName("BrandTagline")
        names.addWidget(title)
        names.addWidget(tagline)
        brand.addWidget(logo)
        brand.addLayout(names, 1)
        layout.addLayout(brand)
        layout.addSpacing(18)

        group = QButtonGroup(self)
        group.setExclusive(True)
        current_section = None
        for index, (key, label, icon, _page, section) in enumerate(NAVIGATION, start=1):
            if section != current_section:
                current_section = section
                caption = QLabel(section)
                caption.setObjectName("SidebarSection")
                layout.addWidget(caption)
            button = QPushButton(f"  {label}")
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIconSize(QSize(19, 19))
            button.setToolTip(f"{label}  (Ctrl+{index})")
            theme().bind_icon(button, icon, "sidebar_text", "sidebar_gold")
            button.clicked.connect(lambda _checked=False, k=key: self.navigate(k))
            group.addButton(button)
            layout.addWidget(button)
            self.nav_buttons[key] = button
        layout.addStretch()

        footer = QFrame()
        footer.setObjectName("SidebarFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(12, 10, 12, 10)
        footer_layout.setSpacing(2)
        footer_title = QLabel("Cơ sở dữ liệu SQLite")
        footer_title.setObjectName("SidebarFooterTitle")
        footer_text = QLabel(f"{config.DB_PATH.name}\nPhiên bản {config.APP_VERSION}")
        footer_text.setObjectName("SidebarFooterText")
        footer_layout.addWidget(footer_title)
        footer_layout.addWidget(footer_text)
        layout.addWidget(footer)
        return sidebar

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(70)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 10, 18, 10)
        layout.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.page_title = QLabel()
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("PageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        layout.addLayout(titles, 1)

        chip = QLabel("●  SQLite đã kết nối")
        chip.setObjectName("HeaderChip")
        chip.setToolTip(str(self.ctx.db.db_path))
        layout.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        self.clock_label = QLabel()
        self.clock_label.setObjectName("HeaderClock")
        layout.addWidget(self.clock_label)

        self.refresh_button = QToolButton()
        self.refresh_button.setToolTip("Tải lại dữ liệu trang hiện tại (F5)")
        self.refresh_button.setIconSize(QSize(20, 20))
        self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        theme().bind_icon(self.refresh_button, "refresh", "text_muted")
        self.refresh_button.clicked.connect(self.refresh_current)
        layout.addWidget(self.refresh_button)

        self.theme_button = QToolButton()
        self.theme_button.setIconSize(QSize(20, 20))
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_button)
        self._update_theme_button()
        return header

    def _setup_shortcuts(self) -> None:
        for index, (key, *_rest) in enumerate(NAVIGATION, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda k=key: self.navigate(k))
        QShortcut(QKeySequence("F5"), self).activated.connect(self.refresh_current)

    # ------------------------------------------------------------------ hành vi
    def show_initial(self) -> None:
        if getattr(self, "_start_maximized", False):
            self.showMaximized()
        else:
            self.show()

    def navigate(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.nav_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(page)
        self.page_title.setText(page.title)
        self.page_subtitle.setText(page.subtitle)
        self.refresh_current()

    def refresh_current(self) -> None:
        page = self.stack.currentWidget()
        if page is None:
            return
        try:
            page.refresh()
        except Exception as exc:  # noqa: BLE001 – không để lỗi đọc dữ liệu làm đóng chương trình
            handle_exception(self, exc)

    def show_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 6000)

    def toggle_theme(self) -> None:
        mode = theme().toggle()
        try:
            self.ctx.settings.set_theme(mode)
        except Exception as exc:  # noqa: BLE001
            handle_exception(self, exc)

    def _on_theme_changed(self, _mode: str) -> None:
        self._update_theme_button()
        self.refresh_current()

    def _update_theme_button(self) -> None:
        dark = theme().is_dark
        self.theme_button.setIcon(theme().icon("sun" if dark else "moon", "gold"))
        self.theme_button.setToolTip("Chuyển sang giao diện sáng" if dark else "Chuyển sang giao diện tối")

    def _update_clock(self) -> None:
        now = datetime.now()
        self.clock_label.setText(f"{WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y  %H:%M}")

    def closeEvent(self, event) -> None:  # noqa: N802 (tên hàm của Qt)
        pos_page = self.pages.get("pos")
        if pos_page is not None and not pos_page.cart.is_empty:
            if not ask_confirm(self, "Thoát chương trình",
                               "Giỏ hàng vẫn còn sản phẩm chưa thanh toán. Bạn có chắc muốn thoát?",
                               "Thoát", "Ở lại", danger=True):
                event.ignore()
                return
        event.accept()
