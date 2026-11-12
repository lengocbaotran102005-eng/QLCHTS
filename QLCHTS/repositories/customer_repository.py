"""Truy xuất bảng ``customers`` kèm thống kê mua hàng (JOIN với ``invoices``)."""
from models.customer import Customer
from repositories.base_repository import BaseRepository
from utils.formatters import now_str
from utils.text_utils import like_pattern

# Tổng hợp số đơn và tổng tiền chỉ tính các hóa đơn đã thanh toán
CUSTOMER_SELECT = """
    SELECT cu.*,
           COUNT(i.invoice_id)               AS order_count,
           COALESCE(SUM(i.total_amount), 0)  AS total_spent,
           MAX(i.created_at)                 AS last_purchase
    FROM customers cu
    LEFT JOIN invoices i ON i.customer_id = cu.customer_id AND i.status = 'PAID'
"""


class CustomerRepository(BaseRepository):
    def search(self, keyword: str = "", conn=None) -> list[Customer]:
        sql = CUSTOMER_SELECT
        params: list = []
        if keyword and keyword.strip():
            pattern = like_pattern(keyword)
            sql += """
                WHERE search_norm(cu.customer_name) LIKE ? ESCAPE '\\'
                   OR search_norm(cu.phone) LIKE ? ESCAPE '\\'
                   OR search_norm(cu.customer_code) LIKE ? ESCAPE '\\'
                   OR search_norm(cu.address) LIKE ? ESCAPE '\\'
            """
            params += [pattern] * 4
        sql += " GROUP BY cu.customer_id ORDER BY cu.customer_name COLLATE NOCASE"
        with self._read(conn) as c:
            return [Customer.from_row(r) for r in c.execute(sql, params).fetchall()]

    def get_by_id(self, customer_id: int, conn=None) -> Customer | None:
        with self._read(conn) as c:
            row = c.execute(
                CUSTOMER_SELECT + " WHERE cu.customer_id = ? GROUP BY cu.customer_id", (customer_id,)
            ).fetchone()
        return Customer.from_row(row) if row else None

    def phone_exists(self, phone: str, exclude_id: int | None = None, conn=None) -> bool:
        with self._read(conn) as c:
            row = c.execute(
                "SELECT 1 FROM customers WHERE phone = ? AND customer_id IS NOT ?", (phone, exclude_id)
            ).fetchone()
        return row is not None

    def count_invoices(self, customer_id: int, conn=None) -> int:
        with self._read(conn) as c:
            return c.execute(
                "SELECT COUNT(*) FROM invoices WHERE customer_id = ?", (customer_id,)
            ).fetchone()[0]

    def next_customer_code(self, conn=None) -> str:
        with self._read(conn) as c:
            return self._next_code(c, "customers", "customer_code", "KH")

    def insert(self, customer: Customer, conn=None) -> int:
        timestamp = now_str()
        with self._write(conn) as c:
            code = customer.customer_code or self._next_code(c, "customers", "customer_code", "KH")
            cur = c.execute(
                """
                INSERT INTO customers (customer_code, customer_name, phone, email, address, note,
                                       created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (code, customer.customer_name, customer.phone or None, customer.email or None,
                 customer.address or None, customer.note or None,
                 customer.created_at or timestamp, timestamp),
            )
            return cur.lastrowid

    def update(self, customer: Customer, conn=None) -> None:
        with self._write(conn) as c:
            c.execute(
                """
                UPDATE customers
                SET customer_name = ?, phone = ?, email = ?, address = ?, note = ?, updated_at = ?
                WHERE customer_id = ?
                """,
                (customer.customer_name, customer.phone or None, customer.email or None,
                 customer.address or None, customer.note or None, now_str(), customer.customer_id),
            )

    def delete(self, customer_id: int, conn=None) -> None:
        with self._write(conn) as c:
            c.execute("DELETE FROM customers WHERE customer_id = ?", (customer_id,))
