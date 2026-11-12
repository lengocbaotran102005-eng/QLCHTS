"""Phân hệ 7 – Báo cáo và thống kê: doanh thu theo ngày/tháng, sản phẩm bán chạy, danh mục, tồn kho thấp."""
import csv
from datetime import date, timedelta

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config
from ui.chart_widget import ChartWidget
from ui.widgets import (
    ALIGN_RIGHT,
    BasePage,
    Card,
    KpiCard,
    fill_table,
    from_qdate,
    hint_label,
    make_button,
    make_date_edit,
    make_item,
    make_spin,
    safe_slot,
    setup_table,
    show_info,
    show_warning,
    to_qdate,
)
from utils.formatters import format_date, format_decimal, format_money, format_number


def _month_start(value: date) -> date:
    return value.replace(day=1)


class ReportsPage(BasePage):
    title = "Báo cáo thống kê"
    subtitle = "Tổng hợp bằng truy vấn SQL (SELECT, SUM, COUNT, GROUP BY, JOIN) trên dữ liệu đã lưu"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("ScrollContent")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)
        scroll.setWidget(body)
        self.root.addWidget(scroll)

        # --- Bộ lọc thời gian ---
        filters = Card(margins=14)
        row = QHBoxLayout()
        row.setSpacing(8)
        today = date.today()
        presets = (
            ("Tháng này", _month_start(today), today),
            ("Tháng trước", _month_start(_month_start(today) - timedelta(days=1)), _month_start(today) - timedelta(days=1)),
            ("30 ngày", today - timedelta(days=29), today),
            ("90 ngày", today - timedelta(days=89), today),
            ("Năm nay", today.replace(month=1, day=1), today),
        )
        for text, start, end in presets:
            chip = make_button(text, variant="chip")
            chip.clicked.connect(lambda _c=False, s=start, e=end: self._set_range(s, e))
            row.addWidget(chip)
        row.addStretch()
        row.addWidget(QLabel("Từ ngày"))
        self.date_from = make_date_edit(today - timedelta(days=89))
        row.addWidget(self.date_from)
        row.addWidget(QLabel("Đến ngày"))
        self.date_to = make_date_edit(today)
        row.addWidget(self.date_to)
        run = make_button("Xem báo cáo", "chart", "primary")
        run.clicked.connect(self.load_report)
        row.addWidget(run)
        export = make_button("Xuất CSV", "export")
        export.setToolTip("Xuất bảng của thẻ đang xem ra tệp CSV (mở được bằng Excel)")
        export.clicked.connect(self.export_csv)
        row.addWidget(export)
        filters.add_layout(row)
        filters.add(hint_label(f"Quy tắc: {config.REVENUE_RULE} Hóa đơn chưa thanh toán không tồn tại trong hệ "
                               "thống vì POS chỉ lưu hóa đơn khi thanh toán thành công."))
        layout.addWidget(filters)

        # --- KPI của khoảng thời gian ---
        kpis = QHBoxLayout()
        kpis.setSpacing(16)
        self.kpi_revenue = KpiCard("Doanh thu thực thu", "money", "gold")
        self.kpi_count = KpiCard("Số giao dịch đã thanh toán", "receipt", "teal")
        self.kpi_average = KpiCard("Giá trị trung bình / đơn", "trend", "sky")
        self.kpi_profit = KpiCard("Lợi nhuận gộp ước tính", "star", "rose")
        self.kpi_items = KpiCard("Sản phẩm đã bán", "gem", "warning")
        for card in (self.kpi_revenue, self.kpi_count, self.kpi_average, self.kpi_profit, self.kpi_items):
            kpis.addWidget(card)
        layout.addLayout(kpis)

        # --- Các thẻ báo cáo ---
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(640)
        self.day_chart, self.day_table = self._chart_tab("Doanh thu theo ngày",
                                                         ["Ngày", "Số hóa đơn", "Tiền hàng", "Chiết khấu", "VAT",
                                                          "Doanh thu thực thu"])
        self.month_chart, self.month_table = self._chart_tab("Doanh thu theo tháng",
                                                             ["Tháng", "Số hóa đơn", "Tiền hàng", "Chiết khấu", "VAT",
                                                              "Doanh thu thực thu"])
        self.best_chart, self.best_table = self._chart_tab("Sản phẩm bán chạy",
                                                           ["Hạng", "SKU", "Sản phẩm", "Danh mục", "SL bán",
                                                            "Số hóa đơn", "Doanh số dòng hàng", "Tồn hiện tại"])
        self.category_chart, self.category_table = self._chart_tab("Theo danh mục",
                                                                   ["Danh mục", "Số lượng bán", "Doanh số dòng hàng",
                                                                    "Tỷ trọng"])
        self.tabs.addTab(self._low_stock_tab(), "Tồn kho thấp")
        layout.addWidget(self.tabs)

    def _chart_tab(self, title: str, headers: list[str]):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(14, 14, 14, 14)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        chart = ChartWidget(min_height=250)
        table = QTableWidget()
        setup_table(table, headers, stretch=2 if len(headers) > 6 else 0)
        table.setMinimumHeight(170)
        splitter.addWidget(chart)
        splitter.addWidget(table)
        splitter.setSizes([340, 260])
        page_layout.addWidget(splitter)
        self.tabs.addTab(page, title)
        return chart, table

    def _low_stock_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 14, 14, 14)
        row = QHBoxLayout()
        row.addWidget(QLabel("Hiển thị sản phẩm đang kinh doanh có tồn kho ≤"))
        self.threshold_spin = make_spin()
        self.threshold_spin.setRange(0, 100000)
        self.threshold_spin.setMinimumHeight(34)
        self.threshold_spin.valueChanged.connect(lambda _v: self._load_low_stock())
        row.addWidget(self.threshold_spin)
        row.addStretch()
        layout.addLayout(row)
        self.low_table = QTableWidget()
        setup_table(self.low_table, ["SKU", "Sản phẩm", "Danh mục", "Chất liệu", "Tồn kho", "Giá bán", "Mức tồn"],
                    stretch=1)
        layout.addWidget(self.low_table, 1)
        self.low_hint = hint_label("")
        layout.addWidget(self.low_hint)
        return page

    # ------------------------------------------------------------------ dữ liệu
    def refresh(self) -> None:
        self.threshold_spin.blockSignals(True)
        self.threshold_spin.setValue(self.ctx.settings.low_stock_threshold)
        self.threshold_spin.blockSignals(False)
        self.load_report()

    def _set_range(self, start: date, end: date) -> None:
        self.date_from.setDate(to_qdate(start))
        self.date_to.setDate(to_qdate(end))
        self.load_report()

    @safe_slot
    def load_report(self) -> None:
        start, end = from_qdate(self.date_from.date()), from_qdate(self.date_to.date())
        if start > end:
            show_warning(self, "Khoảng thời gian không hợp lệ", "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
            return
        reports = self.ctx.reports
        s = reports.summary(start, end)
        self.kpi_revenue.set_value(format_money(s["revenue"]),
                                   f"Chưa gồm VAT: {format_money(s['net_sales'])}  •  VAT: {format_money(s['vat'])}")
        self.kpi_count.set_value(format_number(s["invoice_count"]),
                                 f"Đã hủy: {s['cancelled_count']} ({format_money(s['cancelled_amount'])}) – không tính")
        self.kpi_average.set_value(format_money(s["average_order"]),
                                   f"Chiết khấu đã giảm: {format_money(s['discount'])}")
        self.kpi_profit.set_value(format_money(s["gross_profit"]),
                                  f"= Doanh thu chưa VAT − Giá vốn ({format_money(s['cost'])})")
        self.kpi_items.set_value(format_number(s["items_sold"]), f"Từ {format_date(start)} đến {format_date(end)}")

        if (end - start).days <= 366:
            self._fill_period(self.day_chart, self.day_table, reports.revenue_by_day(start, end), day=True)
        else:
            fill_table(self.day_table, [])
            self.day_chart.show_empty("Khoảng thời gian dài hơn 1 năm – vui lòng xem thẻ \"Doanh thu theo tháng\"")
        self._fill_period(self.month_chart, self.month_table, reports.revenue_by_month(start, end), day=False)
        self._load_best_sellers(start, end)
        self._load_categories(start, end)
        self._load_low_stock()

    def _fill_period(self, chart: ChartWidget, table: QTableWidget, data: list[dict], day: bool) -> None:
        if day:
            labels = [f"{r['period'][8:]}/{r['period'][5:7]}" for r in data]
        else:
            labels = [f"T{r['period'][5:]}/{r['period'][:4]}" for r in data]
        chart.plot_revenue(labels, [r["revenue"] for r in data], [r["invoice_count"] for r in data], kind="bar")
        rows = []
        for r in data:
            period = format_date(r["period"]) if day else f"{r['period'][5:]}/{r['period'][:4]}"
            rows.append([
                make_item(period, sort=r["period"]),
                make_item(str(r["invoice_count"]), align=ALIGN_RIGHT, sort=r["invoice_count"]),
                make_item(format_money(r["subtotal"]), align=ALIGN_RIGHT, sort=r["subtotal"]),
                make_item(format_money(r["discount"]), align=ALIGN_RIGHT, sort=r["discount"]),
                make_item(format_money(r["vat"]), align=ALIGN_RIGHT, sort=r["vat"]),
                make_item(format_money(r["revenue"]), align=ALIGN_RIGHT, sort=r["revenue"], bold=True,
                          color="gold" if r["revenue"] else None),
            ])
        if data:
            rows.append([
                make_item("TỔNG CỘNG", bold=True, sort="9999"),
                make_item(str(sum(r["invoice_count"] for r in data)), align=ALIGN_RIGHT, bold=True, sort=10 ** 12),
                make_item(format_money(sum(r["subtotal"] for r in data)), align=ALIGN_RIGHT, bold=True, sort=10 ** 15),
                make_item(format_money(sum(r["discount"] for r in data)), align=ALIGN_RIGHT, bold=True, sort=10 ** 15),
                make_item(format_money(sum(r["vat"] for r in data)), align=ALIGN_RIGHT, bold=True, sort=10 ** 15),
                make_item(format_money(sum(r["revenue"] for r in data)), align=ALIGN_RIGHT, bold=True, color="gold",
                          sort=10 ** 15),
            ])
        fill_table(table, rows)

    def _load_best_sellers(self, start: date, end: date) -> None:
        data = self.ctx.reports.best_sellers(start, end, limit=10)
        self.best_chart.plot_hbar([r["product_name"] for r in data], [r["quantity"] for r in data], " sp")
        rows = []
        for rank, r in enumerate(data, start=1):
            rows.append([
                make_item(f"#{rank}", sort=rank, bold=rank <= 3, color="gold" if rank <= 3 else None),
                make_item(r["sku"]),
                make_item(r["product_name"], bold=True),
                make_item(r["category_name"] or "—"),
                make_item(str(r["quantity"]), align=ALIGN_RIGHT, sort=r["quantity"], bold=True),
                make_item(str(r["invoice_count"]), align=ALIGN_RIGHT, sort=r["invoice_count"]),
                make_item(format_money(r["sales"]), align=ALIGN_RIGHT, sort=r["sales"]),
                make_item(str(r["stock_quantity"]), align=ALIGN_RIGHT, sort=r["stock_quantity"]),
            ])
        fill_table(self.best_table, rows)

    def _load_categories(self, start: date, end: date) -> None:
        data = self.ctx.reports.revenue_by_category(start, end)
        self.category_chart.plot_donut([r["category_name"] for r in data], [r["sales"] for r in data])
        total = sum(r["sales"] for r in data) or 1
        rows = [[
            make_item(r["category_name"], bold=True),
            make_item(str(r["quantity"]), align=ALIGN_RIGHT, sort=r["quantity"]),
            make_item(format_money(r["sales"]), align=ALIGN_RIGHT, sort=r["sales"]),
            make_item(f"{format_decimal(r['sales'] / total * 100, 1)}%", align=ALIGN_RIGHT, sort=r["sales"]),
        ] for r in data]
        fill_table(self.category_table, rows)

    def _load_low_stock(self) -> None:
        threshold = self.threshold_spin.value()
        products = self.ctx.reports.low_stock(threshold)
        rows = []
        for p in products:
            out = p.stock_quantity == 0
            rows.append([
                make_item(p.sku),
                make_item(p.product_name, bold=True),
                make_item(p.category_name),
                make_item(p.material),
                make_item(str(p.stock_quantity), align=ALIGN_RIGHT, sort=p.stock_quantity, bold=True,
                          color="danger" if out else "warning"),
                make_item(format_money(p.selling_price), align=ALIGN_RIGHT, sort=p.selling_price),
                make_item("Hết hàng" if out else "Sắp hết", color="danger" if out else "warning", bold=True),
            ])
        fill_table(self.low_table, rows)
        self.low_hint.setText(f"{len(products)} sản phẩm cần chú ý nhập thêm hàng." if products
                              else "Không có sản phẩm nào dưới ngưỡng – tồn kho ổn định.")

    # ------------------------------------------------------------------ xuất CSV
    @safe_slot
    def export_csv(self) -> None:
        index = self.tabs.currentIndex()
        table = [self.day_table, self.month_table, self.best_table, self.category_table, self.low_table][index]
        if table.rowCount() == 0:
            show_warning(self, "Không có dữ liệu", "Bảng hiện tại chưa có dữ liệu để xuất.")
            return
        name = self.tabs.tabText(index)
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        default = f"{folder}/BaoCao_{name.replace(' ', '_')}_{date.today():%Y%m%d}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Xuất báo cáo CSV", default, "Tệp CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow([table.horizontalHeaderItem(c).text() for c in range(table.columnCount())])
                for r in range(table.rowCount()):
                    writer.writerow([table.item(r, c).text() if table.item(r, c) else ""
                                     for c in range(table.columnCount())])
        except OSError as exc:
            show_warning(self, "Không thể lưu tệp", f"Không ghi được tệp CSV (tệp có thể đang mở trong Excel).\n{exc}")
            return
        self.notify(f"Đã xuất báo cáo \"{name}\" ra {path}")
        show_info(self, "Xuất CSV thành công", f"Đã lưu báo cáo tại:\n{path}")
