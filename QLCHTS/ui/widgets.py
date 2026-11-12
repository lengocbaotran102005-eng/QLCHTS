"""Các thành phần giao diện dùng chung: thẻ, bảng, nút, hộp thoại thông báo, chạy tác vụ nền."""
import functools
import inspect
import logging
import sqlite3
import traceback
from datetime import date

from PySide6.QtCore import QDate, QLocale, QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from errors import AppError
from ui.theme import ThemeManager

log = logging.getLogger(__name__)

ID_ROLE = Qt.ItemDataRole.UserRole
SORT_ROLE = Qt.ItemDataRole.UserRole + 1
VN_LOCALE = QLocale(QLocale.Language.Vietnamese, QLocale.Country.Vietnam)

ALIGN_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
ALIGN_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter


def theme() -> ThemeManager:
    return ThemeManager.instance()


# ---------------------------------------------------------------------------
# Hộp thoại thông báo (nút bấm tiếng Việt)
# ---------------------------------------------------------------------------
def _message(parent, icon, title: str, text: str, details: str | None = None) -> None:
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    if details:
        box.setDetailedText(details)
    box.addButton("Đóng", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def show_info(parent, title: str, text: str) -> None:
    _message(parent, QMessageBox.Icon.Information, title, text)


def show_warning(parent, title: str, text: str) -> None:
    _message(parent, QMessageBox.Icon.Warning, title, text)


def show_error(parent, title: str, text: str, details: str | None = None) -> None:
    _message(parent, QMessageBox.Icon.Critical, title, text, details)


def ask_confirm(parent, title: str, text: str, confirm_text: str = "Đồng ý", cancel_text: str = "Hủy bỏ",
                danger: bool = False) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton(confirm_text, QMessageBox.ButtonRole.AcceptRole)
    no = box.addButton(cancel_text, QMessageBox.ButtonRole.RejectRole)
    yes.setProperty("variant", "danger" if danger else "primary")
    box.setDefaultButton(no if danger else yes)
    box.exec()
    return box.clickedButton() is yes


def ask_text(parent, title: str, label: str, text: str = "") -> tuple[str, bool]:
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setTextValue(text)
    dialog.setOkButtonText("Đồng ý")
    dialog.setCancelButtonText("Hủy bỏ")
    dialog.resize(420, dialog.sizeHint().height())
    ok = dialog.exec() == QInputDialog.DialogCode.Accepted
    return dialog.textValue(), ok


def handle_exception(parent, exc: Exception) -> None:
    """Hiển thị lỗi thân thiện: lỗi nghiệp vụ, lỗi CSDL hoặc lỗi không mong muốn."""
    if isinstance(exc, AppError):
        show_warning(parent, exc.title, exc.message)
    elif isinstance(exc, sqlite3.Error):
        log.exception("Lỗi cơ sở dữ liệu")
        show_error(parent, "Lỗi cơ sở dữ liệu",
                   "Không thể đọc hoặc ghi cơ sở dữ liệu SQLite. Thao tác đã được hủy (ROLLBACK), "
                   "dữ liệu không bị thay đổi.\n\nVui lòng kiểm tra tệp baotran_jewelry.db không bị mở bởi "
                   "chương trình khác và thư mục có quyền ghi.",
                   details=f"{type(exc).__name__}: {exc}")
    else:
        log.exception("Lỗi không mong muốn")
        show_error(parent, "Lỗi không mong muốn",
                   "Đã xảy ra lỗi khi thực hiện thao tác. Chương trình vẫn tiếp tục hoạt động.",
                   details="".join(traceback.format_exception(exc)))


def safe_slot(method):
    """Bọc hàm xử lý sự kiện: bắt mọi lỗi và hiển thị thông báo thay vì làm dừng chương trình.

    Tự bỏ các tham số thừa mà tín hiệu Qt truyền vào (ví dụ ``checked`` của nút bấm).
    """
    params = list(inspect.signature(method).parameters.values())[1:]
    accepts_varargs = any(p.kind == p.VAR_POSITIONAL for p in params)
    max_args = len([p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])

    @functools.wraps(method)
    def wrapper(self, *args):
        try:
            return method(self, *(args if accepts_varargs else args[:max_args]))
        except Exception as exc:  # noqa: BLE001 – hiển thị cho người dùng
            handle_exception(self if isinstance(self, QWidget) else None, exc)
        return None

    return wrapper


# ---------------------------------------------------------------------------
# Chạy tác vụ nền (tải ảnh từ Internet...) để giao diện không bị treo
# ---------------------------------------------------------------------------
class _TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _BackgroundTask(QRunnable):
    def __init__(self, fn, args):
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = _TaskSignals()

    def run(self):
        try:
            result = self.fn(*self.args)
        except AppError as exc:
            self.signals.failed.emit(exc.message)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(result)


_running_tasks: set = set()


def run_in_background(fn, *args, on_success=None, on_error=None) -> None:
    """Chạy ``fn(*args)`` ở luồng nền; ``on_success``/``on_error`` nên là phương thức của QWidget."""
    task = _BackgroundTask(fn, args)
    signals = task.signals
    _running_tasks.add(signals)
    if on_success:
        signals.finished.connect(on_success)
    if on_error:
        signals.failed.connect(on_error)
    signals.finished.connect(lambda *_: _running_tasks.discard(signals))
    signals.failed.connect(lambda *_: _running_tasks.discard(signals))
    QThreadPool.globalInstance().start(task)


# ---------------------------------------------------------------------------
# Nút, ô nhập, nhãn
# ---------------------------------------------------------------------------
def make_button(text: str = "", icon: str | None = None, variant: str | None = None, *,
                size: str | None = None, tooltip: str | None = None, checkable: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant:
        button.setProperty("variant", variant)
    if size:
        button.setProperty("size", size)
    if tooltip:
        button.setToolTip(tooltip)
    button.setCheckable(checkable)
    if icon:
        role = {"primary": "on_gold", "danger": "danger", "teal": "#FFFFFF", "ghost": "text_muted"}.get(variant, "text")
        theme().bind_icon(button, icon, role)
    return button


def make_combo(items: list[tuple[str, object]] | None = None, editable: bool = False) -> QComboBox:
    combo = QComboBox()
    combo.setItemDelegate(QStyledItemDelegate(combo))  # để QSS áp dụng cho từng dòng
    combo.setEditable(editable)
    combo.setMinimumHeight(36)
    for text, data in items or []:
        combo.addItem(text, data)
    return combo


def pad_spin(spin, min_height: int = 36):
    """Thêm lề chữ cho ô spinbox (QSS không áp được padding cho ô nhập bên trong)."""
    spin.lineEdit().setTextMargins(6, 0, 6, 0)
    if min_height:
        spin.setMinimumHeight(min_height)
    return spin


def make_spin(minimum: int = 0, maximum: int = 1_000_000, value: int | None = None) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(minimum, maximum)
    if value is not None:
        spin.setValue(value)
    return pad_spin(spin)


def make_double_spin(minimum: float = 0.0, maximum: float = 100.0, decimals: int = 1,
                     suffix: str = "") -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setLocale(VN_LOCALE)
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSuffix(suffix)
    return pad_spin(spin)


def make_date_edit(value: date | None = None) -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd/MM/yyyy")
    edit.setLocale(VN_LOCALE)
    pad_spin(edit)
    edit.setMinimumWidth(138)
    edit.setDate(to_qdate(value or date.today()))
    return edit


def to_qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def from_qdate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def hide_spin_buttons(spin) -> None:
    """Ẩn nút tăng/giảm của spinbox bằng QSS (thuộc tính noButtons) – vẫn nhập và dùng phím mũi tên được."""
    spin.setProperty("noButtons", True)


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def hint_label(text: str, name: str = "Hint") -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    return line


def repolish(widget: QWidget) -> None:
    """Áp dụng lại QSS sau khi đổi thuộc tính động (variant, badge...)."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def add_shadow(widget: QWidget, blur: int = 30, offset_y: int = 8, alpha: int = 70) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, offset_y)
    effect.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)


class SearchBox(QLineEdit):
    """Ô tìm kiếm có biểu tượng kính lúp, nút xóa nhanh và phát tín hiệu sau khi ngừng gõ 250 ms."""

    search_requested = Signal(str)

    def __init__(self, placeholder: str = "Tìm kiếm...", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumHeight(38)
        self._action = self.addAction(theme().icon("search", "text_muted"), QLineEdit.ActionPosition.LeadingPosition)
        theme().theme_changed.connect(self._update_icon)
        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(lambda: self.search_requested.emit(self.text().strip()))
        self.textChanged.connect(lambda _: self._timer.start())
        self.returnPressed.connect(lambda: (self._timer.stop(), self.search_requested.emit(self.text().strip())))

    def _update_icon(self, _mode: str) -> None:
        self._action.setIcon(theme().icon("search", "text_muted"))


class MoneySpinBox(QDoubleSpinBox):
    """Ô nhập tiền VNĐ: số nguyên, phân cách hàng nghìn bằng dấu chấm."""

    def __init__(self, maximum: float = 100_000_000_000, parent=None):
        super().__init__(parent)
        self.setLocale(VN_LOCALE)
        self.setDecimals(0)
        self.setRange(0, maximum)
        self.setGroupSeparatorShown(True)
        self.setSuffix(" ₫")
        hide_spin_buttons(self)
        self.setAlignment(ALIGN_RIGHT)
        pad_spin(self)
        self.setSingleStep(100_000)

    def int_value(self) -> int:
        return int(round(self.value()))


class BadgeLabel(QLabel):
    """Nhãn trạng thái bo tròn: ok / low / out / muted / gold."""

    def __init__(self, text: str = "", kind: str = "muted"):
        super().__init__(text)
        self.setAlignment(ALIGN_CENTER)
        self.set_kind(kind, text)

    def set_kind(self, kind: str, text: str | None = None) -> None:
        if text is not None:
            self.setText(text)
        self.setProperty("badge", kind)
        repolish(self)


# ---------------------------------------------------------------------------
# Thẻ (card), KPI, trạng thái rỗng
# ---------------------------------------------------------------------------
class Card(QFrame):
    """Khung nội dung bo góc kiểu kính mờ (glassmorphism) có tiêu đề tùy chọn."""

    def __init__(self, title: str = "", subtitle: str = "", parent=None, object_name: str = "Card",
                 margins: int = 18, spacing: int = 12):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(margins, margins - 2, margins, margins)
        self.layout_.setSpacing(spacing)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("CardSubtitle")
        self.subtitle_label.setWordWrap(True)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        self.header.addLayout(titles, 1)
        if title:
            self.layout_.addLayout(self.header)
        self.subtitle_label.setVisible(bool(subtitle))

    def add_header_widget(self, widget: QWidget) -> None:
        self.header.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.layout_.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.layout_.addLayout(layout, stretch)


class KpiCard(QFrame):
    def __init__(self, title: str, icon: str, accent: str = "gold", parent=None):
        super().__init__(parent)
        self.setObjectName("KpiCard")
        self.setMinimumHeight(122)
        self.setMinimumWidth(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.accent = accent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(10)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("KpiIcon")
        self.icon_label.setProperty("accent", accent)
        self.icon_label.setFixedSize(38, 38)
        self.icon_label.setAlignment(ALIGN_CENTER)
        self.icon_name = icon
        self.title_label = QLabel(title)
        self.title_label.setObjectName("KpiTitle")
        self.title_label.setWordWrap(True)
        top.addWidget(self.icon_label)
        top.addWidget(self.title_label, 1)
        self.value_label = QLabel("—")
        self.value_label.setObjectName("KpiValue")
        self.sub_label = QLabel("")
        self.sub_label.setObjectName("KpiSub")
        self.sub_label.setWordWrap(True)
        layout.addLayout(top)
        layout.addWidget(self.value_label)
        layout.addWidget(self.sub_label)
        layout.addStretch()
        self._apply_icon()
        theme().theme_changed.connect(lambda _m: self._apply_icon())
        add_shadow(self, blur=28, offset_y=6, alpha=55)

    def _apply_icon(self) -> None:
        self.icon_label.setPixmap(theme().icon(self.icon_name, self.accent).pixmap(20, 20))

    def set_value(self, value: str, sub: str = "") -> None:
        self.value_label.setText(value)
        self.sub_label.setText(sub)
        self.value_label.setToolTip(value)


class EmptyState(QWidget):
    """Thông báo thân thiện khi chưa có dữ liệu (thay vì bảng trống hoặc báo lỗi)."""

    def __init__(self, icon: str, title: str, text: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 24)
        layout.setSpacing(6)
        layout.addStretch()
        self.icon_label = QLabel()
        self.icon_label.setAlignment(ALIGN_CENTER)
        self.icon_name = icon
        self.title_label = QLabel(title)
        self.title_label.setObjectName("EmptyTitle")
        self.title_label.setAlignment(ALIGN_CENTER)
        self.text_label = QLabel(text)
        self.text_label.setObjectName("EmptyText")
        self.text_label.setAlignment(ALIGN_CENTER)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.text_label)
        layout.addStretch()
        self._apply_icon()
        theme().theme_changed.connect(lambda _m: self._apply_icon())

    def _apply_icon(self) -> None:
        self.icon_label.setPixmap(theme().icon(self.icon_name, "gold").pixmap(44, 44))

    def set_text(self, title: str, text: str = "") -> None:
        self.title_label.setText(title)
        self.text_label.setText(text)


# ---------------------------------------------------------------------------
# Bảng dữ liệu
# ---------------------------------------------------------------------------
class SortItem(QTableWidgetItem):
    """Ô bảng sắp xếp theo giá trị thật (số tiền, ngày) thay vì theo chuỗi hiển thị."""

    def __lt__(self, other):
        mine, theirs = self.data(SORT_ROLE), other.data(SORT_ROLE)
        if mine is not None and theirs is not None:
            try:
                return mine < theirs
            except TypeError:
                pass
        return super().__lt__(other)


def make_item(text, *, align=ALIGN_LEFT, sort=None, data=None, color: str | None = None, bold: bool = False,
              tooltip: str | None = None, icon=None) -> SortItem:
    item = SortItem("" if text is None else str(text))
    item.setTextAlignment(align)
    if sort is not None:
        item.setData(SORT_ROLE, sort)
    if data is not None:
        item.setData(ID_ROLE, data)
    if color:
        item.setForeground(QColor(theme().color(color)))
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    if tooltip:
        item.setToolTip(tooltip)
    if icon is not None:
        item.setIcon(icon)
    return item


def setup_table(table: QTableWidget, headers: list[str], *, stretch: int | None = None,
                widths: dict[int, int] | None = None, row_height: int = 40, sortable: bool = True) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setDefaultAlignment(ALIGN_LEFT)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(60)
    for column, width in (widths or {}).items():
        table.setColumnWidth(column, width)
    table.setProperty("stretch_column", stretch)
    if stretch is not None:
        header.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
    table.setSortingEnabled(sortable)


def fill_table(table: QTableWidget, rows: list[list[QTableWidgetItem]], resize: bool = True) -> None:
    """Đổ dữ liệu vào bảng (tạm tắt sắp xếp để tránh xáo trộn dòng khi đang điền)."""
    sorting = table.isSortingEnabled()
    table.setSortingEnabled(False)
    table.clearContents()
    table.setRowCount(len(rows))
    for r, items in enumerate(rows):
        for c, item in enumerate(items):
            if item is not None:
                table.setItem(r, c, item)
    if resize:
        header = table.horizontalHeader()
        stretch = table.property("stretch_column")
        if stretch is not None:
            header.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Interactive)
        for column in range(table.columnCount()):
            table.resizeColumnToContents(column)
            table.setColumnWidth(column, min(table.columnWidth(column) + 18, 420 if column == stretch else 360))
        # Cột "co giãn" chỉ kéo dài khi tổng độ rộng còn vừa khung; nếu không thì giữ đủ rộng để đọc được nội dung
        total = sum(table.columnWidth(c) for c in range(table.columnCount()))
        if stretch is not None and total <= table.viewport().width():
            header.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
    table.setSortingEnabled(sorting)


def selected_id(table: QTableWidget):
    """Giá trị ID_ROLE của ô cột 0 thuộc dòng đang chọn (hoặc None)."""
    rows = table.selectionModel().selectedRows() if table.selectionModel() else []
    if not rows:
        return None
    item = table.item(rows[0].row(), 0)
    return item.data(ID_ROLE) if item else None


def select_by_id(table: QTableWidget, value) -> bool:
    if value is None:
        return False
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item and item.data(ID_ROLE) == value:
            table.selectRow(row)
            table.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtCenter)
            return True
    return False


# ---------------------------------------------------------------------------
# Trang (màn hình phân hệ) cơ sở
# ---------------------------------------------------------------------------
class BasePage(QWidget):
    """Mỗi phân hệ là một trang; ``refresh()`` được gọi mỗi khi người dùng mở trang."""

    title = ""
    subtitle = ""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("PageRoot")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 20, 24, 20)
        self.root.setSpacing(16)

    def refresh(self) -> None:
        """Nạp lại dữ liệu từ SQLite (các trang con ghi đè)."""

    def notify(self, message: str) -> None:
        self.ctx.notify(message)
