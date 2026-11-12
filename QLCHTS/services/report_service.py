"""Nghiệp vụ thống kê – báo cáo, tổng hợp bằng SQL (SELECT, SUM, COUNT, GROUP BY, JOIN).

Quy tắc doanh thu (xem ``config.REVENUE_RULE``): chỉ tính các hóa đơn có
``status = 'PAID'``; hóa đơn đã hủy (``CANCELLED``) bị loại khỏi doanh thu và số đơn.
"""
from datetime import date, timedelta

import config
from database import Database
from models.invoice import Invoice
from models.product import Product
from repositories.invoice_repository import InvoiceRepository
from repositories.product_repository import ProductRepository

PAID = config.INVOICE_PAID


def _iso(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


class ReportService:
    def __init__(self, db: Database, invoice_repo: InvoiceRepository, product_repo: ProductRepository):
        self.db = db
        self.invoices = invoice_repo
        self.products = product_repo

    # ------------------------------------------------------------- Dashboard
    def dashboard_kpis(self, low_stock_threshold: int) -> dict:
        today = date.today()
        month_start = today.replace(day=1)
        with self.db.connection() as conn:
            revenue = conn.execute(
                "SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue "
                "FROM invoices WHERE status = ?", (PAID,)
            ).fetchone()
            today_row = conn.execute(
                "SELECT COUNT(*) AS orders, COALESCE(SUM(total_amount), 0) AS revenue "
                "FROM invoices WHERE status = ? AND date(created_at) = ?", (PAID, today.isoformat())
            ).fetchone()
            customers = conn.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(CASE WHEN date(created_at) >= ? THEN 1 ELSE 0 END), 0) AS new_this_month "
                "FROM customers", (month_start.isoformat(),)
            ).fetchone()
            cancelled = conn.execute(
                "SELECT COUNT(*) FROM invoices WHERE status = ?", (config.INVOICE_CANCELLED,)
            ).fetchone()[0]
        stock = self.products.stock_summary(low_stock_threshold)
        return {
            "revenue": revenue["revenue"],
            "orders": revenue["orders"],
            "today_revenue": today_row["revenue"],
            "today_orders": today_row["orders"],
            "cancelled_orders": cancelled,
            "product_count": stock["product_count"],
            "active_products": stock["active_count"],
            "total_units": stock["total_units"],
            "low_stock": stock["low_stock"],
            "out_of_stock": stock["out_of_stock"],
            "customer_count": customers["total"],
            "new_customers": customers["new_this_month"],
        }

    def recent_invoices(self, limit: int = 10) -> list[Invoice]:
        return self.invoices.recent(limit)

    # ------------------------------------------------------------- Doanh thu
    def revenue_by_day(self, start: date, end: date) -> list[dict]:
        """Doanh thu từng ngày trong khoảng [start, end]; ngày không có giao dịch = 0."""
        sql = """
            SELECT date(created_at)               AS period,
                   COUNT(*)                       AS invoice_count,
                   COALESCE(SUM(subtotal), 0)        AS subtotal,
                   COALESCE(SUM(discount_amount), 0) AS discount,
                   COALESCE(SUM(vat_amount), 0)      AS vat,
                   COALESCE(SUM(total_amount), 0)    AS revenue
            FROM invoices
            WHERE status = ? AND date(created_at) BETWEEN ? AND ?
            GROUP BY date(created_at)
            ORDER BY period
        """
        with self.db.connection() as conn:
            rows = {r["period"]: dict(r) for r in conn.execute(sql, (PAID, _iso(start), _iso(end)))}
        result = []
        day = start
        while day <= end:
            key = day.isoformat()
            result.append(rows.get(key, {"period": key, "invoice_count": 0, "subtotal": 0,
                                          "discount": 0, "vat": 0, "revenue": 0}))
            day += timedelta(days=1)
        return result

    def revenue_by_month(self, start: date, end: date) -> list[dict]:
        """Doanh thu từng tháng (yyyy-mm) trong khoảng ngày; tháng không có giao dịch = 0."""
        sql = """
            SELECT strftime('%Y-%m', created_at)  AS period,
                   COUNT(*)                       AS invoice_count,
                   COALESCE(SUM(subtotal), 0)        AS subtotal,
                   COALESCE(SUM(discount_amount), 0) AS discount,
                   COALESCE(SUM(vat_amount), 0)      AS vat,
                   COALESCE(SUM(total_amount), 0)    AS revenue
            FROM invoices
            WHERE status = ? AND date(created_at) BETWEEN ? AND ?
            GROUP BY strftime('%Y-%m', created_at)
            ORDER BY period
        """
        with self.db.connection() as conn:
            rows = {r["period"]: dict(r) for r in conn.execute(sql, (PAID, _iso(start), _iso(end)))}
        result = []
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            key = f"{year:04d}-{month:02d}"
            result.append(rows.get(key, {"period": key, "invoice_count": 0, "subtotal": 0,
                                          "discount": 0, "vat": 0, "revenue": 0}))
            month += 1
            if month > 12:
                year, month = year + 1, 1
        return result

    def summary(self, start: date, end: date) -> dict:
        """Tổng hợp doanh thu, số giao dịch, giá vốn và lợi nhuận gộp ước tính trong khoảng ngày."""
        with self.db.connection() as conn:
            paid = conn.execute(
                """
                SELECT COUNT(*)                          AS invoice_count,
                       COALESCE(SUM(subtotal), 0)        AS subtotal,
                       COALESCE(SUM(discount_amount), 0) AS discount,
                       COALESCE(SUM(vat_amount), 0)      AS vat,
                       COALESCE(SUM(total_amount), 0)    AS revenue
                FROM invoices
                WHERE status = ? AND date(created_at) BETWEEN ? AND ?
                """, (PAID, _iso(start), _iso(end))
            ).fetchone()
            items = conn.execute(
                """
                SELECT COALESCE(SUM(d.quantity), 0)                AS items_sold,
                       COALESCE(SUM(d.quantity * d.unit_cost), 0)  AS cost
                FROM invoice_details d
                JOIN invoices i ON i.invoice_id = d.invoice_id
                WHERE i.status = ? AND date(i.created_at) BETWEEN ? AND ?
                """, (PAID, _iso(start), _iso(end))
            ).fetchone()
            cancelled = conn.execute(
                """
                SELECT COUNT(*) AS cancelled_count, COALESCE(SUM(total_amount), 0) AS cancelled_amount
                FROM invoices WHERE status = ? AND date(created_at) BETWEEN ? AND ?
                """, (config.INVOICE_CANCELLED, _iso(start), _iso(end))
            ).fetchone()
        net_sales = paid["subtotal"] - paid["discount"]  # doanh thu chưa gồm VAT
        count = paid["invoice_count"]
        return {
            "invoice_count": count,
            "subtotal": paid["subtotal"],
            "discount": paid["discount"],
            "vat": paid["vat"],
            "revenue": paid["revenue"],
            "net_sales": net_sales,
            "average_order": round(paid["revenue"] / count) if count else 0,
            "items_sold": items["items_sold"],
            "cost": items["cost"],
            "gross_profit": net_sales - items["cost"],
            "cancelled_count": cancelled["cancelled_count"],
            "cancelled_amount": cancelled["cancelled_amount"],
        }

    # ------------------------------------------------------------- Sản phẩm
    def best_sellers(self, start: date, end: date, limit: int = 10) -> list[dict]:
        """Sản phẩm bán chạy theo số lượng (chỉ hóa đơn đã thanh toán)."""
        sql = """
            SELECT d.product_id,
                   COALESCE(p.sku, MAX(d.sku))                    AS sku,
                   COALESCE(p.product_name, MAX(d.product_name))  AS product_name,
                   COALESCE(c.category_name, MAX(d.category_name)) AS category_name,
                   SUM(d.quantity)                                AS quantity,
                   SUM(d.line_total)                              AS sales,
                   COUNT(DISTINCT d.invoice_id)                   AS invoice_count,
                   COALESCE(p.stock_quantity, 0)                  AS stock_quantity
            FROM invoice_details d
            JOIN invoices i ON i.invoice_id = d.invoice_id
            LEFT JOIN products p ON p.product_id = d.product_id
            LEFT JOIN categories c ON c.category_id = p.category_id
            WHERE i.status = ? AND date(i.created_at) BETWEEN ? AND ?
            GROUP BY d.product_id
            ORDER BY quantity DESC, sales DESC
            LIMIT ?
        """
        with self.db.connection() as conn:
            return [dict(r) for r in conn.execute(sql, (PAID, _iso(start), _iso(end), limit))]

    def revenue_by_category(self, start: date, end: date) -> list[dict]:
        sql = """
            SELECT COALESCE(d.category_name, 'Khác') AS category_name,
                   SUM(d.quantity)                   AS quantity,
                   SUM(d.line_total)                 AS sales
            FROM invoice_details d
            JOIN invoices i ON i.invoice_id = d.invoice_id
            WHERE i.status = ? AND date(i.created_at) BETWEEN ? AND ?
            GROUP BY COALESCE(d.category_name, 'Khác')
            ORDER BY sales DESC
        """
        with self.db.connection() as conn:
            return [dict(r) for r in conn.execute(sql, (PAID, _iso(start), _iso(end)))]

    def low_stock(self, threshold: int) -> list[Product]:
        return self.products.low_stock(threshold)
