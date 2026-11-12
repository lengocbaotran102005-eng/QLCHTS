"""Truy xuất bảng ``employees`` (nhân viên bán hàng)."""
from models.customer import Employee
from repositories.base_repository import BaseRepository
from utils.formatters import now_str


class EmployeeRepository(BaseRepository):
    def get_all(self, active_only: bool = False, conn=None) -> list[Employee]:
        sql = "SELECT * FROM employees"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY is_active DESC, employee_name COLLATE NOCASE"
        with self._read(conn) as c:
            return [Employee.from_row(r) for r in c.execute(sql).fetchall()]

    def get_by_id(self, employee_id: int, conn=None) -> Employee | None:
        with self._read(conn) as c:
            row = c.execute("SELECT * FROM employees WHERE employee_id = ?", (employee_id,)).fetchone()
        return Employee.from_row(row) if row else None

    def insert(self, employee: Employee, conn=None) -> int:
        with self._write(conn) as c:
            code = employee.employee_code or self._next_code(c, "employees", "employee_code", "NV", 3)
            cur = c.execute(
                """
                INSERT INTO employees (employee_code, employee_name, role, phone, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (code, employee.employee_name, employee.role, employee.phone or None,
                 1 if employee.is_active else 0, now_str()),
            )
            return cur.lastrowid

    def update(self, employee: Employee, conn=None) -> None:
        with self._write(conn) as c:
            c.execute(
                "UPDATE employees SET employee_name = ?, role = ?, phone = ?, is_active = ? "
                "WHERE employee_id = ?",
                (employee.employee_name, employee.role, employee.phone or None,
                 1 if employee.is_active else 0, employee.employee_id),
            )
