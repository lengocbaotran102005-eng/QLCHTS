"""Phân hệ 5 – Lịch sử giao dịch và hóa đơn: tra cứu, xem chi tiết, in lại, xuất PDF, hủy hóa đơn."""
from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QSplitter, QTableWidget, QWidget

import config
from ui.invoice_dialog import export_invoice_pdf, open_invoice
from ui.widgets import (
    ALIGN_RIGHT,
    BasePage,
    Card,
    SearchBox,
    ask_confirm,
    ask_text,
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
    show_info,
    show_warning,
    to_qdate,
)
from utils.formatters import format_datetime, format_money, format_weight


class InvoicesPage(BasePage):
    title = "Lịch sử giao dịch"
    subtitle = "Tra cứu hóa đơn đã lưu trong SQLite – xem chi tiết, in lại, xuất PDF hoặc hủy hóa đơn"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.root.addWidget(self._build_filters())
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.addWidget(self._build_list())
        splitter.addWidget(self._build_detail())
        splitter.setSizes([460, 320])
        self.root.addWidget(splitter, 1)

    def _build_filters(self) -> QWidget:
        card = Card(margins=14)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.search = SearchBox("Mã hóa đơn, tên khách hàng, số điện thoại, nhân viên...")
        self.search.search_requested.connect(lambda _t: self.load_invoices())
        self.status_filter = make_combo([("Tất cả trạng thái", None),
                                         (config.INVOICE_STATUS_LABELS[config.INVOICE_PAID], config.INVOICE_PAID),
                                         (config.INVOICE_STATUS_LABELS[config.INVOICE_CANCELLED],
                                          config.INVOICE_CANCELLED)])
        self.status_filter.currentIndexChanged.connect(lambda _i: self.load_invoices())
        self.use_dates = QCheckBox("Lọc theo ngày")
        self.use_dates.setChecked(True)
        self.date_from = make_date_edit(date.today() - timedelta(days=29))
        self.date_to = make_date_edit(date.today())
        self.use_dates.toggled.connect(self._toggle_dates)
        row.addWidget(self.search, 1)
        row.addWidget(self.status_filter)
        row.addWidget(self.use_dates)
        row.addWidget(QLabel("Từ"))
        row.addWidget(self.date_from)
        row.addWidget(QLabel("Đến"))
        row.addWidget(self.date_to)
        apply_button = make_button("Tìm kiếm", "search", "primary")
        apply_button.clicked.connect(self.load_invoices)
        row.addWidget(apply_button)
        card.add_layout(row)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for text, days in (("Hôm nay", 1), ("7 ngày", 7), ("30 ngày", 30), ("90 ngày", 90), ("Tất cả", None)):
            chip = make_button(text, variant="chip")
            chip.clicked.connect(lambda _c=False, d=days: self._quick_range(d))
            chips.addWidget(chip)
        chips.addStretch()
        self.summary_label = hint_label("")
        chips.addWidget(self.summary_label)
        card.add_layout(chips)
        return card

    def _build_list(self) -> QWidget:
        card = Card("Danh sách hóa đơn", "Chọn hóa đơn để xem chi tiết; nhấn đúp để mở bản xem trước / in")
        self.table = QTableWidget()
        setup_table(self.table, ["Mã hóa đơn", "Ngày giờ", "Khách hàng", "Nhân viên", "SL SP", "Tổng tiền hàng",
                                 "Chiết khấu", "VAT", "Tổng thanh toán", "Thanh toán", "Trạng thái"], stretch=2)
        self.table.itemSelectionChanged.connect(self._load_details)
        self.table.doubleClicked.connect(lambda _i: self.open_selected())
        card.add(self.table, 1)
        return card

    def _build_detail(self) -> QWidget:
        self.detail_card = Card("Chi tiết hóa đơn", "Chọn một hóa đơn ở bảng phía trên")
        self.view_button = make_button("Xem / In hóa đơn", "printer", "teal")
        self.view_button.clicked.connect(self.open_selected)
        self.pdf_button = make_button("Xuất PDF", "pdf", "primary")
        self.pdf_button.clicked.connect(self.export_selected)
        self.cancel_button = make_button("Hủy hóa đơn", "cancel", "danger")
        self.cancel_button.clicked.connect(self.cancel_selected)
        for button in (self.view_button, self.pdf_button, self.cancel_button):
            self.detail_card.add_header_widget(button)
            button.setEnabled(False)
        self.detail_table = QTableWidget()
        setup_table(self.detail_table, ["SKU", "Tên sản phẩm (tại thời điểm bán)", "Danh mục", "Chất liệu",
                                        "Trọng lượng", "SL", "Đơn giá", "Thành tiền"], stretch=1, sortable=False)
        self.detail_card.add(self.detail_table, 1)
        self.detail_info = hint_label("")
        self.detail_card.add(self.detail_info)
        return self.detail_card

    # ------------------------------------------------------------------ dữ liệu
    def refresh(self) -> None:
        self.load_invoices()

    def _toggle_dates(self, checked: bool) -> None:
        self.date_from.setEnabled(checked)
        self.date_to.setEnabled(checked)
        self.load_invoices()

    def _quick_range(self, days: int | None) -> None:
        if days is None:
            self.use_dates.setChecked(False)
            return
        today = date.today()
        self.date_from.setDate(to_qdate(today - timedelta(days=days - 1)))
        self.date_to.setDate(to_qdate(today))
        if self.use_dates.isChecked():
            self.load_invoices()
        else:
            self.use_dates.setChecked(True)

    @safe_slot
    def load_invoices(self) -> None:
        date_from = date_to = None
        if self.use_dates.isChecked():
            start, end = from_qdate(self.date_from.date()), from_qdate(self.date_to.date())
            if start > end:
                show_warning(self, "Khoảng thời gian không hợp lệ", "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
                return
            date_from, date_to = start.isoformat(), end.isoformat()
        current = selected_id(self.table)
        invoices = self.ctx.pos.search_invoices(self.search.text(), date_from, date_to,
                                                self.status_filter.currentData())
        rows = []
        for inv in invoices:
            rows.append([
                make_item(inv.invoice_code, data=inv.invoice_id, bold=True),
                make_item(format_datetime(inv.created_at), sort=inv.created_at),
                make_item(inv.customer_name, tooltip=inv.customer_phone),
                make_item(inv.employee_name or "—"),
                make_item(str(inv.item_count), align=ALIGN_RIGHT, sort=inv.item_count),
                make_item(format_money(inv.subtotal), align=ALIGN_RIGHT, sort=inv.subtotal),
                make_item(format_money(inv.discount_amount), align=ALIGN_RIGHT, sort=inv.discount_amount,
                          color="rose" if inv.discount_amount else None),
                make_item(format_money(inv.vat_amount), align=ALIGN_RIGHT, sort=inv.vat_amount),
                make_item(format_money(inv.total_amount), align=ALIGN_RIGHT, sort=inv.total_amount, bold=True),
                make_item(inv.payment_method),
                make_item(inv.status_label, color="teal" if inv.is_paid else "danger", bold=True),
            ])
        self.table.blockSignals(True)
        fill_table(self.table, rows)
        select_by_id(self.table, current)
        self.table.blockSignals(False)
        paid = [inv for inv in invoices if inv.is_paid]
        self.summary_label.setText(
            f"{len(invoices)} hóa đơn  •  Đã thanh toán: {len(paid)}  •  Đã hủy: {len(invoices) - len(paid)}  •  "
            f"Doanh thu thực thu: {format_money(sum(i.total_amount for i in paid))}"
        )
        self._load_details()

    def _load_details(self) -> None:
        invoice_id = selected_id(self.table)
        for button in (self.view_button, self.pdf_button, self.cancel_button):
            button.setEnabled(invoice_id is not None)
        if invoice_id is None:
            self.detail_table.setRowCount(0)
            self.detail_card.title_label.setText("Chi tiết hóa đơn")
            self.detail_card.subtitle_label.setText("Chọn một hóa đơn ở bảng phía trên")
            self.detail_info.setText("")
            return
        try:
            invoice, details = self.ctx.pos.get_invoice(invoice_id)
        except Exception:  # noqa: BLE001
            return
        self.cancel_button.setEnabled(invoice.is_paid)
        self.detail_card.title_label.setText(f"Chi tiết hóa đơn {invoice.invoice_code}")
        self.detail_card.subtitle_label.setText(
            f"{format_datetime(invoice.created_at)}  •  Khách hàng: {invoice.customer_name}"
            f"{' – ' + invoice.customer_phone if invoice.customer_phone else ''}  •  "
            f"Nhân viên: {invoice.employee_name or '—'}  •  {invoice.payment_method}")
        rows = []
        for d in details:
            rows.append([
                make_item(d.sku),
                make_item(d.product_name, bold=True),
                make_item(d.category_name or "—"),
                make_item(d.material),
                make_item(format_weight(d.weight, d.weight_unit, with_grams=True)),
                make_item(str(d.quantity), align=ALIGN_RIGHT),
                make_item(format_money(d.unit_price), align=ALIGN_RIGHT),
                make_item(format_money(d.line_total), align=ALIGN_RIGHT, bold=True),
            ])
        fill_table(self.detail_table, rows)
        info = (f"Tổng tiền hàng {format_money(invoice.subtotal)} − Chiết khấu {format_money(invoice.discount_amount)}"
                f" ({invoice.discount_label}) + VAT {invoice.vat_rate:g}% {format_money(invoice.vat_amount)} = "
                f"Tổng thanh toán {format_money(invoice.total_amount)}")
        if not invoice.is_paid:
            info += f"\nĐÃ HỦY lúc {format_datetime(invoice.cancelled_at)} – Lý do: {invoice.cancel_reason}"
        if invoice.note:
            info += f"\nGhi chú: {invoice.note}"
        self.detail_info.setText(info)

    # ------------------------------------------------------------------ thao tác
    def open_selected(self) -> None:
        invoice_id = selected_id(self.table)
        if invoice_id:
            open_invoice(self, self.ctx, invoice_id)

    @safe_slot
    def export_selected(self) -> None:
        invoice_id = selected_id(self.table)
        if invoice_id:
            export_invoice_pdf(self, self.ctx, invoice_id)

    @safe_slot
    def cancel_selected(self) -> None:
        invoice_id = selected_id(self.table)
        if invoice_id is None:
            return
        invoice, _details = self.ctx.pos.get_invoice(invoice_id)
        if not invoice.is_paid:
            show_warning(self, "Không thể hủy", "Hóa đơn này đã được hủy trước đó.")
            return
        if not ask_confirm(self, "Hủy hóa đơn",
                           f"Hủy hóa đơn {invoice.invoice_code} ({format_money(invoice.total_amount)})?\n\n"
                           "• Tồn kho của các sản phẩm sẽ được hoàn trả.\n"
                           "• Hóa đơn vẫn được lưu để tra cứu nhưng không tính vào doanh thu.",
                           "Tiếp tục hủy", danger=True):
            return
        reason, ok = ask_text(self, "Lý do hủy hóa đơn", "Nhập lý do hủy (bắt buộc):")
        if not ok:
            return
        employees = self.ctx.settings.employees(active_only=True)
        self.ctx.pos.cancel_invoice(invoice_id, reason, cancelled_by=employees[0].employee_name if employees else "")
        self.notify(f"Đã hủy hóa đơn {invoice.invoice_code} và hoàn trả tồn kho.")
        show_info(self, "Đã hủy hóa đơn", f"Hóa đơn {invoice.invoice_code} đã được hủy, tồn kho đã được hoàn trả.")
        self.load_invoices()
        select_by_id(self.table, invoice_id)
