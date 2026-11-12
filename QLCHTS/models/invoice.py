"""Model hóa đơn và chi tiết hóa đơn.

Chi tiết hóa đơn lưu "ảnh chụp" (snapshot) tên, SKU, chất liệu, trọng lượng và đơn
giá tại thời điểm bán, nên việc sửa sản phẩm sau này không làm sai hóa đơn cũ.
"""
from dataclasses import dataclass

import config
from models.base import row_to_kwargs
from utils.formatters import format_decimal, format_money, format_weight


@dataclass
class Invoice:
    invoice_id: int | None = None
    invoice_code: str = ""
    customer_id: int | None = None
    customer_name: str = config.WALK_IN_CUSTOMER
    customer_phone: str = ""
    customer_address: str = ""
    employee_id: int | None = None
    employee_name: str = ""
    created_at: str = ""
    subtotal: int = 0
    discount_type: str = config.DISCOUNT_AMOUNT
    discount_value: float = 0.0
    discount_amount: int = 0
    vat_rate: float = 0.0
    vat_amount: int = 0
    total_amount: int = 0
    amount_received: int = 0
    change_amount: int = 0
    payment_method: str = config.PAYMENT_CASH
    status: str = config.INVOICE_PAID
    note: str = ""
    cancelled_at: str = ""
    cancel_reason: str = ""
    item_count: int = 0
    customer_code: str = ""

    @classmethod
    def from_row(cls, row) -> "Invoice":
        invoice = cls(**row_to_kwargs(cls, row))
        for attr in ("customer_phone", "customer_address", "employee_name", "note",
                     "cancelled_at", "cancel_reason", "customer_code"):
            if getattr(invoice, attr) is None:
                setattr(invoice, attr, "")
        return invoice

    @property
    def status_label(self) -> str:
        return config.INVOICE_STATUS_LABELS.get(self.status, self.status)

    @property
    def is_paid(self) -> bool:
        return self.status == config.INVOICE_PAID

    @property
    def taxable_amount(self) -> int:
        return self.subtotal - self.discount_amount

    @property
    def discount_label(self) -> str:
        """Mô tả mức chiết khấu đã áp dụng, ví dụ '5%' hoặc 'theo số tiền'."""
        if self.discount_amount <= 0:
            return "Không áp dụng"
        if self.discount_type == config.DISCOUNT_PERCENT:
            return f"{format_decimal(self.discount_value, 2)}%"
        return f"Giảm {format_money(self.discount_value)}"


@dataclass
class InvoiceDetail:
    detail_id: int | None = None
    invoice_id: int | None = None
    product_id: int | None = None
    product_name: str = ""
    sku: str = ""
    category_name: str = ""
    material: str = ""
    weight: float = 0.0
    weight_unit: str = ""
    quantity: int = 0
    unit_price: int = 0
    unit_cost: int = 0
    line_total: int = 0

    @classmethod
    def from_row(cls, row) -> "InvoiceDetail":
        detail = cls(**row_to_kwargs(cls, row))
        detail.category_name = detail.category_name or ""
        detail.material = detail.material or ""
        detail.weight_unit = detail.weight_unit or ""
        return detail

    @property
    def weight_text(self) -> str:
        return format_weight(self.weight, self.weight_unit)
