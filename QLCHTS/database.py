"""Kết nối SQLite, khởi tạo lược đồ CSDL (schema) và quản lý transaction.

Nguyên tắc sử dụng:
* Mỗi thao tác mở một kết nối mới và đóng ngay sau khi xong (``connection()``),
  bảo đảm giải phóng tài nguyên.
* Mọi thao tác ghi liên quan đến nhiều bảng đi qua ``transaction()``: nếu có lỗi
  ở bất kỳ bước nào, toàn bộ thay đổi được ROLLBACK.
* Mỗi kết nối đều bật ``PRAGMA foreign_keys = ON`` để kiểm tra khóa ngoại.
"""
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import config
from utils.formatters import now_str
from utils.text_utils import normalize_search

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Lược đồ CSDL. Toàn bộ được chạy trong một transaction khi khởi tạo.
SCHEMA_SQL = """
BEGIN;

CREATE TABLE IF NOT EXISTS categories (
    category_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description   TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    sku            TEXT NOT NULL UNIQUE COLLATE NOCASE,
    product_name   TEXT NOT NULL,
    category_id    INTEGER NOT NULL
                   REFERENCES categories(category_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    material       TEXT NOT NULL,
    weight         REAL NOT NULL CHECK (weight > 0),
    weight_unit    TEXT NOT NULL CHECK (weight_unit IN ('chỉ', 'lượng', 'gram')),
    cost_price     INTEGER NOT NULL CHECK (cost_price >= 0),
    selling_price  INTEGER NOT NULL CHECK (selling_price > 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    image_path     TEXT,
    description    TEXT,
    is_active      INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_code TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    phone         TEXT UNIQUE,
    email         TEXT,
    address       TEXT,
    note          TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_code TEXT NOT NULL UNIQUE,
    employee_name TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'Nhân viên bán hàng',
    phone         TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    invoice_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_code     TEXT NOT NULL UNIQUE,
    customer_id      INTEGER REFERENCES customers(customer_id) ON DELETE RESTRICT,
    customer_name    TEXT NOT NULL,
    customer_phone   TEXT,
    customer_address TEXT,
    employee_id      INTEGER REFERENCES employees(employee_id) ON DELETE RESTRICT,
    employee_name    TEXT,
    created_at       TEXT NOT NULL,
    subtotal         INTEGER NOT NULL CHECK (subtotal >= 0),
    discount_type    TEXT NOT NULL DEFAULT 'amount' CHECK (discount_type IN ('percent', 'amount')),
    discount_value   REAL NOT NULL DEFAULT 0 CHECK (discount_value >= 0),
    discount_amount  INTEGER NOT NULL DEFAULT 0
                     CHECK (discount_amount >= 0 AND discount_amount <= subtotal),
    vat_rate         REAL NOT NULL DEFAULT 0 CHECK (vat_rate >= 0 AND vat_rate <= 100),
    vat_amount       INTEGER NOT NULL DEFAULT 0 CHECK (vat_amount >= 0),
    total_amount     INTEGER NOT NULL CHECK (total_amount >= 0),
    amount_received  INTEGER NOT NULL DEFAULT 0 CHECK (amount_received >= 0),
    change_amount    INTEGER NOT NULL DEFAULT 0 CHECK (change_amount >= 0),
    payment_method   TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'PAID' CHECK (status IN ('PAID', 'CANCELLED')),
    note             TEXT,
    cancelled_at     TEXT,
    cancel_reason    TEXT,
    CHECK (total_amount = subtotal - discount_amount + vat_amount)
);

CREATE TABLE IF NOT EXISTS invoice_details (
    detail_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id    INTEGER NOT NULL REFERENCES invoices(invoice_id) ON DELETE CASCADE,
    product_id    INTEGER NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    product_name  TEXT NOT NULL,
    sku           TEXT NOT NULL,
    category_name TEXT,
    material      TEXT,
    weight        REAL,
    weight_unit   TEXT,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    INTEGER NOT NULL CHECK (unit_price >= 0),
    unit_cost     INTEGER NOT NULL DEFAULT 0 CHECK (unit_cost >= 0),
    line_total    INTEGER NOT NULL CHECK (line_total = quantity * unit_price)
);

CREATE TABLE IF NOT EXISTS inventory_transactions (
    transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id       INTEGER NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('IMPORT', 'SALE', 'ADJUST', 'CANCEL')),
    quantity_change  INTEGER NOT NULL CHECK (quantity_change <> 0),
    stock_after      INTEGER NOT NULL CHECK (stock_after >= 0),
    reference_code   TEXT,
    note             TEXT,
    created_by       TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    setting_key   TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_category   ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at);
CREATE INDEX IF NOT EXISTS idx_invoices_customer   ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status     ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_details_invoice     ON invoice_details(invoice_id);
CREATE INDEX IF NOT EXISTS idx_details_product     ON invoice_details(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_product   ON inventory_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_created   ON inventory_transactions(created_at);

COMMIT;
"""

# Danh sách bảng (hằng số trong mã nguồn, không lấy từ dữ liệu người dùng nhập)
TABLE_NAMES = (
    "categories",
    "products",
    "customers",
    "employees",
    "invoices",
    "invoice_details",
    "inventory_transactions",
    "settings",
)


class Database:
    """Đối tượng quản lý tệp CSDL SQLite ``baotran_jewelry.db``."""

    def __init__(self, db_path: Path | str = config.DB_PATH):
        self.db_path = Path(db_path)

    # ------------------------------------------------------------------ kết nối
    def connect(self) -> sqlite3.Connection:
        """Mở kết nối mới tới tệp SQLite (người gọi chịu trách nhiệm đóng)."""
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # Hàm SQL tự định nghĩa: tìm kiếm không dấu, không phân biệt hoa/thường
        conn.create_function("search_norm", 1, normalize_search, deterministic=True)
        return conn

    @contextmanager
    def connection(self):
        """Kết nối dùng cho thao tác đọc; tự động đóng khi ra khỏi khối ``with``."""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """Transaction ghi dữ liệu: COMMIT khi thành công, ROLLBACK khi có lỗi.

        Dùng ``BEGIN IMMEDIATE`` để khóa ghi ngay từ đầu, tránh xung đột khi hai
        thao tác cùng ghi (ví dụ cùng trừ tồn kho).
        """
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
                log.warning("Đã ROLLBACK transaction do xảy ra lỗi.")
            raise
        finally:
            conn.close()

    # ---------------------------------------------------------------- khởi tạo
    def initialize(self) -> bool:
        """Tạo tệp CSDL, các bảng và cài đặt mặc định nếu chưa có.

        Trả về True nếu tệp CSDL vừa được tạo mới.
        """
        is_new = not self.db_path.exists()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._insert_default_settings()
        log.info("CSDL sẵn sàng: %s%s", self.db_path, " (tạo mới)" if is_new else "")
        return is_new

    def _insert_default_settings(self) -> None:
        timestamp = now_str()
        with self.transaction() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                [(key, value, timestamp) for key, value in config.DEFAULT_SETTINGS.items()],
            )

    # ------------------------------------------------------------- tiện ích
    def table_counts(self) -> dict[str, int]:
        """Đếm số bản ghi của từng bảng (dùng để kiểm tra CSDL trong màn hình Cài đặt)."""
        counts = {}
        with self.connection() as conn:
            for table in TABLE_NAMES:
                # Tên bảng lấy từ hằng số TABLE_NAMES nên an toàn khi ghép vào câu lệnh
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return counts

    def integrity_check(self) -> tuple[str, int]:
        """Chạy PRAGMA integrity_check và foreign_key_check; trả về (kết quả, số lỗi khóa ngoại)."""
        with self.connection() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            fk_errors = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        return result, fk_errors

    def backup_to(self, destination: Path | str) -> None:
        """Sao lưu toàn bộ CSDL sang tệp khác bằng Backup API của SQLite."""
        destination = Path(destination)
        if destination.resolve() == self.db_path.resolve():
            raise ValueError("Tệp sao lưu phải khác tệp CSDL đang sử dụng.")
        with self.connection() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
