"""Nghiệp vụ kho hàng: nhập kho, điều chỉnh tồn kho (kiểm kê) và tra cứu lịch sử kho.

Mọi thay đổi số lượng đều được ghi vào bảng ``inventory_transactions`` cùng lý do
và thời điểm, trong cùng transaction với việc cập nhật ``products.stock_quantity``.
"""
from database import Database
from errors import ValidationError
from models.inventory import InventoryTransaction
from models.product import Product
from repositories.inventory_repository import InventoryRepository
from repositories.product_repository import ProductRepository
from services.product_service import ProductService
from utils.validators import require_int, require_text


class InventoryService:
    def __init__(self, db: Database, product_repo: ProductRepository, inventory_repo: InventoryRepository,
                 product_service: ProductService):
        self.db = db
        self.products = product_repo
        self.inventory = inventory_repo
        self.product_service = product_service

    def import_stock(self, product_id: int, quantity, reference_code: str = "", note: str = "",
                     created_by: str = "") -> int:
        """Nhập thêm hàng vào kho. Trả về tồn kho mới."""
        product = self.product_service.get(product_id)
        quantity = require_int(quantity, "số lượng nhập", minimum=1, maximum=1_000_000)
        with self.db.transaction() as conn:
            new_stock = self.products.change_stock(product.product_id, quantity, conn=conn)
            self.inventory.add(product.product_id, "IMPORT", quantity, new_stock,
                               reference_code=reference_code.strip(),
                               note=note.strip() or "Nhập hàng vào kho", created_by=created_by, conn=conn)
        return new_stock

    def adjust_stock(self, product_id: int, actual_quantity, reason: str, created_by: str = "") -> int:
        """Điều chỉnh tồn kho về số lượng thực tế (kiểm kê). Bắt buộc nhập lý do."""
        product = self.product_service.get(product_id)
        actual_quantity = require_int(actual_quantity, "số lượng thực tế", minimum=0, maximum=1_000_000)
        reason = require_text(reason, "lý do điều chỉnh", 255)
        delta = actual_quantity - product.stock_quantity
        if delta == 0:
            raise ValidationError("Số lượng thực tế bằng tồn kho hiện tại, không cần điều chỉnh.")
        with self.db.transaction() as conn:
            new_stock = self.products.change_stock(product.product_id, delta, conn=conn)
            self.inventory.add(product.product_id, "ADJUST", delta, new_stock, note=reason,
                               created_by=created_by, conn=conn)
        return new_stock

    def history(self, product_id: int | None = None, transaction_type: str | None = None,
                date_from: str | None = None, date_to: str | None = None,
                limit: int = 500) -> list[InventoryTransaction]:
        return self.inventory.history(product_id, transaction_type, date_from, date_to, limit)

    def stock_list(self, keyword: str = "", level: str = "all", threshold: int = 3) -> list[Product]:
        """Danh sách tồn kho; level: 'all' | 'low' (sắp hết) | 'out' (hết hàng)."""
        products = self.products.search(keyword)
        if level == "low":
            products = [p for p in products if p.is_active and 0 < p.stock_quantity <= threshold]
        elif level == "out":
            products = [p for p in products if p.is_active and p.stock_quantity == 0]
        return products

    def summary(self, threshold: int) -> dict:
        return self.products.stock_summary(threshold)
