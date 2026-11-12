"""Truy xuất bảng ``inventory_transactions`` (lịch sử nhập/xuất/điều chỉnh kho)."""
from models.inventory import InventoryTransaction
from repositories.base_repository import BaseRepository
from utils.formatters import now_str


class InventoryRepository(BaseRepository):
    def add(self, product_id: int, transaction_type: str, quantity_change: int, stock_after: int,
            reference_code: str = "", note: str = "", created_by: str = "", created_at: str | None = None,
            conn=None) -> int:
        with self._write(conn) as c:
            cur = c.execute(
                """
                INSERT INTO inventory_transactions (product_id, transaction_type, quantity_change,
                                                    stock_after, reference_code, note, created_by,
                                                    created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (product_id, transaction_type, quantity_change, stock_after, reference_code or None,
                 note or None, created_by or None, created_at or now_str()),
            )
            return cur.lastrowid

    def history(self, product_id: int | None = None, transaction_type: str | None = None,
                date_from: str | None = None, date_to: str | None = None, limit: int = 500,
                conn=None) -> list[InventoryTransaction]:
        sql = """
            SELECT t.*, p.sku, p.product_name
            FROM inventory_transactions t
            JOIN products p ON p.product_id = t.product_id
            WHERE 1 = 1
        """
        params: list = []
        if product_id:
            sql += " AND t.product_id = ?"
            params.append(product_id)
        if transaction_type:
            sql += " AND t.transaction_type = ?"
            params.append(transaction_type)
        if date_from:
            sql += " AND date(t.created_at) >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND date(t.created_at) <= ?"
            params.append(date_to)
        sql += " ORDER BY t.created_at DESC, t.transaction_id DESC LIMIT ?"
        params.append(limit)
        with self._read(conn) as c:
            return [InventoryTransaction.from_row(r) for r in c.execute(sql, params).fetchall()]

    def delete_by_product(self, product_id: int, conn=None) -> None:
        """Chỉ dùng khi xóa hẳn một sản phẩm chưa từng bán (xem ProductService.delete)."""
        with self._write(conn) as c:
            c.execute("DELETE FROM inventory_transactions WHERE product_id = ?", (product_id,))
