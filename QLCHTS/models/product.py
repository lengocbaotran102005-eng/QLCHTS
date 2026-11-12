"""Model danh mục và sản phẩm trang sức."""
from dataclasses import dataclass

from models.base import row_to_kwargs
from utils.formatters import format_weight, to_grams


@dataclass
class Category:
    category_id: int | None = None
    category_name: str = ""
    description: str = ""
    product_count: int = 0

    @classmethod
    def from_row(cls, row) -> "Category":
        return cls(**row_to_kwargs(cls, row))


@dataclass
class Product:
    product_id: int | None = None
    product_code: str = ""
    sku: str = ""
    product_name: str = ""
    category_id: int | None = None
    category_name: str = ""
    material: str = ""
    weight: float = 0.0
    weight_unit: str = "chỉ"
    cost_price: int = 0
    selling_price: int = 0
    stock_quantity: int = 0
    image_path: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""
    sold_quantity: int = 0

    @classmethod
    def from_row(cls, row) -> "Product":
        product = cls(**row_to_kwargs(cls, row))
        product.is_active = bool(product.is_active)
        product.image_path = product.image_path or ""
        product.description = product.description or ""
        return product

    @property
    def weight_text(self) -> str:
        return format_weight(self.weight, self.weight_unit)

    @property
    def weight_in_grams(self) -> float:
        return to_grams(self.weight, self.weight_unit)

    @property
    def status_label(self) -> str:
        return "Đang kinh doanh" if self.is_active else "Ngừng kinh doanh"

    def stock_level(self, low_threshold: int) -> str:
        """'out' (hết hàng), 'low' (sắp hết) hoặc 'ok' (còn hàng)."""
        if self.stock_quantity <= 0:
            return "out"
        if self.stock_quantity <= low_threshold:
            return "low"
        return "ok"
