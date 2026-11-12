"""Khởi tạo và gom các repository/service dùng chung cho toàn ứng dụng.

Giao diện chỉ làm việc với các service trong ``AppContext``, không viết SQL trực tiếp.
"""
from dataclasses import dataclass, field
from typing import Any, Callable

from database import Database
from repositories import (
    CategoryRepository,
    CustomerRepository,
    EmployeeRepository,
    InventoryRepository,
    InvoiceRepository,
    ProductRepository,
    SettingsRepository,
)
from services.customer_service import CustomerService
from services.inventory_service import InventoryService
from services.pos_service import PosService
from services.product_service import ProductService
from services.report_service import ReportService
from services.settings_service import SettingsService


@dataclass
class AppContext:
    db: Database
    settings: SettingsService
    products: ProductService
    customers: CustomerService
    inventory: InventoryService
    pos: PosService
    reports: ReportService
    # Các thành phần giao diện được gắn thêm khi tạo cửa sổ chính (ThemeManager, báo trạng thái, chuyển trang)
    theme: Any = None
    notify: Callable[[str], None] = field(default=lambda message: None)
    navigate: Callable[[str], None] = field(default=lambda page_key: None)

    @classmethod
    def create(cls, db: Database) -> "AppContext":
        category_repo = CategoryRepository(db)
        product_repo = ProductRepository(db)
        customer_repo = CustomerRepository(db)
        employee_repo = EmployeeRepository(db)
        invoice_repo = InvoiceRepository(db)
        inventory_repo = InventoryRepository(db)
        settings_repo = SettingsRepository(db)

        product_service = ProductService(db, product_repo, category_repo, inventory_repo)
        return cls(
            db=db,
            settings=SettingsService(settings_repo, employee_repo),
            products=product_service,
            customers=CustomerService(customer_repo, invoice_repo),
            inventory=InventoryService(db, product_repo, inventory_repo, product_service),
            pos=PosService(db, product_repo, customer_repo, employee_repo, invoice_repo, inventory_repo),
            reports=ReportService(db, invoice_repo, product_repo),
        )
