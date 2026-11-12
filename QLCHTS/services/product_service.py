"""Nghiệp vụ quản lý sản phẩm: kiểm tra dữ liệu, thêm/sửa/xóa, ngừng kinh doanh."""
import sqlite3

import config
from database import Database
from errors import NotFoundError, ProductInUseError, ValidationError
from models.product import Category, Product
from repositories.category_repository import CategoryRepository
from repositories.inventory_repository import InventoryRepository
from repositories.product_repository import ProductRepository
from utils.validators import clean_text, require_code, require_int, require_number, require_text

MAX_PRICE = 100_000_000_000  # 100 tỷ đồng – giới hạn hợp lý cho một sản phẩm


class ProductService:
    def __init__(self, db: Database, product_repo: ProductRepository, category_repo: CategoryRepository,
                 inventory_repo: InventoryRepository):
        self.db = db
        self.products = product_repo
        self.categories = category_repo
        self.inventory = inventory_repo

    # ------------------------------------------------------------- truy vấn
    def search(self, keyword: str = "", category_id: int | None = None, active: bool | None = None,
               in_stock_only: bool = False) -> list[Product]:
        return self.products.search(keyword, category_id, active, in_stock_only)

    def get(self, product_id: int) -> Product:
        product = self.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Sản phẩm không tồn tại hoặc đã bị xóa.")
        return product

    def list_categories(self) -> list[Category]:
        return self.categories.get_all()

    def add_category(self, name: str, description: str = "") -> int:
        name = require_text(name, "tên danh mục", 60)
        if self.categories.get_by_name(name):
            raise ValidationError(f"Danh mục \"{name}\" đã tồn tại.")
        return self.categories.insert(name, clean_text(description))

    def suggest_code(self) -> str:
        return self.products.next_product_code()

    # ------------------------------------------------------------- kiểm tra
    def validate(self, product: Product, initial_stock: int | None = None) -> Product:
        """Chuẩn hóa và kiểm tra dữ liệu sản phẩm; ném ValidationError nếu không hợp lệ."""
        product.product_code = require_code(product.product_code or self.suggest_code(), "mã sản phẩm")
        product.sku = require_code(product.sku, "mã SKU")
        product.product_name = require_text(product.product_name, "tên sản phẩm", 150)
        product.material = require_text(product.material, "chất liệu", 100)
        product.description = (product.description or "").strip()
        product.image_path = (product.image_path or "").strip()

        if not product.category_id or self.categories.get_by_id(product.category_id) is None:
            raise ValidationError("Vui lòng chọn danh mục trang sức hợp lệ.")
        if product.weight_unit not in config.WEIGHT_UNITS:
            raise ValidationError("Đơn vị trọng lượng phải là chỉ, lượng hoặc gram.")
        product.weight = require_number(product.weight, "trọng lượng", minimum=0, maximum=100000,
                                        allow_equal_min=False)
        product.cost_price = int(require_number(product.cost_price, "giá nhập", minimum=0, maximum=MAX_PRICE))
        product.selling_price = int(require_number(product.selling_price, "giá bán", minimum=0,
                                                   maximum=MAX_PRICE, allow_equal_min=False))
        if initial_stock is not None:
            product.stock_quantity = require_int(initial_stock, "số lượng tồn kho", minimum=0, maximum=1_000_000)

        if self.products.code_exists(product.product_code, exclude_id=product.product_id):
            raise ValidationError(f"Mã sản phẩm \"{product.product_code}\" đã tồn tại.")
        if self.products.sku_exists(product.sku, exclude_id=product.product_id):
            raise ValidationError(f"Mã SKU \"{product.sku}\" đã tồn tại. Mỗi sản phẩm phải có SKU riêng.")
        return product

    # ------------------------------------------------------------- ghi dữ liệu
    def create(self, product: Product, initial_stock: int = 0, created_by: str = "") -> int:
        """Thêm sản phẩm và ghi phiếu nhập kho đầu kỳ trong cùng một transaction."""
        product.product_id = None
        self.validate(product, initial_stock)
        try:
            with self.db.transaction() as conn:
                product_id = self.products.insert(product, conn=conn)
                if product.stock_quantity > 0:
                    self.inventory.add(product_id, "IMPORT", product.stock_quantity, product.stock_quantity,
                                       reference_code=product.product_code,
                                       note="Nhập kho khi tạo sản phẩm", created_by=created_by, conn=conn)
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"Không thể lưu sản phẩm do trùng mã SKU hoặc mã sản phẩm ({exc}).") from exc
        return product_id

    def update(self, product: Product) -> None:
        if not product.product_id or self.products.get_by_id(product.product_id) is None:
            raise NotFoundError("Sản phẩm cần sửa không còn tồn tại.")
        self.validate(product)
        try:
            self.products.update(product)
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"Không thể cập nhật do trùng mã SKU hoặc mã sản phẩm ({exc}).") from exc

    def set_active(self, product_id: int, active: bool) -> None:
        self.get(product_id)
        self.products.set_active(product_id, active)

    def delete(self, product_id: int) -> None:
        """Xóa hẳn sản phẩm CHƯA từng bán. Sản phẩm đã bán -> ném ProductInUseError.

        Với sản phẩm đã có trong hóa đơn, giao diện sẽ đề nghị chuyển sang
        "Ngừng kinh doanh" để bảo toàn lịch sử hóa đơn.
        """
        product = self.get(product_id)
        sales = self.products.count_sales(product_id)
        if sales:
            raise ProductInUseError(
                f"Sản phẩm \"{product.product_name}\" đã phát sinh {sales} dòng hóa đơn nên không thể xóa.",
                sales,
            )
        with self.db.transaction() as conn:
            self.inventory.delete_by_product(product_id, conn=conn)
            self.products.delete(product_id, conn=conn)
