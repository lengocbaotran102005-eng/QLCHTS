"""Truy xuất bảng ``categories`` (danh mục trang sức)."""
from models.product import Category
from repositories.base_repository import BaseRepository


class CategoryRepository(BaseRepository):
    def get_all(self, conn=None) -> list[Category]:
        sql = """
            SELECT c.category_id, c.category_name, c.description,
                   COUNT(p.product_id) AS product_count
            FROM categories c
            LEFT JOIN products p ON p.category_id = c.category_id
            GROUP BY c.category_id
            ORDER BY c.category_name COLLATE NOCASE
        """
        with self._read(conn) as c:
            return [Category.from_row(r) for r in c.execute(sql).fetchall()]

    def get_by_id(self, category_id: int, conn=None) -> Category | None:
        with self._read(conn) as c:
            row = c.execute("SELECT * FROM categories WHERE category_id = ?", (category_id,)).fetchone()
        return Category.from_row(row) if row else None

    def get_by_name(self, name: str, conn=None) -> Category | None:
        with self._read(conn) as c:
            row = c.execute(
                "SELECT * FROM categories WHERE category_name = ? COLLATE NOCASE", (name,)
            ).fetchone()
        return Category.from_row(row) if row else None

    def insert(self, name: str, description: str = "", conn=None) -> int:
        with self._write(conn) as c:
            cur = c.execute(
                "INSERT INTO categories (category_name, description) VALUES (?, ?)", (name, description)
            )
            return cur.lastrowid
