"""Kiểm thử nghiệp vụ cốt lõi trên một tệp SQLite tạm (không ảnh hưởng baotran_jewelry.db).

Chạy trong PyCharm: chuột phải thư mục ``tests`` -> Run 'Python tests in tests',
hoặc trong Terminal: ``python -m unittest discover -s tests -v``.
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from app_context import AppContext  # noqa: E402
from database import Database  # noqa: E402
from errors import BusinessRuleError, ProductInUseError, StockError, ValidationError  # noqa: E402
from models.customer import Customer  # noqa: E402
from models.product import Product  # noqa: E402
from seed_data import seed_sample_data  # noqa: E402
from services.pos_service import Cart, calculate_totals  # noqa: E402
from utils.formatters import money_in_words  # noqa: E402


class BaseCase(unittest.TestCase):
    seed = False

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.db = Database(self.folder / "test.db")
        self.db.initialize()
        if self.seed:
            seed_sample_data(self.db)
        self.ctx = AppContext.create(self.db)
        employees = self.ctx.settings.employees()
        if not employees:
            from models.customer import Employee
            self.ctx.settings.save_employee(Employee(employee_name="Nhân viên test", role="Thu ngân"))
        self.employee_id = self.ctx.settings.employees()[0].employee_id

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def count(self, table: str) -> int:
        with self.db.connection() as conn:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def make_product(self, sku="T-001", price=10_000_000, stock=5, name="Nhẫn vàng thử nghiệm") -> int:
        category_id = self.ctx.products.list_categories()[0].category_id if self.ctx.products.list_categories() \
            else self.ctx.products.add_category("Nhẫn")
        product = Product(product_code="", sku=sku, product_name=name, category_id=category_id,
                          material="Vàng 18K (750)", weight=1.5, weight_unit="chỉ", cost_price=price - 1_000_000,
                          selling_price=price)
        return self.ctx.products.create(product, initial_stock=stock)


class DatabaseTests(BaseCase):
    def test_tables_created_with_foreign_keys(self):
        with self.db.connection() as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        for table in ("categories", "products", "customers", "invoices", "invoice_details",
                      "inventory_transactions", "settings", "employees"):
            self.assertIn(table, tables)

    def test_seed_only_once_and_persists_after_reopen(self):
        self.assertTrue(seed_sample_data(self.db))
        counts = self.db.table_counts()
        self.assertGreaterEqual(counts["products"], 8)
        self.assertFalse(seed_sample_data(self.db))  # lần 2 không thêm trùng
        reopened = Database(self.db.db_path)        # "tắt và mở lại chương trình"
        reopened.initialize()
        self.assertFalse(seed_sample_data(reopened))
        self.assertEqual(reopened.table_counts(), counts)
        self.assertEqual(reopened.integrity_check(), ("ok", 0))

    def test_foreign_key_is_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction() as conn:
                conn.execute("INSERT INTO invoice_details (invoice_id, product_id, product_name, sku, quantity, "
                             "unit_price, line_total) VALUES (9999, 9999, 'x', 'x', 1, 1, 1)")


class ProductTests(BaseCase):
    def test_create_update_and_search(self):
        product_id = self.make_product()
        product = self.ctx.products.get(product_id)
        self.assertEqual(product.stock_quantity, 5)
        self.assertEqual(self.count("inventory_transactions"), 1)  # phiếu nhập kho đầu kỳ
        product.selling_price = 12_000_000
        product.product_name = "Nhẫn vàng đã đổi tên"
        self.ctx.products.update(product)
        self.assertEqual(self.ctx.products.get(product_id).selling_price, 12_000_000)
        # Tìm kiếm không dấu, không phân biệt hoa thường, nhiều từ
        self.assertEqual(len(self.ctx.products.search("NHAN DOI TEN")), 1)
        self.assertEqual(len(self.ctx.products.search("vàng 18k")), 1)
        self.assertEqual(len(self.ctx.products.search("t-001")), 1)

    def test_duplicate_sku_and_invalid_values(self):
        self.make_product(sku="DUP-1")
        with self.assertRaises(ValidationError):
            self.make_product(sku="dup-1")  # SKU không phân biệt hoa thường
        with self.assertRaises(ValidationError):
            self.make_product(sku="NEG-1", price=0)
        with self.assertRaises(ValidationError):
            self.make_product(sku="NEG-2", stock=-1)

    def test_delete_rules(self):
        unsold = self.make_product(sku="DEL-1")
        self.ctx.products.delete(unsold)
        self.assertEqual(self.count("products"), 0)
        sold = self.make_product(sku="DEL-2")
        cart = Cart()
        cart.add(self.ctx.products.get(sold))
        self.ctx.pos.checkout(cart, employee_id=self.employee_id)
        with self.assertRaises(ProductInUseError):
            self.ctx.products.delete(sold)
        self.ctx.products.set_active(sold, False)
        self.assertFalse(self.ctx.products.get(sold).is_active)
        self.assertEqual(len(self.ctx.products.search(active=True)), 0)


class PricingTests(unittest.TestCase):
    def test_percent_discount_and_vat(self):
        s = calculate_totals(32_440_000, config.DISCOUNT_PERCENT, 5, 10)
        self.assertEqual(s.discount_amount, 1_622_000)
        self.assertEqual(s.taxable_amount, 30_818_000)
        self.assertEqual(s.vat_amount, 3_081_800)
        self.assertEqual(s.total, 32_440_000 - 1_622_000 + 3_081_800)

    def test_amount_discount_and_rounding(self):
        s = calculate_totals(1_250_005, config.DISCOUNT_AMOUNT, 5, 8)
        self.assertEqual(s.discount_amount, 5)
        self.assertEqual(s.vat_amount, 100_000)  # 1.250.000 × 8%
        self.assertEqual(s.total, 1_350_000)

    def test_invalid_discount(self):
        with self.assertRaises(ValidationError):
            calculate_totals(1_000_000, config.DISCOUNT_PERCENT, 101, 10)
        with self.assertRaises(ValidationError):
            calculate_totals(1_000_000, config.DISCOUNT_AMOUNT, 1_000_001, 10)
        with self.assertRaises(ValidationError):
            calculate_totals(1_000_000, config.DISCOUNT_AMOUNT, -1, 10)
        with self.assertRaises(ValidationError):
            calculate_totals(1_000_000, config.DISCOUNT_AMOUNT, 0, 120)


class CheckoutTests(BaseCase):
    def test_cart_cannot_exceed_stock(self):
        product = self.ctx.products.get(self.make_product(stock=2))
        cart = Cart()
        cart.add(product, 2)
        with self.assertRaises(StockError):
            cart.add(product, 1)
        self.assertEqual(self.ctx.products.get(product.product_id).stock_quantity, 2)  # giỏ hàng không trừ kho

    def test_checkout_saves_invoice_and_reduces_stock(self):
        p1 = self.make_product(sku="A-1", price=10_000_000, stock=5)
        p2 = self.make_product(sku="A-2", price=2_000_000, stock=3)
        cart = Cart()
        cart.add(self.ctx.products.get(p1), 2)
        cart.add(self.ctx.products.get(p2), 1)
        invoice = self.ctx.pos.checkout(cart, employee_id=self.employee_id, discount_type=config.DISCOUNT_PERCENT,
                                        discount_value=5, vat_rate=10, payment_method=config.PAYMENT_CASH,
                                        amount_received=30_000_000)
        saved, details = self.ctx.pos.get_invoice(invoice.invoice_id)
        self.assertEqual(saved.subtotal, 22_000_000)
        self.assertEqual(saved.discount_amount, 1_100_000)
        self.assertEqual(saved.vat_amount, 2_090_000)
        self.assertEqual(saved.total_amount, 22_990_000)
        self.assertEqual(saved.change_amount, 7_010_000)
        self.assertEqual(len(details), 2)
        self.assertEqual(self.ctx.products.get(p1).stock_quantity, 3)
        self.assertEqual(self.ctx.products.get(p2).stock_quantity, 2)
        sale_rows = self.ctx.inventory.history(transaction_type="SALE")
        self.assertEqual(sorted(t.quantity_change for t in sale_rows), [-2, -1])
        self.assertTrue(saved.invoice_code.startswith(f"HD{date.today():%Y%m%d}-"))

    def test_empty_cart_and_insufficient_cash(self):
        with self.assertRaises(BusinessRuleError):
            self.ctx.pos.checkout(Cart(), employee_id=self.employee_id)
        cart = Cart()
        cart.add(self.ctx.products.get(self.make_product()))
        with self.assertRaises(ValidationError):
            self.ctx.pos.checkout(cart, employee_id=self.employee_id, payment_method=config.PAYMENT_CASH,
                                  amount_received=1000)
        self.assertEqual(self.count("invoices"), 0)

    def test_rollback_when_stock_changed_after_adding_to_cart(self):
        product_id = self.make_product(stock=3)
        cart = Cart()
        cart.add(self.ctx.products.get(product_id), 3)
        self.ctx.inventory.adjust_stock(product_id, 1, "Kiểm kê thực tế")  # tồn kho giảm sau khi thêm vào giỏ
        with self.assertRaises(StockError):
            self.ctx.pos.checkout(cart, employee_id=self.employee_id)
        self.assertEqual(self.count("invoices"), 0)
        self.assertEqual(self.ctx.products.get(product_id).stock_quantity, 1)

    def test_rollback_on_error_in_middle_of_transaction(self):
        product_id = self.make_product(stock=4)
        cart = Cart()
        cart.add(self.ctx.products.get(product_id), 2)
        original_add = self.ctx.pos.inventory.add

        def broken_add(*args, **kwargs):
            raise sqlite3.OperationalError("Lỗi giả lập khi ghi lịch sử kho")

        self.ctx.pos.inventory.add = broken_add
        try:
            with self.assertRaises(sqlite3.OperationalError):
                self.ctx.pos.checkout(cart, employee_id=self.employee_id)
        finally:
            self.ctx.pos.inventory.add = original_add
        # Không có hóa đơn "nửa vời" và tồn kho không bị trừ
        self.assertEqual(self.count("invoices"), 0)
        self.assertEqual(self.count("invoice_details"), 0)
        self.assertEqual(self.ctx.products.get(product_id).stock_quantity, 4)

    def test_old_invoice_keeps_snapshot_after_product_changes(self):
        product_id = self.make_product(price=10_000_000)
        cart = Cart()
        cart.add(self.ctx.products.get(product_id))
        invoice = self.ctx.pos.checkout(cart, employee_id=self.employee_id)
        product = self.ctx.products.get(product_id)
        product.product_name = "Tên mới"
        product.selling_price = 99_000_000
        self.ctx.products.update(product)
        _saved, details = self.ctx.pos.get_invoice(invoice.invoice_id)
        self.assertEqual(details[0].product_name, "Nhẫn vàng thử nghiệm")
        self.assertEqual(details[0].unit_price, 10_000_000)

    def test_cancel_invoice_restores_stock_and_excludes_revenue(self):
        product_id = self.make_product(stock=5, price=1_000_000)
        cart = Cart()
        cart.add(self.ctx.products.get(product_id), 2)
        invoice = self.ctx.pos.checkout(cart, employee_id=self.employee_id, vat_rate=0)
        kpi = self.ctx.reports.dashboard_kpis(3)
        self.assertEqual((kpi["revenue"], kpi["orders"]), (2_000_000, 1))
        self.ctx.pos.cancel_invoice(invoice.invoice_id, "Khách đổi ý")
        self.assertEqual(self.ctx.products.get(product_id).stock_quantity, 5)
        kpi = self.ctx.reports.dashboard_kpis(3)
        self.assertEqual((kpi["revenue"], kpi["orders"], kpi["cancelled_orders"]), (0, 0, 1))
        with self.assertRaises(BusinessRuleError):
            self.ctx.pos.cancel_invoice(invoice.invoice_id, "Hủy lần 2")


class CustomerAndInventoryTests(BaseCase):
    def test_customer_validation(self):
        customer_id = self.ctx.customers.save(Customer(customer_name="Nguyễn Văn A", phone="0901 234 567"))
        self.assertEqual(self.ctx.customers.get(customer_id).phone, "0901234567")
        with self.assertRaises(ValidationError):
            self.ctx.customers.save(Customer(customer_name="Trùng SĐT", phone="0901234567"))
        with self.assertRaises(ValidationError):
            self.ctx.customers.save(Customer(customer_name="Sai SĐT", phone="12345"))
        with self.assertRaises(ValidationError):
            self.ctx.customers.save(Customer(customer_name="", phone="0912345678"))

    def test_import_and_adjust_stock_are_logged(self):
        product_id = self.make_product(stock=2)
        self.assertEqual(self.ctx.inventory.import_stock(product_id, 3, "PN-01"), 5)
        with self.assertRaises(ValidationError):
            self.ctx.inventory.adjust_stock(product_id, 4, "")  # bắt buộc nhập lý do
        self.assertEqual(self.ctx.inventory.adjust_stock(product_id, 4, "Hàng lỗi"), 4)
        history = self.ctx.inventory.history(product_id)
        self.assertEqual([t.transaction_type for t in history], ["ADJUST", "IMPORT", "IMPORT"])
        self.assertEqual(history[0].quantity_change, -1)
        self.assertEqual(history[0].stock_after, 4)


class ReportTests(BaseCase):
    seed = True

    def test_reports_are_consistent(self):
        end = date.today()
        start = end - timedelta(days=120)
        summary = self.ctx.reports.summary(start, end)
        by_day = self.ctx.reports.revenue_by_day(start, end)
        by_month = self.ctx.reports.revenue_by_month(start, end)
        self.assertEqual(sum(r["revenue"] for r in by_day), summary["revenue"])
        self.assertEqual(sum(r["revenue"] for r in by_month), summary["revenue"])
        self.assertEqual(sum(r["invoice_count"] for r in by_day), summary["invoice_count"])
        with self.db.connection() as conn:
            paid = conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM invoices WHERE status = 'PAID'").fetchone()[0]
        self.assertEqual(self.ctx.reports.dashboard_kpis(3)["revenue"], paid)
        self.assertTrue(self.ctx.reports.best_sellers(start, end))
        self.assertEqual(summary["cancelled_count"], 1)

    def test_reports_without_transactions(self):
        future = date.today() + timedelta(days=400)
        self.assertEqual(self.ctx.reports.summary(future, future)["revenue"], 0)
        self.assertEqual(self.ctx.reports.best_sellers(future, future), [])


class FormatterTests(unittest.TestCase):
    def test_money_in_words(self):
        self.assertEqual(money_in_words(0), "Không đồng")
        self.assertEqual(money_in_words(105), "Một trăm linh năm đồng")
        self.assertEqual(money_in_words(21), "Hai mươi mốt đồng")
        self.assertEqual(money_in_words(12_500_000), "Mười hai triệu năm trăm nghìn đồng")
        self.assertEqual(money_in_words(1_005_000), "Một triệu không trăm linh năm nghìn đồng")


class PdfExportTest(BaseCase):
    seed = True

    def test_export_pdf(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from printing.invoice_printer import InvoicePrinter
        _app = QApplication.instance() or QApplication([])
        invoice = self.ctx.pos.search_invoices(limit=1)[0]
        saved, details = self.ctx.pos.get_invoice(invoice.invoice_id)
        path = InvoicePrinter(saved, details, self.ctx.settings.all()).export_pdf(self.folder / "hoa_don.pdf")
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 1000)
        self.assertEqual(path.read_bytes()[:4], b"%PDF")


if __name__ == "__main__":
    unittest.main(verbosity=2)
