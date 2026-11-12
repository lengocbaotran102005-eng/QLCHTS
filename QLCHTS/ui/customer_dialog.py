"""Biểu mẫu thông tin khách hàng (dùng chung cho màn hình Khách hàng và nút "Thêm khách" ở POS)."""
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget

from models.customer import Customer
from ui.widgets import field_label, handle_exception, hint_label, make_button, section_title


class CustomerForm(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.customer_id: int | None = None
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(12)
        self.code_edit = QLineEdit()
        self.code_edit.setReadOnly(True)
        self.code_edit.setPlaceholderText("Tự động sinh khi lưu")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ví dụ: Nguyễn Thị Lan")
        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("10 chữ số, bắt đầu bằng 0")
        self.phone_edit.setMaxLength(14)
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Không bắt buộc")
        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("Số nhà, đường, phường/xã, tỉnh/thành")
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("Sở thích, size nhẫn, ngày kỷ niệm...")
        self.note_edit.setFixedHeight(70)
        for widget in (self.code_edit, self.name_edit, self.phone_edit, self.email_edit, self.address_edit):
            widget.setMinimumHeight(36)
        form.addRow(field_label("Mã khách hàng"), self.code_edit)
        form.addRow(field_label("Họ tên *"), self.name_edit)
        form.addRow(field_label("Số điện thoại *"), self.phone_edit)
        form.addRow(field_label("Email"), self.email_edit)
        form.addRow(field_label("Địa chỉ"), self.address_edit)
        form.addRow(field_label("Ghi chú"), self.note_edit)

    def set_customer(self, customer: Customer | None) -> None:
        customer = customer or Customer()
        self.customer_id = customer.customer_id
        self.code_edit.setText(customer.customer_code)
        self.name_edit.setText(customer.customer_name)
        self.phone_edit.setText(customer.phone)
        self.email_edit.setText(customer.email)
        self.address_edit.setText(customer.address)
        self.note_edit.setPlainText(customer.note)

    def customer(self) -> Customer:
        return Customer(
            customer_id=self.customer_id,
            customer_code=self.code_edit.text().strip(),
            customer_name=self.name_edit.text(),
            phone=self.phone_edit.text(),
            email=self.email_edit.text(),
            address=self.address_edit.text(),
            note=self.note_edit.toPlainText(),
        )


class CustomerDialog(QDialog):
    """Hộp thoại thêm nhanh khách hàng; sau khi lưu, ``customer_id`` chứa mã khách vừa tạo."""

    def __init__(self, ctx, parent=None, customer: Customer | None = None):
        super().__init__(parent)
        self.ctx = ctx
        self.customer_id: int | None = None
        self.setWindowTitle("Thông tin khách hàng")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(section_title("Thêm khách hàng mới" if customer is None else "Cập nhật khách hàng"))
        layout.addWidget(hint_label("Khách hàng được lưu vào CSDL để tra cứu lịch sử mua hàng và tích lũy."))
        self.form = CustomerForm()
        self.form.set_customer(customer)
        layout.addWidget(self.form)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = make_button("Hủy bỏ", variant="ghost")
        cancel.clicked.connect(self.reject)
        save = make_button("Lưu khách hàng", "save", "primary")
        save.clicked.connect(self._save)
        save.setDefault(True)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def _save(self) -> None:
        try:
            self.customer_id = self.ctx.customers.save(self.form.customer())
        except Exception as exc:  # noqa: BLE001
            handle_exception(self, exc)
            return
        self.accept()
