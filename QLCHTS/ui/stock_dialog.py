"""Hộp thoại nhập kho / điều chỉnh tồn kho (kiểm kê) – mọi thay đổi đều được ghi lịch sử kho."""
from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout

from models.product import Product
from ui.widgets import (
    field_label,
    handle_exception,
    hint_label,
    make_button,
    make_combo,
    make_spin,
    section_title,
)
from utils.formatters import format_money, format_weight

ADJUST_REASONS = [
    "Kiểm kê thực tế",
    "Hàng lỗi / hư hỏng",
    "Thất lạc",
    "Chuyển sang gia công lại",
    "Nhập nhầm số lượng",
    "Khác",
]


class StockDialog(QDialog):
    """mode = 'import' (nhập thêm hàng) hoặc 'adjust' (điều chỉnh về số lượng thực tế)."""

    def __init__(self, ctx, product: Product, mode: str = "import", parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.product = product
        self.mode = mode
        self.new_stock: int | None = None
        is_import = mode == "import"
        self.setWindowTitle("Nhập kho" if is_import else "Điều chỉnh tồn kho")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(section_title("Nhập thêm hàng vào kho" if is_import else "Điều chỉnh tồn kho theo kiểm kê"))
        info = QLabel(f"<b>{product.product_name}</b><br>SKU: {product.sku}  •  "
                      f"{format_weight(product.weight, product.weight_unit)}  •  Giá nhập: "
                      f"{format_money(product.cost_price)}<br>Tồn kho hiện tại: <b>{product.stock_quantity}</b>")
        info.setObjectName("MutedText")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.quantity = make_spin()
        self.quantity.setRange(1 if is_import else 0, 1_000_000)
        self.quantity.setValue(1 if is_import else product.stock_quantity)
        self.quantity.setMinimumHeight(36)
        form.addRow(field_label("Số lượng nhập thêm *" if is_import else "Số lượng thực tế *"), self.quantity)
        self.preview = hint_label("")
        form.addRow("", self.preview)
        if is_import:
            self.reference = QLineEdit()
            self.reference.setPlaceholderText("Ví dụ: PN-2026-015 (không bắt buộc)")
            self.reference.setMinimumHeight(36)
            form.addRow(field_label("Mã phiếu nhập"), self.reference)
            self.note = QLineEdit()
            self.note.setPlaceholderText("Nhà cung cấp, lô hàng...")
            self.note.setMinimumHeight(36)
            form.addRow(field_label("Ghi chú"), self.note)
        else:
            self.reason_combo = make_combo([(r, r) for r in ADJUST_REASONS])
            form.addRow(field_label("Lý do *"), self.reason_combo)
            self.note = QLineEdit()
            self.note.setPlaceholderText("Mô tả chi tiết lý do điều chỉnh")
            self.note.setMinimumHeight(36)
            form.addRow(field_label("Chi tiết"), self.note)
        layout.addLayout(form)
        layout.addWidget(hint_label("Thời điểm và người thực hiện được lưu vào bảng inventory_transactions."))

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = make_button("Hủy bỏ", variant="ghost")
        cancel.clicked.connect(self.reject)
        save = make_button("Xác nhận nhập kho" if is_import else "Lưu điều chỉnh", "check", "primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self.quantity.valueChanged.connect(self._update_preview)
        self._update_preview()

    def _update_preview(self) -> None:
        value = self.quantity.value()
        if self.mode == "import":
            self.preview.setText(f"Tồn kho sau khi nhập: {self.product.stock_quantity + value}")
        else:
            delta = value - self.product.stock_quantity
            sign = "+" if delta > 0 else ""
            self.preview.setText(f"Chênh lệch: {sign}{delta}  →  tồn kho mới: {value}")

    def _employee_name(self) -> str:
        employees = self.ctx.settings.employees(active_only=True)
        return employees[0].employee_name if employees else ""

    def _save(self) -> None:
        try:
            if self.mode == "import":
                self.new_stock = self.ctx.inventory.import_stock(
                    self.product.product_id, self.quantity.value(), self.reference.text(), self.note.text(),
                    created_by=self._employee_name())
            else:
                reason = self.reason_combo.currentText()
                if self.note.text().strip():
                    reason = f"{reason}: {self.note.text().strip()}"
                self.new_stock = self.ctx.inventory.adjust_stock(
                    self.product.product_id, self.quantity.value(), reason, created_by=self._employee_name())
        except Exception as exc:  # noqa: BLE001
            handle_exception(self, exc)
            return
        self.accept()
