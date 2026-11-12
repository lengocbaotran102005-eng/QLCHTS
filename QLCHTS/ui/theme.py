"""Giao diện sáng/tối: bảng màu thương hiệu, QSS (Qt Style Sheets) và quản lý icon theo theme.

Màu chủ đạo: đen than (charcoal), vàng Champagne Gold và xanh ngọc.
"""
import weakref
from string import Template

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

import config
from ui.icons import make_icon

PALETTES = {
    "dark": {
        "bg": "#0F0F12", "bg_end": "#18150F",
        "surface": "#18181D", "surface_alt": "#1F1F26", "surface_hover": "#282830",
        "glass": "rgba(28, 28, 35, 0.86)", "glass_border": "rgba(255, 255, 255, 0.07)",
        "border": "#2A2A33", "border_strong": "#3A3A46",
        "text": "#EEE9E0", "text_muted": "#A39D92", "text_faint": "#6F6A62",
        "gold": "#D8B97F", "gold_light": "#EBD3A3", "gold_dark": "#B48F55",
        "gold_soft": "rgba(216, 185, 127, 0.14)", "on_gold": "#1B160E",
        "teal": "#2DBBA8", "teal_soft": "rgba(45, 187, 168, 0.16)",
        "rose": "#E58EA2", "rose_soft": "rgba(229, 142, 162, 0.15)",
        "sky": "#74ADE6", "sky_soft": "rgba(116, 173, 230, 0.15)",
        "danger": "#EC6A74", "danger_soft": "rgba(236, 106, 116, 0.14)",
        "warning": "#EDB65A", "warning_soft": "rgba(237, 182, 90, 0.15)",
        "success": "#45C98F",
        "input_bg": "#131317", "selection": "rgba(216, 185, 127, 0.20)",
        "row_hover": "rgba(255, 255, 255, 0.035)", "row_border": "rgba(255, 255, 255, 0.045)",
        "header_bg": "#131317", "table_header": "#1C1C22", "scroll": "#3B3B47",
        "kpi_a": "rgba(36, 34, 30, 0.95)", "kpi_b": "rgba(24, 24, 30, 0.95)",
        "chart_grid": "#2C2C36", "chart_bg": "#1B1B21", "shadow": "rgba(0, 0, 0, 120)",
        "sidebar_bg": "#0A0A0C", "sidebar_border": "#1D1D23", "sidebar_text": "#B7B1A6",
        "sidebar_muted": "#6C675F", "sidebar_hover": "rgba(255, 255, 255, 0.05)",
        "sidebar_active": "rgba(216, 185, 127, 0.13)",
    },
    "light": {
        "bg": "#F5F1EA", "bg_end": "#ECE3D3",
        "surface": "#FFFFFF", "surface_alt": "#FAF7F1", "surface_hover": "#F2ECE1",
        "glass": "rgba(255, 255, 255, 0.88)", "glass_border": "rgba(120, 95, 50, 0.13)",
        "border": "#E6DED0", "border_strong": "#D5CAB7",
        "text": "#1E1C19", "text_muted": "#6A645A", "text_faint": "#A0998C",
        "gold": "#A47A38", "gold_light": "#C7A062", "gold_dark": "#8A6529",
        "gold_soft": "rgba(164, 122, 56, 0.12)", "on_gold": "#FFFFFF",
        "teal": "#0F8A7B", "teal_soft": "rgba(15, 138, 123, 0.12)",
        "rose": "#C2577A", "rose_soft": "rgba(194, 87, 122, 0.11)",
        "sky": "#3A78B8", "sky_soft": "rgba(58, 120, 184, 0.11)",
        "danger": "#C8404C", "danger_soft": "rgba(200, 64, 76, 0.10)",
        "warning": "#B07410", "warning_soft": "rgba(176, 116, 16, 0.12)",
        "success": "#1E9A63",
        "input_bg": "#FFFFFF", "selection": "rgba(164, 122, 56, 0.16)",
        "row_hover": "rgba(120, 95, 50, 0.05)", "row_border": "rgba(120, 95, 50, 0.08)",
        "header_bg": "#FFFFFF", "table_header": "#F7F2EA", "scroll": "#D2C7B4",
        "kpi_a": "rgba(255, 255, 255, 0.97)", "kpi_b": "rgba(250, 245, 236, 0.97)",
        "chart_grid": "#ECE5D8", "chart_bg": "#FEFDFB", "shadow": "rgba(110, 85, 40, 45)",
        "sidebar_bg": "#141417", "sidebar_border": "#232329", "sidebar_text": "#BDB7AC",
        "sidebar_muted": "#77726A", "sidebar_hover": "rgba(255, 255, 255, 0.06)",
        "sidebar_active": "rgba(216, 185, 127, 0.15)",
    },
}
# Màu điểm nhấn của thanh điều hướng luôn là vàng sáng (thanh bên luôn nền tối)
SIDEBAR_GOLD = "#D8B97F"

QSS = Template("""
QWidget { color: $text; font-family: "$font"; font-size: 10pt; }
QMainWindow { background: $bg; }
QDialog { background: $surface; }
QWidget#ContentArea {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $bg, stop:1 $bg_end);
}
QWidget#PageRoot, QWidget#ScrollContent, QStackedWidget#PageStack { background: transparent; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }

/* ---------- Thanh điều hướng bên trái ---------- */
QFrame#Sidebar { background: $sidebar_bg; border-right: 1px solid $sidebar_border; }
QLabel#BrandName { color: $sidebar_gold; font-family: "$serif"; font-size: 15pt; font-weight: 700; }
QLabel#BrandTagline { color: $sidebar_muted; font-size: 8pt; }
QLabel#SidebarSection { color: $sidebar_muted; font-size: 7.5pt; font-weight: 700; padding: 10px 14px 4px 14px; }
QPushButton#NavButton {
    background: transparent; color: $sidebar_text; border: none; border-radius: 10px;
    padding: 10px 14px; text-align: left; font-size: 10pt;
}
QPushButton#NavButton:hover { background: $sidebar_hover; color: #F4EFE6; }
QPushButton#NavButton:checked {
    background: $sidebar_active; color: $sidebar_gold; font-weight: 600;
    border-left: 3px solid $sidebar_gold; padding-left: 11px;
}
QFrame#SidebarFooter { background: rgba(255, 255, 255, 0.03); border: 1px solid $sidebar_border; border-radius: 12px; }
QLabel#SidebarFooterTitle { color: #E9E3D8; font-weight: 600; font-size: 9pt; }
QLabel#SidebarFooterText { color: $sidebar_muted; font-size: 8pt; }

/* ---------- Thanh tiêu đề ---------- */
QFrame#HeaderBar { background: $header_bg; border-bottom: 1px solid $border; }
QLabel#PageTitle { font-size: 16pt; font-weight: 700; color: $text; }
QLabel#PageSubtitle { color: $text_muted; font-size: 9pt; }
QLabel#HeaderClock { color: $text_muted; font-size: 9pt; }
QLabel#HeaderChip {
    background: $teal_soft; color: $teal; border-radius: 11px; padding: 4px 10px; font-size: 8.5pt; font-weight: 600;
}

/* ---------- Thẻ, nhãn ---------- */
QFrame#Card { background: $glass; border: 1px solid $glass_border; border-radius: 16px; }
QFrame#SubCard { background: $surface_alt; border: 1px solid $border; border-radius: 12px; }
QLabel#CardTitle { font-size: 11.5pt; font-weight: 700; color: $text; }
QLabel#CardSubtitle { color: $text_muted; font-size: 8.5pt; }
QLabel#SectionTitle { font-size: 10.5pt; font-weight: 700; color: $text; }
QLabel#FieldLabel { color: $text_muted; font-weight: 600; font-size: 9pt; }
QLabel#Hint { color: $text_faint; font-size: 8.5pt; }
QLabel#ErrorHint { color: $danger; font-size: 9pt; font-weight: 600; }
QLabel#SuccessHint { color: $teal; font-size: 9pt; font-weight: 600; }
QLabel#MutedText { color: $text_muted; }
QFrame#Divider { background: $border; border: none; min-height: 1px; max-height: 1px; }

QFrame#KpiCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $kpi_a, stop:1 $kpi_b);
    border: 1px solid $glass_border; border-radius: 18px;
}
QLabel#KpiTitle { color: $text_muted; font-size: 9pt; font-weight: 600; }
QLabel#KpiValue { color: $text; font-size: 17pt; font-weight: 700; }
QLabel#KpiSub { color: $text_faint; font-size: 8.5pt; }
QLabel#KpiIcon { border-radius: 14px; background: $gold_soft; }
QLabel#KpiIcon[accent="teal"] { background: $teal_soft; }
QLabel#KpiIcon[accent="rose"] { background: $rose_soft; }
QLabel#KpiIcon[accent="sky"] { background: $sky_soft; }
QLabel#KpiIcon[accent="warning"] { background: $warning_soft; }

QLabel[badge="ok"] { background: $teal_soft; color: $teal; border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 600; }
QLabel[badge="low"] { background: $warning_soft; color: $warning; border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 600; }
QLabel[badge="out"] { background: $danger_soft; color: $danger; border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 600; }
QLabel[badge="muted"] { background: $surface_hover; color: $text_muted; border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 600; }
QLabel[badge="gold"] { background: $gold_soft; color: $gold; border-radius: 9px; padding: 2px 9px; font-size: 8.5pt; font-weight: 600; }

/* ---------- Nút bấm ---------- */
QPushButton {
    background: $surface_alt; color: $text; border: 1px solid $border_strong; border-radius: 9px;
    padding: 7px 14px; font-weight: 600;
}
QPushButton:hover { background: $surface_hover; border-color: $gold; }
QPushButton:pressed { background: $surface; }
QPushButton:disabled { color: $text_faint; background: $surface; border-color: $border; }
QPushButton[variant="primary"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $gold_light, stop:1 $gold_dark);
    color: $on_gold; border: 1px solid $gold_dark;
}
QPushButton[variant="primary"]:hover { background: $gold_light; border-color: $gold_light; }
QPushButton[variant="primary"]:pressed { background: $gold_dark; }
QPushButton[variant="primary"]:disabled { background: $gold_soft; color: $text_faint; border-color: transparent; }
QPushButton[variant="teal"] { background: $teal; color: #FFFFFF; border: 1px solid $teal; }
QPushButton[variant="teal"]:hover { background: $teal_soft; color: $teal; }
QPushButton[variant="danger"] { background: $danger_soft; color: $danger; border: 1px solid $danger_soft; }
QPushButton[variant="danger"]:hover { background: $danger; color: #FFFFFF; border-color: $danger; }
QPushButton[variant="ghost"] { background: transparent; border: 1px solid transparent; color: $text_muted; }
QPushButton[variant="ghost"]:hover { background: $surface_hover; color: $text; border-color: $border; }
QPushButton[variant="chip"] { background: transparent; border: 1px solid $border_strong; border-radius: 14px; padding: 4px 12px; color: $text_muted; font-weight: 600; }
QPushButton[variant="chip"]:hover { border-color: $gold; color: $text; }
QPushButton[variant="chip"]:checked { background: $gold_soft; border-color: $gold; color: $gold; }
QPushButton[size="large"] { padding: 12px 18px; font-size: 12pt; border-radius: 12px; }
QPushButton[size="small"] { padding: 4px 9px; font-size: 9pt; border-radius: 7px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 4px; color: $text; }
QToolButton:hover { background: $surface_hover; border-color: $border_strong; }
QToolButton:pressed { background: $gold_soft; }
QToolButton:disabled { color: $text_faint; }
QToolButton#QtyButton { border: 1px solid $border_strong; border-radius: 7px; background: $surface_alt; }
QToolButton#QtyButton:hover { border-color: $gold; }
QToolButton#QtyButton:disabled { border-color: $border; background: transparent; }
QToolButton#DangerTool:hover { background: $danger_soft; border-color: $danger_soft; }

/* ---------- Ô nhập liệu ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit, QPlainTextEdit {
    background: $input_bg; border: 1px solid $border_strong; border-radius: 9px; padding: 6px 10px;
    color: $text; selection-background-color: $gold_dark; selection-color: #FFFFFF;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus,
QTextEdit:focus, QPlainTextEdit:focus { border: 1px solid $gold; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled,
QTextEdit:disabled, QPlainTextEdit:disabled { color: $text_faint; background: $surface_alt; border-color: $border; }
QLineEdit[readOnly="true"] { background: $surface_alt; color: $text_muted; }
QLineEdit[invalid="true"], QComboBox[invalid="true"] { border: 1px solid $danger; }
QComboBox { padding-right: 8px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 24px; border: none; }
QComboBox::down-arrow { image: url($chevron_down); width: 12px; height: 12px; }
QComboBox QAbstractItemView {
    background: $surface; border: 1px solid $border_strong; border-radius: 8px; padding: 4px; outline: none;
    selection-background-color: $selection; selection-color: $text;
}
QComboBox QAbstractItemView::item { min-height: 28px; padding: 3px 8px; border-radius: 6px; }
QComboBox QAbstractItemView::item:hover { background: $row_hover; }
QComboBox QAbstractItemView::item:selected { background: $selection; color: $text; }
/* Ô nhập bên trong spinbox/combobox không có viền riêng */
QAbstractSpinBox QLineEdit { border: none; padding: 0px 8px; margin: 0px; background: transparent; border-radius: 0px; }
QComboBox QLineEdit { border: none; padding: 0px 2px; margin: 0px; background: transparent; border-radius: 0px; }
/* Spinbox ẩn nút tăng/giảm (dùng thuộc tính thay cho NoButtons để tránh lỗi co ô nhập của Qt) */
QAbstractSpinBox[noButtons="true"]::up-button, QAbstractSpinBox[noButtons="true"]::down-button { width: 0px; border: none; }
QAbstractSpinBox[noButtons="true"]::up-arrow, QAbstractSpinBox[noButtons="true"]::down-arrow { image: none; }
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; background: transparent;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; background: transparent;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url($chevron_up); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url($chevron_down); width: 10px; height: 10px; }
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled,
QDoubleSpinBox::down-arrow:disabled { image: none; }
QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: none; }
QDateEdit::down-arrow { image: url($calendar_icon); width: 14px; height: 14px; }

QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid $border_strong; background: $input_bg; }
QCheckBox::indicator:hover { border-color: $gold; }
QCheckBox::indicator:checked { background: $gold; border-color: $gold; image: url($check_icon); }
QRadioButton { spacing: 8px; }

/* ---------- Bảng dữ liệu ---------- */
QTableView, QTableWidget, QListWidget, QTreeView {
    background: $surface; alternate-background-color: $surface_alt; border: 1px solid $border;
    border-radius: 12px; gridline-color: transparent; outline: none;
    selection-background-color: $selection; selection-color: $text;
}
QTableView::item, QTableWidget::item { padding: 4px 8px; border-bottom: 1px solid $row_border; }
QTableView::item:hover, QTableWidget::item:hover { background: $row_hover; }
QTableView::item:selected, QTableWidget::item:selected { background: $selection; color: $text; }
QHeaderView { background: transparent; border: none; }
QHeaderView::section {
    background: $table_header; color: $text_muted; font-weight: 700; font-size: 9pt;
    padding: 8px 8px; border: none; border-bottom: 1px solid $border_strong;
}
QHeaderView::section:first { border-top-left-radius: 12px; }
QHeaderView::section:last { border-top-right-radius: 12px; }
QTableCornerButton::section { background: $table_header; border: none; }
QListWidget::item { padding: 6px 8px; border-radius: 8px; }
QListWidget::item:selected { background: $selection; color: $text; }

/* ---------- Tab, nhóm, thanh cuộn ---------- */
QTabWidget::pane { border: 1px solid $glass_border; border-radius: 14px; background: $glass; top: -1px; }
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab {
    background: transparent; color: $text_muted; padding: 9px 16px; margin-right: 4px;
    border: none; border-bottom: 2px solid transparent; font-weight: 600;
}
QTabBar::tab:selected { color: $gold; border-bottom: 2px solid $gold; }
QTabBar::tab:hover:!selected { color: $text; }
QGroupBox {
    border: 1px solid $border; border-radius: 12px; margin-top: 16px; padding: 14px 12px 12px 12px;
    font-weight: 700; background: $surface_alt;
}
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: $gold; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 3px 2px 3px 0; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: $gold_dark; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 0 3px 2px 3px; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 4px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: $gold_dark; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: $gold_soft; }

/* ---------- Khác ---------- */
QToolTip { background: $surface_alt; color: $text; border: 1px solid $gold; padding: 6px 8px; border-radius: 6px; }
QMenu { background: $surface; border: 1px solid $border_strong; padding: 6px; border-radius: 8px; }
QMenu::item { padding: 7px 22px; border-radius: 6px; }
QMenu::item:selected { background: $selection; }
QStatusBar { background: $header_bg; color: $text_muted; border-top: 1px solid $border; }
QStatusBar::item { border: none; }
QMessageBox { background: $surface; }
QMessageBox QLabel { color: $text; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: $surface_alt; }
QCalendarWidget QToolButton { color: $text; background: transparent; padding: 4px 8px; font-weight: 600; }
QCalendarWidget QToolButton:hover { background: $surface_hover; }
QCalendarWidget QMenu { background: $surface; }
QCalendarWidget QSpinBox { padding: 2px 18px 2px 6px; }
QCalendarWidget QAbstractItemView:enabled {
    background: $surface; color: $text; selection-background-color: $gold; selection-color: $on_gold; outline: none;
}
QCalendarWidget QAbstractItemView:disabled { color: $text_faint; }
QProgressBar { background: $surface_alt; border: 1px solid $border; border-radius: 6px; height: 10px; text-align: center; }
QProgressBar::chunk { background: $gold; border-radius: 5px; }

/* ---------- Bán hàng POS ---------- */
QFrame#ProductCard { background: $surface; border: 1px solid $border; border-radius: 16px; }
QFrame#ProductCard:hover { border: 1px solid $gold; background: $surface_alt; }
QFrame#ProductCard[inactive="true"] { background: $surface_alt; }
QLabel#ProductName { font-weight: 700; font-size: 10pt; color: $text; }
QLabel#ProductMeta { color: $text_muted; font-size: 8.5pt; }
QLabel#ProductPrice { color: $gold; font-weight: 700; font-size: 11.5pt; }
QFrame#CartPanel { background: $glass; border: 1px solid $glass_border; border-radius: 16px; }
QFrame#CartRow { background: $surface; border: 1px solid $border; border-radius: 12px; }
QFrame#CartRow:hover { border-color: $gold_dark; }
QLabel#CartItemName { font-weight: 700; }
QLabel#CartItemMeta { color: $text_muted; font-size: 8.5pt; }
QLabel#CartLineTotal { font-weight: 700; color: $text; font-size: 10.5pt; }
QLabel#TotalCaption { color: $text_muted; }
QLabel#TotalValue { font-weight: 600; color: $text; }
QLabel#DiscountValue { font-weight: 600; color: $rose; }
QLabel#GrandTotalCaption { font-weight: 700; color: $text; font-size: 11pt; }
QLabel#GrandTotal { color: $gold; font-size: 19pt; font-weight: 800; font-family: "$serif"; }
QLabel#FormulaHint { color: $text_faint; font-size: 8pt; }
QFrame#TotalsBox { background: $surface_alt; border: 1px solid $border; border-radius: 12px; }
QLabel#EmptyTitle { font-size: 12pt; font-weight: 700; color: $text; }
QLabel#EmptyText { color: $text_muted; }
QLabel#ImagePreview { background: $surface_alt; border: 1px dashed $border_strong; border-radius: 12px; }
""")


def _pick_font(candidates: list[str], fallback: str) -> str:
    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            return name
    return fallback


class ThemeManager(QObject):
    """Áp dụng QSS + QPalette, đổi icon theo màu khi chuyển giữa giao diện sáng và tối."""

    theme_changed = Signal(str)
    _instance: "ThemeManager | None" = None

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.mode = "dark"
        self.font_family = _pick_font(["Segoe UI", "Arial"], app.font().family())
        self.serif_family = _pick_font(["Palatino Linotype", "Cambria", "Times New Roman"], self.font_family)
        self._icon_bindings: list[tuple[weakref.ref, str, str, str | None]] = []
        ThemeManager._instance = self

    @classmethod
    def instance(cls) -> "ThemeManager":
        return cls._instance

    # ------------------------------------------------------------------ màu
    @property
    def palette(self) -> dict:
        return PALETTES[self.mode]

    def color(self, key: str) -> str:
        if key == "sidebar_gold":
            return SIDEBAR_GOLD
        return self.palette.get(key, key)

    @property
    def is_dark(self) -> bool:
        return self.mode == "dark"

    # ------------------------------------------------------------------ áp dụng
    def apply(self, mode: str) -> None:
        self.mode = "light" if mode == "light" else "dark"
        values = dict(self.palette)
        values.update(self._theme_icon_urls())
        values.update(font=self.font_family, serif=self.serif_family, sidebar_gold=SIDEBAR_GOLD)
        self.app.setStyleSheet(QSS.substitute(values))
        self.app.setPalette(self._build_palette())
        self._refresh_icons()
        self.theme_changed.emit(self.mode)

    def toggle(self) -> str:
        self.apply("light" if self.is_dark else "dark")
        return self.mode

    def _build_palette(self) -> QPalette:
        p = self.palette
        pal = QPalette()
        roles = {
            QPalette.ColorRole.Window: p["bg"], QPalette.ColorRole.WindowText: p["text"],
            QPalette.ColorRole.Base: p["input_bg"], QPalette.ColorRole.AlternateBase: p["surface_alt"],
            QPalette.ColorRole.Text: p["text"], QPalette.ColorRole.Button: p["surface_alt"],
            QPalette.ColorRole.ButtonText: p["text"], QPalette.ColorRole.Highlight: p["gold_dark"],
            QPalette.ColorRole.HighlightedText: "#FFFFFF", QPalette.ColorRole.ToolTipBase: p["surface_alt"],
            QPalette.ColorRole.ToolTipText: p["text"], QPalette.ColorRole.PlaceholderText: p["text_faint"],
            QPalette.ColorRole.Link: p["teal"], QPalette.ColorRole.BrightText: p["danger"],
        }
        for role, color in roles.items():
            pal.setColor(role, QColor(color))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
            pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(p["text_faint"]))
        return pal

    def _theme_icon_urls(self) -> dict:
        """Tạo các tệp SVG nhỏ đã tô màu (mũi tên, dấu tích) để dùng trong QSS."""
        folder = config.THEME_ICONS_DIR
        folder.mkdir(parents=True, exist_ok=True)
        muted, on_gold = self.palette["text_muted"], self.palette["on_gold"]
        shapes = {
            "chevron_down": ('<path d="m6 9 6 6 6-6"/>', muted, 2.4),
            "chevron_up": ('<path d="m6 15 6-6 6 6"/>', muted, 2.4),
            "check_icon": ('<path d="m5 12.5 4.5 4.5L19 7.5"/>', on_gold, 3),
            "calendar_icon": ('<rect x="3.5" y="5" width="17" height="15.5" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
                              muted, 2),
        }
        urls = {}
        for key, (body, color, width) in shapes.items():
            path = folder / f"{key}_{self.mode}.svg"
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
                   f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
            try:
                if not path.exists() or path.read_text(encoding="utf-8") != svg:
                    path.write_text(svg, encoding="utf-8")
            except OSError:
                pass
            urls[key] = path.as_posix()
        return urls

    # ------------------------------------------------------------------ icon
    def icon(self, name: str, role: str = "text", checked_role: str | None = None):
        return make_icon(name, self.color(role), self.color(checked_role) if checked_role else None)

    def bind_icon(self, widget, name: str, role: str = "text", checked_role: str | None = None) -> None:
        """Gán icon cho nút và tự đổi màu icon khi đổi giao diện sáng/tối."""
        widget.setIcon(self.icon(name, role, checked_role))
        self._icon_bindings.append((weakref.ref(widget), name, role, checked_role))

    def _refresh_icons(self) -> None:
        alive = []
        for ref, name, role, checked_role in self._icon_bindings:
            widget = ref()
            if widget is None:
                continue
            try:
                widget.setIcon(self.icon(name, role, checked_role))
            except RuntimeError:  # đối tượng C++ đã bị hủy
                continue
            alive.append((ref, name, role, checked_role))
        self._icon_bindings = alive
