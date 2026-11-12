"""Truy xuất bảng ``products``: tìm kiếm, thêm, sửa, xóa, cập nhật tồn kho."""
from errors import StockError
from models.product import Product
from repositories.base_repository import BaseRepository
from utils.formatters import now_str
from utils.text_utils import like_patterns

PRODUCT_SELECT = """
    SELECT p.*, c.category_name
    FROM products p
    JOIN categories c ON c.category_id = p.category_id
"""


class ProductRepository(BaseRepository):
    # ------------------------------------------------------------------ đọc
    def search(self, keyword: str = "", category_id: int | None = None, active: bool | None = None,
               in_stock_only: bool = False, conn=None) -> list[Product]:
        """Tìm sản phẩm theo tên, SKU, mã SP, chất liệu, danh mục (không dấu, không phân biệt hoa/thường).

        Các điều kiện WHERE là chuỗi cố định; giá trị người dùng nhập luôn truyền qua tham số ``?``.
        """
        sql = PRODUCT_SELECT + " WHERE 1 = 1"
        params: list = []
        # Mỗi từ trong từ khóa phải xuất hiện ở ít nhất một cột (AND giữa các từ, OR giữa các cột)
        for pattern in like_patterns(keyword or ""):
            sql += """
                AND (search_norm(p.product_name) LIKE ? ESCAPE '\\'
                     OR search_norm(p.sku) LIKE ? ESCAPE '\\'
                     OR search_norm(p.product_code) LIKE ? ESCAPE '\\'
                     OR search_norm(p.material) LIKE ? ESCAPE '\\'
                     OR search_norm(c.category_name) LIKE ? ESCAPE '\\')
            """
            params += [pattern] * 5
        if category_id:
            sql += " AND p.category_id = ?"
            params.append(category_id)
        if active is not None:
            sql += " AND p.is_active = ?"
            params.append(1 if active else 0)
        if in_stock_only:
            sql += " AND p.stock_quantity > 0"
        sql += " ORDER BY p.is_active DESC, c.category_name COLLATE NOCASE, p.product_name COLLATE NOCASE"
        with self._read(conn) as c:
            return [Product.from_row(r) for r in c.execute(sql, params).fetchall()]

    def get_by_id(self, product_id: int, conn=None) -> Product | None:
        with self._read(conn) as c:
            row = c.execute(PRODUCT_SELECT + " WHERE p.product_id = ?", (product_id,)).fetchone()
        return Product.from_row(row) if row else None

    def sku_exists(self, sku: str, exclude_id: int | None = None, conn=None) -> bool:
        with self._read(conn) as c:
            row = c.execute(
                "SELECT 1 FROM products WHERE sku = ? COLLATE NOCASE AND product_id IS NOT ?",
                (sku, exclude_id),
            ).fetchone()
        return row is not None

    def code_exists(self, code: str, exclude_id: int | None = None, conn=None) -> bool:
        with self._read(conn) as c:
            row = c.execute(
                "SELECT 1 FROM products WHERE product_code = ? COLLATE NOCASE AND product_id IS NOT ?",
                (code, exclude_id),
            ).fetchone()
        return row is not None

    def next_product_code(self, conn=None) -> str:
        with self._read(conn) as c:
            return self._next_code(c, "products", "product_code", "SP")

    def count_sales(self, product_id: int, conn=None) -> int:
        """Số dòng chi tiết hóa đơn đã bán sản phẩm này (dùng để chặn xóa)."""
        with self._read(conn) as c:
            return c.execute(
                "SELECT COUNT(*) FROM invoice_details WHERE product_id = ?", (product_id,)
            ).fetchone()[0]

    def low_stock(self, threshold: int, conn=None) -> list[Product]:
        sql = PRODUCT_SELECT + """
            WHERE p.is_active = 1 AND p.stock_quantity <= ?
            ORDER BY p.stock_quantity ASC, p.product_name COLLATE NOCASE
        """
        with self._read(conn) as c:
            return [Product.from_row(r) for r in c.execute(sql, (threshold,)).fetchall()]

    def stock_summary(self, threshold: int, conn=None) -> dict:
        sql = """
            SELECT COUNT(*)                                             AS product_count,
                   COALESCE(SUM(is_active), 0)                          AS active_count,
                   COALESCE(SUM(stock_quantity), 0)                     AS total_units,
                   COALESCE(SUM(stock_quantity * cost_price), 0)        AS stock_value_cost,
                   COALESCE(SUM(stock_quantity * selling_price), 0)     AS stock_value_retail,
                   COALESCE(SUM(CASE WHEN is_active = 1 AND stock_quantity = 0 THEN 1 ELSE 0 END), 0)
                                                                        AS out_of_stock,
                   COALESCE(SUM(CASE WHEN is_active = 1 AND stock_quantity > 0 AND stock_quantity <= ?
                                     THEN 1 ELSE 0 END), 0)             AS low_stock
            FROM products
        """
        with self._read(conn) as c:
            return dict(c.execute(sql, (threshold,)).fetchone())

    # ------------------------------------------------------------------ ghi
    def insert(self, product: Product, conn=None) -> int:
        timestamp = now_str()
        sql = """
            INSERT INTO products (product_code, sku, product_name, category_id, material, weight,
                                  weight_unit, cost_price, selling_price, stock_quantity, image_path,
                                  description, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            product.product_code, product.sku, product.product_name, product.category_id,
            product.material, product.weight, product.weight_unit, product.cost_price,
            product.selling_price, product.stock_quantity, product.image_path or None,
            product.description or None, 1 if product.is_active else 0, timestamp, timestamp,
        )
        with self._write(conn) as c:
            return c.execute(sql, params).lastrowid

    def update(self, product: Product, conn=None) -> None:
        """Cập nhật thông tin sản phẩm (không cập nhật tồn kho – tồn kho thay đổi qua phiếu kho)."""
        sql = """
            UPDATE products
            SET product_code = ?, sku = ?, product_name = ?, category_id = ?, material = ?,
                weight = ?, weight_unit = ?, cost_price = ?, selling_price = ?, image_path = ?,
                description = ?, is_active = ?, updated_at = ?
            WHERE product_id = ?
        """
        params = (
            product.product_code, product.sku, product.product_name, product.category_id,
            product.material, product.weight, product.weight_unit, product.cost_price,
            product.selling_price, product.image_path or None, product.description or None,
            1 if product.is_active else 0, now_str(), product.product_id,
        )
        with self._write(conn) as c:
            c.execute(sql, params)

    def set_active(self, product_id: int, active: bool, conn=None) -> None:
        with self._write(conn) as c:
            c.execute(
                "UPDATE products SET is_active = ?, updated_at = ? WHERE product_id = ?",
                (1 if active else 0, now_str(), product_id),
            )

    def delete(self, product_id: int, conn=None) -> None:
        with self._write(conn) as c:
            c.execute("DELETE FROM products WHERE product_id = ?", (product_id,))

    def change_stock(self, product_id: int, delta: int, conn=None) -> int:
        """Cộng/trừ tồn kho một cách nguyên tử và trả về tồn kho mới.

        Điều kiện ``stock_quantity + delta >= 0`` nằm ngay trong câu UPDATE nên không
        bao giờ trừ kho xuống âm, kể cả khi có hai thao tác đồng thời.
        """
        with self._write(conn) as c:
            cur = c.execute(
                """
                UPDATE products
                SET stock_quantity = stock_quantity + ?, updated_at = ?
                WHERE product_id = ? AND stock_quantity + ? >= 0
                """,
                (delta, now_str(), product_id, delta),
            )
            if cur.rowcount != 1:
                row = c.execute(
                    "SELECT product_name, stock_quantity FROM products WHERE product_id = ?", (product_id,)
                ).fetchone()
                if row is None:
                    raise StockError("Sản phẩm không còn tồn tại trong cơ sở dữ liệu.")
                raise StockError(
                    f"Sản phẩm \"{row['product_name']}\" chỉ còn {row['stock_quantity']} trong kho, "
                    f"không đủ để xuất {abs(delta)}."
                )
            return c.execute(
                "SELECT stock_quantity FROM products WHERE product_id = ?", (product_id,)
            ).fetchone()[0]
