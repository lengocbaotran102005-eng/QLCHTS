"""Phân hệ 4 – Quản lý khách hàng: thêm, sửa, tìm kiếm, xóa và xem lịch sử mua hàng."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QTableWidget, QVBoxLayout, QWidget

from ui.customer_dialog import CustomerForm
from ui.invoice_dialog import open_invoice
from ui.widgets import (
    ALIGN_RIGHT,
    BasePage,
    Card,
    SearchBox,
    ask_confirm,
    fill_table,
    hint_label,
    make_button,
    make_item,
    safe_slot,
    select_by_id,
    selected_id,
    setup_table,
    show_info,
)
from utils.formatters import format_date, format_datetime, format_money


class CustomersPage(BasePage):
    title = "Quản lý khách hàng"
    subtitle = "Lưu thông tin liên hệ, tra cứu lịch sử mua hàng – hỗ trợ cả giao dịch khách lẻ"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.current_id: int | None = None
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.addWidget(self._build_list())
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([860, 460])
        self.root.addWidget(splitter)

    def _build_list(self) -> QWidget:
        card = Card("Danh sách khách hàng", "Số đơn và tổng mua chỉ tính hóa đơn đã thanh toán")
        add_button = make_button("Thêm khách hàng", "user-plus", "primary")
        add_button.clicked.connect(self.new_customer)
        card.add_header_widget(add_button)
        self.search = SearchBox("Tìm theo họ tên, số điện thoại, mã KH, địa chỉ...")
        self.search.search_requested.connect(lambda _t: self.load_customers())
        card.add(self.search)
        self.table = QTableWidget()
        setup_table(self.table, ["Mã KH", "Họ tên", "Số điện thoại", "Email", "Địa chỉ", "Số đơn", "Tổng mua",
                                 "Mua gần nhất"], stretch=4)
        self.table.itemSelectionChanged.connect(self._on_selection)
        card.add(self.table, 1)
        self.count_label = hint_label("")
        card.add(self.count_label)
        return card

    def _build_detail(self) -> QWidget:
        holder = QWidget()
        holder.setMinimumWidth(400)
        holder.setMaximumWidth(560)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.form_card = Card("Thêm khách hàng mới", "Họ tên và số điện thoại là bắt buộc")
        self.form = CustomerForm()
        self.form_card.add(self.form)
        buttons = QHBoxLayout()
        reset = make_button("Làm mới", "refresh", "ghost")
        reset.clicked.connect(self.new_customer)
        self.delete_button = make_button("Xóa", "trash", "danger")
        self.delete_button.clicked.connect(self.delete_customer)
        save = make_button("Lưu khách hàng", "save", "primary")
        save.clicked.connect(self.save_customer)
        buttons.addWidget(reset)
        buttons.addWidget(self.delete_button)
        buttons.addStretch()
        buttons.addWidget(save)
        self.form_card.add_layout(buttons)
        layout.addWidget(self.form_card)

        self.history_card = Card("Lịch sử mua hàng", "Nhấn đúp để mở lại hóa đơn")
        self.history_table = QTableWidget()
        setup_table(self.history_table, ["Mã hóa đơn", "Ngày", "Tổng thanh toán", "Trạng thái"], stretch=0)
        self.history_table.doubleClicked.connect(lambda _i: self._open_history_invoice())
        self.history_card.add(self.history_table, 1)
        self.history_summary = hint_label("Chọn khách hàng để xem lịch sử mua hàng.")
        self.history_card.add(self.history_summary)
        layout.addWidget(self.history_card, 1)
        return holder

    # ------------------------------------------------------------------ dữ liệu
    def refresh(self) -> None:
        self.load_customers()
        if self.current_id is None:
            self.new_customer()

    def load_customers(self) -> None:
        customers = self.ctx.customers.search(self.search.text())
        rows = []
        for c in customers:
            rows.append([
                make_item(c.customer_code, data=c.customer_id),
                make_item(c.customer_name, bold=True),
                make_item(c.phone),
                make_item(c.email or "—"),
                make_item(c.address or "—", tooltip=c.address),
                make_item(str(c.order_count), align=ALIGN_RIGHT, sort=c.order_count),
                make_item(format_money(c.total_spent), align=ALIGN_RIGHT, sort=c.total_spent, bold=True,
                          color="gold" if c.total_spent else None),
                make_item(format_date(c.last_purchase) if c.last_purchase else "—", sort=c.last_purchase or ""),
            ])
        self.table.blockSignals(True)
        fill_table(self.table, rows)
        select_by_id(self.table, self.current_id)
        self.table.blockSignals(False)
        self.count_label.setText(f"{len(customers)} khách hàng.")

    def _on_selection(self) -> None:
        customer_id = selected_id(self.table)
        if customer_id is None:
            return
        try:
            customer = self.ctx.customers.get(customer_id)
        except Exception:  # noqa: BLE001 – khách vừa bị xóa
            return
        self.current_id = customer.customer_id
        self.form.set_customer(customer)
        self.form_card.title_label.setText("Cập nhật khách hàng")
        self.form_card.subtitle_label.setText(f"Ngày tạo: {format_datetime(customer.created_at)}")
        self.delete_button.setEnabled(True)
        self._load_history(customer.customer_id)

    def _load_history(self, customer_id: int) -> None:
        invoices = self.ctx.customers.purchase_history(customer_id)
        rows = []
        for inv in invoices:
            rows.append([
                make_item(inv.invoice_code, data=inv.invoice_id, bold=True),
                make_item(format_datetime(inv.created_at), sort=inv.created_at),
                make_item(format_money(inv.total_amount), align=ALIGN_RIGHT, sort=inv.total_amount),
                make_item(inv.status_label, color="teal" if inv.is_paid else "danger"),
            ])
        fill_table(self.history_table, rows)
        paid = [inv for inv in invoices if inv.is_paid]
        self.history_summary.setText(
            f"{len(paid)} đơn đã thanh toán  •  Tổng mua: {format_money(sum(i.total_amount for i in paid))}"
            + (f"  •  {len(invoices) - len(paid)} đơn đã hủy" if len(invoices) > len(paid) else "")
            if invoices else "Khách hàng chưa có giao dịch nào."
        )

    @safe_slot
    def new_customer(self) -> None:
        self.current_id = None
        self.table.clearSelection()
        self.form.set_customer(None)
        self.form.code_edit.setText(self.ctx.customers.suggest_code())
        self.form_card.title_label.setText("Thêm khách hàng mới")
        self.form_card.subtitle_label.setText("Họ tên và số điện thoại là bắt buộc")
        self.delete_button.setEnabled(False)
        self.history_table.setRowCount(0)
        self.history_summary.setText("Khách hàng mới chưa có lịch sử mua hàng.")
        self.form.name_edit.setFocus()

    @safe_slot
    def save_customer(self) -> None:
        customer = self.form.customer()
        is_new = customer.customer_id is None
        if is_new:
            customer.customer_code = ""  # để CSDL sinh mã chính xác tại thời điểm lưu
        self.current_id = self.ctx.customers.save(customer)
        self.load_customers()
        self._on_selection()
        message = "Đã thêm khách hàng mới." if is_new else "Đã cập nhật thông tin khách hàng."
        self.notify(message)
        show_info(self, "Lưu thành công", message)

    @safe_slot
    def delete_customer(self) -> None:
        if self.current_id is None:
            return
        customer = self.ctx.customers.get(self.current_id)
        if not ask_confirm(self, "Xóa khách hàng", f"Xóa khách hàng \"{customer.customer_name}\" "
                                                   f"({customer.phone}) khỏi cơ sở dữ liệu?", "Xóa", danger=True):
            return
        self.ctx.customers.delete(customer.customer_id)
        self.notify(f"Đã xóa khách hàng \"{customer.customer_name}\".")
        self.current_id = None
        self.load_customers()
        self.new_customer()

    def _open_history_invoice(self) -> None:
        invoice_id = selected_id(self.history_table)
        if invoice_id:
            open_invoice(self, self.ctx, invoice_id)
