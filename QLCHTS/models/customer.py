"""Model khách hàng và nhân viên bán hàng."""
from dataclasses import dataclass

from models.base import row_to_kwargs


@dataclass
class Customer:
    customer_id: int | None = None
    customer_code: str = ""
    customer_name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    note: str = ""
    created_at: str = ""
    updated_at: str = ""
    # Thông tin tổng hợp (tính bằng truy vấn JOIN + COUNT/SUM, không lưu trong bảng)
    order_count: int = 0
    total_spent: int = 0
    last_purchase: str = ""

    @classmethod
    def from_row(cls, row) -> "Customer":
        customer = cls(**row_to_kwargs(cls, row))
        for attr in ("phone", "email", "address", "note", "last_purchase"):
            if getattr(customer, attr) is None:
                setattr(customer, attr, "")
        return customer

    @property
    def display_name(self) -> str:
        return f"{self.customer_name} – {self.phone}" if self.phone else self.customer_name


@dataclass
class Employee:
    employee_id: int | None = None
    employee_code: str = ""
    employee_name: str = ""
    role: str = "Nhân viên bán hàng"
    phone: str = ""
    is_active: bool = True
    created_at: str = ""

    @classmethod
    def from_row(cls, row) -> "Employee":
        employee = cls(**row_to_kwargs(cls, row))
        employee.is_active = bool(employee.is_active)
        employee.phone = employee.phone or ""
        return employee
