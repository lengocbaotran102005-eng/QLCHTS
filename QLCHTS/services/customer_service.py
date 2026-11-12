"""Nghiệp vụ quản lý khách hàng."""
import sqlite3

from errors import BusinessRuleError, NotFoundError, ValidationError
from models.customer import Customer
from models.invoice import Invoice
from repositories.customer_repository import CustomerRepository
from repositories.invoice_repository import InvoiceRepository
from utils.validators import clean_phone, clean_text, is_valid_email, is_valid_phone, require_text


class CustomerService:
    def __init__(self, customer_repo: CustomerRepository, invoice_repo: InvoiceRepository):
        self.customers = customer_repo
        self.invoices = invoice_repo

    def search(self, keyword: str = "") -> list[Customer]:
        return self.customers.search(keyword)

    def get(self, customer_id: int) -> Customer:
        customer = self.customers.get_by_id(customer_id)
        if customer is None:
            raise NotFoundError("Khách hàng không tồn tại hoặc đã bị xóa.")
        return customer

    def suggest_code(self) -> str:
        return self.customers.next_customer_code()

    def purchase_history(self, customer_id: int) -> list[Invoice]:
        return self.invoices.search(customer_id=customer_id)

    def validate(self, customer: Customer) -> Customer:
        customer.customer_name = require_text(customer.customer_name, "họ tên khách hàng", 100)
        customer.phone = clean_phone(customer.phone)
        if not customer.phone:
            raise ValidationError("Vui lòng nhập số điện thoại khách hàng.")
        if not is_valid_phone(customer.phone):
            raise ValidationError("Số điện thoại phải gồm 10 chữ số và bắt đầu bằng số 0 (ví dụ 0901234567).")
        customer.email = (customer.email or "").strip()
        if customer.email and not is_valid_email(customer.email):
            raise ValidationError("Email không đúng định dạng (ví dụ: ten@gmail.com).")
        customer.address = clean_text(customer.address)
        customer.note = (customer.note or "").strip()
        if self.customers.phone_exists(customer.phone, exclude_id=customer.customer_id):
            raise ValidationError(f"Số điện thoại {customer.phone} đã thuộc về một khách hàng khác.")
        return customer

    def save(self, customer: Customer) -> int:
        """Thêm mới (khi chưa có customer_id) hoặc cập nhật khách hàng."""
        self.validate(customer)
        try:
            if customer.customer_id:
                self.get(customer.customer_id)
                self.customers.update(customer)
                return customer.customer_id
            return self.customers.insert(customer)
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"Không thể lưu khách hàng do trùng dữ liệu ({exc}).") from exc

    def delete(self, customer_id: int) -> None:
        customer = self.get(customer_id)
        count = self.customers.count_invoices(customer_id)
        if count:
            raise BusinessRuleError(
                f"Khách hàng \"{customer.customer_name}\" đã có {count} hóa đơn nên không thể xóa "
                "(cần giữ lịch sử giao dịch)."
            )
        self.customers.delete(customer_id)
