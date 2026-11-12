"""Lớp cơ sở cho các repository.

Mỗi phương thức nhận tham số ``conn`` tùy chọn:
* ``conn=None``: repository tự mở kết nối (đọc) hoặc transaction riêng (ghi).
* ``conn`` được truyền vào: tham gia transaction đang mở của tầng service
  (ví dụ: thanh toán = tạo hóa đơn + chi tiết + trừ kho trong cùng một transaction).
"""
from contextlib import contextmanager

from database import Database


class BaseRepository:
    def __init__(self, db: Database):
        self.db = db

    @contextmanager
    def _read(self, conn=None):
        if conn is not None:
            yield conn
        else:
            with self.db.connection() as new_conn:
                yield new_conn

    @contextmanager
    def _write(self, conn=None):
        if conn is not None:
            yield conn
        else:
            with self.db.transaction() as new_conn:
                yield new_conn

    @staticmethod
    def _next_code(conn, table: str, column: str, prefix: str, width: int = 4) -> str:
        """Sinh mã kế tiếp dạng PREFIX0001 dựa trên mã lớn nhất hiện có.

        ``table``/``column`` là hằng số do lập trình viên truyền vào (không phải dữ liệu người dùng).
        """
        rows = conn.execute(
            f"SELECT {column} FROM {table} WHERE {column} LIKE ?", (f"{prefix}%",)
        ).fetchall()
        numbers = [int(r[0][len(prefix):]) for r in rows if r[0][len(prefix):].isdigit()]
        return f"{prefix}{(max(numbers) + 1 if numbers else 1):0{width}d}"
