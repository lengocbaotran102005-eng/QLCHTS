"""Phân hệ Quản lý kho hàng: tồn kho hiện tại, nhập kho, điều chỉnh kiểm kê và lịch sử kho."""
from datetime import date, timedelta

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QTableWidget, QTabWidget, QVBoxLayout, QWidget

import config
from ui.stock_dialog import StockDialog
from ui.widgets import (
    ALIGN_RIGHT,
    BasePage,
    KpiCard,
    SearchBox,
    fill_table,
    from_qdate,
    hint_label,
    make_button,
    make_combo,
    make_date_edit,
    make_item,
    safe_slot,
    select_by_id,
    selected_id,
    setup_table,
    show_warning,
)
from utils.formatters import format_datetime, format_money, format_number, format_weight

LEVEL_TEXT = {"ok": "Còn hàng", "low": "Sắp hết", "out": "Hết hàng"}
LEVEL_COLOR = {"ok": "teal", "low": "warning", "out": "danger"}


class InventoryPage(BasePage):
    title = "Quản lý kho hàng"
    subtitle = "Theo dõi tồn kho, nhập hàng, điều chỉnh kiểm kê – mọi thay đổi đều có lịch sử và lý do"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        kpis = QHBoxLayout()
        kpis.setSpacing(16)
        self.kpi_units = KpiCard("Tổng số lượng tồn kho", "package", "sky")
        self.kpi_value = KpiCard("Giá trị tồn kho (giá nhập)", "money", "gold")
        self.kpi_low = KpiCard("Sản phẩm sắp hết hàng", "alert", "warning")
        self.kpi_out = KpiCard("Sản phẩm đã hết hàng", "cancel", "rose")
        for card in (self.kpi_units, self.kpi_value, self.kpi_low, self.kpi_out):
            kpis.addWidget(card)
        self.root.addLayout(kpis)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_stock_tab(), "Tồn kho hiện tại")
        self.tabs.addTab(self._build_history_tab(), "Lịch sử nhập – xuất – điều chỉnh kho")
        self.root.addWidget(self.tabs, 1)

    def _build_stock_tab(self) -> QWidget:
        card = QWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = SearchBox("Tìm sản phẩm theo tên, SKU, chất liệu...")
        self.search.search_requested.connect(lambda _t: self.load_stock())
        self.level_filter = make_combo([("Tất cả mức tồn", "all"), ("Sắp hết hàng", "low"), ("Hết hàng", "out")])
        self.level_filter.currentIndexChanged.connect(lambda _i: self.load_stock())
        import_button = make_button("Nhập kho", "import", "primary")
        import_button.clicked.connect(lambda: self.open_stock_dialog("import"))
        adjust_button = make_button("Điều chỉnh tồn kho", "clipboard")
        adjust_button.clicked.connect(lambda: self.open_stock_dialog("adjust"))
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.level_filter)
        toolbar.addWidget(import_button)
        toolbar.addWidget(adjust_button)
        layout.addLayout(toolbar)
        self.stock_table = QTableWidget()
        setup_table(self.stock_table, ["SKU", "Tên sản phẩm", "Danh mục", "Trọng lượng", "Tồn kho", "Giá nhập",
                                       "Giá trị tồn", "Mức tồn", "Kinh doanh"], stretch=1)
        self.stock_table.itemSelectionChanged.connect(self._on_product_selected)
        self.stock_table.doubleClicked.connect(lambda _i: self.open_stock_dialog("import"))
        layout.addWidget(self.stock_table, 1)
        self.stock_hint = hint_label("")
        layout.addWidget(self.stock_hint)
        return card

    def _build_history_tab(self) -> QWidget:
        card = QWidget()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.type_filter = make_combo([("Tất cả loại giao dịch", None)]
                                      + [(label, key) for key, label in config.INVENTORY_TYPE_LABELS.items()])
        self.type_filter.currentIndexChanged.connect(lambda _i: self.load_history())
        self.only_selected = QCheckBox("Chỉ sản phẩm đang chọn")
        self.only_selected.toggled.connect(lambda _c: self.load_history())
        self.date_from = make_date_edit(date.today() - timedelta(days=90))
        self.date_to = make_date_edit(date.today())
        apply_button = make_button("Lọc", "search", size="small")
        apply_button.clicked.connect(self.load_history)
        filters.addWidget(self.type_filter)
        filters.addWidget(self.only_selected)
        filters.addStretch()
        filters.addWidget(QLabel("Từ"))
        filters.addWidget(self.date_from)
        filters.addWidget(QLabel("Đến"))
        filters.addWidget(self.date_to)
        filters.addWidget(apply_button)
        layout.addLayout(filters)
        self.history_table = QTableWidget()
        setup_table(self.history_table, ["Thời gian", "SKU", "Sản phẩm", "Loại giao dịch", "Thay đổi",
                                         "Tồn sau", "Tham chiếu", "Lý do / Ghi chú", "Người thực hiện"], stretch=7)
        layout.addWidget(self.history_table, 1)
        self.history_hint = hint_label("Dữ liệu từ bảng inventory_transactions. Chọn sản phẩm ở thẻ \"Tồn kho hiện tại\" "
                                       "rồi đánh dấu \"Chỉ sản phẩm đang chọn\" để xem lịch sử riêng.")
        layout.addWidget(self.history_hint)
        return card

    # ------------------------------------------------------------------ dữ liệu
    def refresh(self) -> None:
        threshold = self.ctx.settings.low_stock_threshold
        summary = self.ctx.inventory.summary(threshold)
        self.kpi_units.set_value(format_number(summary["total_units"]),
                                 f"{summary['product_count']} mã sản phẩm trong kho")
        self.kpi_value.set_value(format_money(summary["stock_value_cost"]),
                                 f"Theo giá bán: {format_money(summary['stock_value_retail'])}")
        self.kpi_low.set_value(format_number(summary["low_stock"]), f"Tồn kho ≤ {threshold} (đang kinh doanh)")
        self.kpi_out.set_value(format_number(summary["out_of_stock"]), "Cần nhập thêm hàng")
        self.load_stock()
        self.load_history()

    def load_stock(self) -> None:
        threshold = self.ctx.settings.low_stock_threshold
        current = selected_id(self.stock_table)
        products = self.ctx.inventory.stock_list(self.search.text(), self.level_filter.currentData(), threshold)
        rows = []
        for p in products:
            level = p.stock_level(threshold)
            rows.append([
                make_item(p.sku, data=p.product_id),
                make_item(p.product_name, bold=True),
                make_item(p.category_name),
                make_item(format_weight(p.weight, p.weight_unit), sort=p.weight_in_grams),
                make_item(str(p.stock_quantity), align=ALIGN_RIGHT, sort=p.stock_quantity, bold=True,
                          color=LEVEL_COLOR[level] if level != "ok" else None),
                make_item(format_money(p.cost_price), align=ALIGN_RIGHT, sort=p.cost_price),
                make_item(format_money(p.cost_price * p.stock_quantity), align=ALIGN_RIGHT,
                          sort=p.cost_price * p.stock_quantity),
                make_item(LEVEL_TEXT[level], color=LEVEL_COLOR[level], bold=True),
                make_item(p.status_label, color="text" if p.is_active else "text_faint"),
            ])
        self.stock_table.blockSignals(True)
        fill_table(self.stock_table, rows)
        select_by_id(self.stock_table, current)
        self.stock_table.blockSignals(False)
        self.stock_hint.setText(f"{len(products)} sản phẩm. Ngưỡng cảnh báo tồn kho thấp: ≤ {threshold} "
                                "(thay đổi tại Cài đặt hệ thống).")

    def _on_product_selected(self) -> None:
        if self.only_selected.isChecked():
            self.load_history()

    @safe_slot
    def load_history(self) -> None:
        start, end = from_qdate(self.date_from.date()), from_qdate(self.date_to.date())
        if start > end:
            show_warning(self, "Khoảng thời gian không hợp lệ", "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
            return
        product_id = selected_id(self.stock_table) if self.only_selected.isChecked() else None
        history = self.ctx.inventory.history(product_id, self.type_filter.currentData(), start.isoformat(),
                                             end.isoformat())
        colors = {"IMPORT": "teal", "SALE": "gold", "ADJUST": "warning", "CANCEL": "sky"}
        rows = []
        for tx in history:
            sign = "+" if tx.quantity_change > 0 else ""
            rows.append([
                make_item(format_datetime(tx.created_at), sort=tx.created_at, data=tx.transaction_id),
                make_item(tx.sku),
                make_item(tx.product_name),
                make_item(tx.type_label, color=colors.get(tx.transaction_type), bold=True),
                make_item(f"{sign}{tx.quantity_change}", align=ALIGN_RIGHT, sort=tx.quantity_change,
                          color="teal" if tx.quantity_change > 0 else "danger", bold=True),
                make_item(str(tx.stock_after), align=ALIGN_RIGHT, sort=tx.stock_after),
                make_item(tx.reference_code or "—"),
                make_item(tx.note or "—", tooltip=tx.note),
                make_item(tx.created_by or "—"),
            ])
        fill_table(self.history_table, rows)
        self.history_hint.setText(f"{len(history)} giao dịch kho (tối đa 500 giao dịch gần nhất) – "
                                  "dữ liệu từ bảng inventory_transactions.")

    @safe_slot
    def open_stock_dialog(self, mode: str) -> None:
        product_id = selected_id(self.stock_table)
        if product_id is None:
            show_warning(self, "Chưa chọn sản phẩm", "Vui lòng chọn một sản phẩm trong bảng tồn kho.")
            return
        dialog = StockDialog(self.ctx, self.ctx.products.get(product_id), mode, self)
        if dialog.exec():
            action = "Nhập kho" if mode == "import" else "Điều chỉnh tồn kho"
            self.notify(f"{action} thành công. Tồn kho mới: {dialog.new_stock}.")
            self.refresh()
