"""Phân hệ 1 – Tổng quan (Dashboard): thẻ KPI, biểu đồ doanh thu, cảnh báo tồn kho, giao dịch gần đây."""
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

import config
from ui.chart_widget import ChartWidget, short_money
from ui.invoice_dialog import open_invoice
from ui.widgets import (
    ALIGN_RIGHT,
    BasePage,
    Card,
    EmptyState,
    KpiCard,
    fill_table,
    from_qdate,
    hint_label,
    make_button,
    make_combo,
    make_date_edit,
    make_item,
    safe_slot,
    selected_id,
    setup_table,
    show_warning,
    to_qdate,
)
from utils.formatters import format_date, format_datetime, format_money, format_number


class DashboardPage(BasePage):
    title = "Tổng quan"
    subtitle = "Số liệu kinh doanh tổng hợp trực tiếp từ cơ sở dữ liệu SQLite"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("ScrollContent")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(18)
        scroll.setWidget(body)
        self.root.addWidget(scroll)

        # --- Thẻ KPI ---
        kpis = QGridLayout()
        kpis.setSpacing(16)
        self.kpi_revenue = KpiCard("Tổng doanh thu (thực thu)", "money", "gold")
        self.kpi_orders = KpiCard("Đơn hàng đã thanh toán", "receipt", "teal")
        self.kpi_products = KpiCard("Sản phẩm trong danh mục", "gem", "rose")
        self.kpi_stock = KpiCard("Tổng số lượng tồn kho", "package", "sky")
        self.kpi_customers = KpiCard("Khách hàng", "users", "warning")
        for column, card in enumerate((self.kpi_revenue, self.kpi_orders, self.kpi_products, self.kpi_stock,
                                       self.kpi_customers)):
            kpis.addWidget(card, 0, column)
        layout.addLayout(kpis)

        # --- Biểu đồ + cảnh báo tồn kho ---
        middle = QHBoxLayout()
        middle.setSpacing(16)
        self.chart_card = Card("Biểu đồ doanh thu", "Chỉ tính hóa đơn đã thanh toán")
        self.mode_combo = make_combo([("Theo ngày", "day"), ("Theo tháng", "month")])
        self.kind_combo = make_combo([("Biểu đồ cột", "bar"), ("Biểu đồ đường", "line")])
        self.chart_card.add_header_widget(self.mode_combo)
        self.chart_card.add_header_widget(self.kind_combo)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.range_buttons = []
        for text, days in (("7 ngày", 7), ("30 ngày", 30), ("90 ngày", 90), ("Năm nay", None)):
            button = make_button(text, variant="chip", checkable=True)
            button.clicked.connect(lambda _c=False, d=days, b=button: self._quick_range(d, b))
            controls.addWidget(button)
            self.range_buttons.append(button)
        controls.addStretch()
        controls.addWidget(QLabel("Từ"))
        self.date_from = make_date_edit(date.today() - timedelta(days=29))
        controls.addWidget(self.date_from)
        controls.addWidget(QLabel("Đến"))
        self.date_to = make_date_edit(date.today())
        controls.addWidget(self.date_to)
        apply_button = make_button("Xem", "search", "primary")
        apply_button.clicked.connect(self.load_chart)
        controls.addWidget(apply_button)
        self.chart_card.add_layout(controls)
        self.chart = ChartWidget(min_height=290)
        self.chart_card.add(self.chart, 1)
        self.chart_summary = hint_label("")
        self.chart_card.add(self.chart_summary)
        self.mode_combo.currentIndexChanged.connect(lambda _i: self.load_chart())
        self.kind_combo.currentIndexChanged.connect(lambda _i: self.load_chart())
        middle.addWidget(self.chart_card, 3)

        self.stock_card = Card("Cảnh báo tồn kho", "Sản phẩm đang kinh doanh sắp hết hoặc đã hết hàng")
        self.stock_list = QListWidget()
        self.stock_list.setMinimumWidth(270)
        self.stock_list.setWordWrap(True)
        self.stock_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stock_empty = EmptyState("check", "Tồn kho ổn định", "Không có sản phẩm nào dưới ngưỡng cảnh báo.")
        self.stock_stack = QStackedWidget()
        self.stock_stack.addWidget(self.stock_list)
        self.stock_stack.addWidget(self.stock_empty)
        self.stock_card.add(self.stock_stack, 1)
        open_inventory = make_button("Mở Quản lý kho hàng", "package")
        open_inventory.clicked.connect(lambda: self.ctx.navigate("inventory"))
        self.stock_card.add(open_inventory)
        middle.addWidget(self.stock_card, 1)
        layout.addLayout(middle)

        # --- Giao dịch gần đây ---
        self.recent_card = Card("Giao dịch gần đây", "Nhấn đúp vào một giao dịch để xem chi tiết hóa đơn")
        view_all = make_button("Xem tất cả", "receipt", "ghost")
        view_all.clicked.connect(lambda: self.ctx.navigate("invoices"))
        self.recent_card.add_header_widget(view_all)
        self.recent_table = QTableWidget()
        setup_table(self.recent_table, ["Mã hóa đơn", "Thời gian giao dịch", "Khách hàng", "Nhân viên bán hàng",
                                        "Tổng thanh toán", "Trạng thái"], stretch=2)
        self.recent_table.setMinimumHeight(320)
        self.recent_table.doubleClicked.connect(lambda _i: self.open_selected())
        self.recent_empty = EmptyState("receipt", "Chưa có giao dịch nào",
                                       "Hãy vào màn hình Bán hàng POS để tạo hóa đơn đầu tiên.")
        self.recent_stack = QStackedWidget()
        self.recent_stack.addWidget(self.recent_table)
        self.recent_stack.addWidget(self.recent_empty)
        self.recent_card.add(self.recent_stack)
        layout.addWidget(self.recent_card)
        layout.addWidget(hint_label(f"Quy tắc tính: {config.REVENUE_RULE}"))

        self.range_buttons[1].setChecked(True)

    # ------------------------------------------------------------------ dữ liệu
    def refresh(self) -> None:
        threshold = self.ctx.settings.low_stock_threshold
        k = self.ctx.reports.dashboard_kpis(threshold)
        self.kpi_revenue.set_value(format_money(k["revenue"]),
                                   f"Hôm nay: {format_money(k['today_revenue'])}  •  ≈ {short_money(k['revenue'])}")
        self.kpi_orders.set_value(format_number(k["orders"]),
                                  f"Hôm nay: {k['today_orders']} đơn  •  Đã hủy: {k['cancelled_orders']}")
        self.kpi_products.set_value(format_number(k["product_count"]),
                                    f"{k['active_products']} đang kinh doanh  •  "
                                    f"{k['product_count'] - k['active_products']} ngừng kinh doanh")
        self.kpi_stock.set_value(format_number(k["total_units"]),
                                 f"{k['low_stock']} sắp hết  •  {k['out_of_stock']} hết hàng (ngưỡng ≤ {threshold})")
        self.kpi_customers.set_value(format_number(k["customer_count"]),
                                     f"Khách mới tháng này: {k['new_customers']}")
        self._load_low_stock(threshold)
        self._load_recent()
        self.load_chart()

    def _load_low_stock(self, threshold: int) -> None:
        self.stock_list.clear()
        products = self.ctx.reports.low_stock(threshold)
        for p in products[:30]:
            state = "HẾT HÀNG" if p.stock_quantity == 0 else f"Còn {p.stock_quantity}"
            item = QListWidgetItem(f"{p.product_name}\n{p.sku}  •  {state}")
            item.setIcon(self.ctx.theme.icon("alert", "danger" if p.stock_quantity == 0 else "warning"))
            item.setToolTip(f"{p.product_name} – tồn kho: {p.stock_quantity}")
            self.stock_list.addItem(item)
        self.stock_stack.setCurrentIndex(0 if products else 1)

    def _load_recent(self) -> None:
        invoices = self.ctx.reports.recent_invoices(12)
        rows = []
        for inv in invoices:
            rows.append([
                make_item(inv.invoice_code, data=inv.invoice_id, bold=True),
                make_item(format_datetime(inv.created_at), sort=inv.created_at),
                make_item(inv.customer_name),
                make_item(inv.employee_name or "—"),
                make_item(format_money(inv.total_amount), align=ALIGN_RIGHT, sort=inv.total_amount, bold=True),
                make_item(inv.status_label, color="teal" if inv.is_paid else "danger"),
            ])
        fill_table(self.recent_table, rows)
        self.recent_stack.setCurrentIndex(0 if invoices else 1)

    def _quick_range(self, days: int | None, button) -> None:
        for other in self.range_buttons:
            other.setChecked(other is button)
        today = date.today()
        if days is None:
            self.date_from.setDate(to_qdate(today.replace(month=1, day=1)))
            self.mode_combo.setCurrentIndex(1)
        else:
            self.date_from.setDate(to_qdate(today - timedelta(days=days - 1)))
            self.mode_combo.setCurrentIndex(0)
        self.date_to.setDate(to_qdate(today))
        self.load_chart()

    @safe_slot
    def load_chart(self) -> None:
        start, end = from_qdate(self.date_from.date()), from_qdate(self.date_to.date())
        if start > end:
            show_warning(self, "Khoảng thời gian không hợp lệ", "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
            return
        mode = self.mode_combo.currentData()
        kind = self.kind_combo.currentData()
        if mode == "month":
            data = self.ctx.reports.revenue_by_month(start, end)
            labels = [f"T{row['period'][5:]}/{row['period'][2:4]}" for row in data]
        else:
            if (end - start).days > 366:
                show_warning(self, "Khoảng thời gian quá dài",
                             "Xem theo ngày tối đa 366 ngày. Hãy chọn \"Theo tháng\" cho khoảng thời gian dài hơn.")
                return
            data = self.ctx.reports.revenue_by_day(start, end)
            labels = [f"{row['period'][8:]}/{row['period'][5:7]}" for row in data]
        revenues = [row["revenue"] for row in data]
        counts = [row["invoice_count"] for row in data]
        self.chart.plot_revenue(labels, revenues, counts, kind=kind)
        self.chart_summary.setText(
            f"Từ {format_date(start)} đến {format_date(end)}: doanh thu {format_money(sum(revenues))} "
            f"từ {sum(counts)} hóa đơn đã thanh toán."
        )

    def open_selected(self) -> None:
        invoice_id = selected_id(self.recent_table)
        if invoice_id:
            open_invoice(self, self.ctx, invoice_id)
            self.refresh()
