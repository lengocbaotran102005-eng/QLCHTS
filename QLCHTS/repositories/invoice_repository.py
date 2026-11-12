"""Truy xuất bảng ``invoices`` và ``invoice_details``."""
import config
from models.invoice import Invoice, InvoiceDetail
from models.product import Product
from repositories.base_repository import BaseRepository
from utils.text_utils import like_pattern

INVOICE_SELECT = """
    SELECT i.*, cu.customer_code,
           (SELECT COALESCE(SUM(d.quantity), 0) FROM invoice_details d
             WHERE d.invoice_id = i.invoice_id) AS item_count
    FROM invoices i
    LEFT JOIN customers cu ON cu.customer_id = i.customer_id
"""


class InvoiceRepository(BaseRepository):
    # ------------------------------------------------------------------ đọc
    def get_by_id(self, invoice_id: int, conn=None) -> Invoice | None:
        with self._read(conn) as c:
            row = c.execute(INVOICE_SELECT + " WHERE i.invoice_id = ?", (invoice_id,)).fetchone()
        return Invoice.from_row(row) if row else None

    def get_by_code(self, invoice_code: str, conn=None) -> Invoice | None:
        with self._read(conn) as c:
            row = c.execute(INVOICE_SELECT + " WHERE i.invoice_code = ?", (invoice_code,)).fetchone()
        return Invoice.from_row(row) if row else None

    def get_details(self, invoice_id: int, conn=None) -> list[InvoiceDetail]:
        with self._read(conn) as c:
            rows = c.execute(
                "SELECT * FROM invoice_details WHERE invoice_id = ? ORDER BY detail_id", (invoice_id,)
            ).fetchall()
        return [InvoiceDetail.from_row(r) for r in rows]

    def search(self, keyword: str = "", date_from: str | None = None, date_to: str | None = None,
               status: str | None = None, customer_id: int | None = None, limit: int = 1000,
               conn=None) -> list[Invoice]:
        """Tra cứu hóa đơn theo mã HĐ, tên/SĐT khách hàng, khoảng ngày và trạng thái."""
        sql = INVOICE_SELECT + " WHERE 1 = 1"
        params: list = []
        if keyword and keyword.strip():
            pattern = like_pattern(keyword)
            sql += """
                AND (search_norm(i.invoice_code) LIKE ? ESCAPE '\\'
                     OR search_norm(i.customer_name) LIKE ? ESCAPE '\\'
                     OR search_norm(i.customer_phone) LIKE ? ESCAPE '\\'
                     OR search_norm(i.employee_name) LIKE ? ESCAPE '\\')
            """
            params += [pattern] * 4
        if date_from:
            sql += " AND date(i.created_at) >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND date(i.created_at) <= ?"
            params.append(date_to)
        if status:
            sql += " AND i.status = ?"
            params.append(status)
        if customer_id:
            sql += " AND i.customer_id = ?"
            params.append(customer_id)
        sql += " ORDER BY i.created_at DESC, i.invoice_id DESC LIMIT ?"
        params.append(limit)
        with self._read(conn) as c:
            return [Invoice.from_row(r) for r in c.execute(sql, params).fetchall()]

    def recent(self, limit: int = 10, conn=None) -> list[Invoice]:
        return self.search(limit=limit, conn=conn)

    def next_invoice_code(self, day_key: str, conn=None) -> str:
        """Sinh mã hóa đơn duy nhất theo ngày: HD + yyyymmdd + '-' + số thứ tự 4 chữ số.

        ``day_key`` dạng 'yyyymmdd'. Nên gọi bên trong transaction (BEGIN IMMEDIATE) để
        không trùng mã; cột ``invoice_code`` còn có ràng buộc UNIQUE để bảo vệ thêm.
        """
        prefix = f"HD{day_key}-"
        with self._read(conn) as c:
            return self._next_code(c, "invoices", "invoice_code", prefix)

    # ------------------------------------------------------------------ ghi
    def insert_invoice(self, invoice: Invoice, conn) -> int:
        cur = conn.execute(
            """
            INSERT INTO invoices (invoice_code, customer_id, customer_name, customer_phone,
                                  customer_address, employee_id, employee_name, created_at, subtotal,
                                  discount_type, discount_value, discount_amount, vat_rate, vat_amount,
                                  total_amount, amount_received, change_amount, payment_method, status,
                                  note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (invoice.invoice_code, invoice.customer_id, invoice.customer_name,
             invoice.customer_phone or None, invoice.customer_address or None, invoice.employee_id,
             invoice.employee_name or None, invoice.created_at, invoice.subtotal, invoice.discount_type,
             invoice.discount_value, invoice.discount_amount, invoice.vat_rate, invoice.vat_amount,
             invoice.total_amount, invoice.amount_received, invoice.change_amount,
             invoice.payment_method, invoice.status, invoice.note or None),
        )
        return cur.lastrowid

    def insert_detail(self, invoice_id: int, product: Product, quantity: int, conn) -> int:
        """Ghi một dòng chi tiết, lưu snapshot thông tin sản phẩm tại thời điểm bán."""
        cur = conn.execute(
            """
            INSERT INTO invoice_details (invoice_id, product_id, product_name, sku, category_name,
                                         material, weight, weight_unit, quantity, unit_price,
                                         unit_cost, line_total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (invoice_id, product.product_id, product.product_name, product.sku, product.category_name,
             product.material, product.weight, product.weight_unit, quantity, product.selling_price,
             product.cost_price, quantity * product.selling_price),
        )
        return cur.lastrowid

    def mark_cancelled(self, invoice_id: int, reason: str, cancelled_at: str, conn) -> None:
        conn.execute(
            "UPDATE invoices SET status = ?, cancelled_at = ?, cancel_reason = ? WHERE invoice_id = ?",
            (config.INVOICE_CANCELLED, cancelled_at, reason, invoice_id),
        )
