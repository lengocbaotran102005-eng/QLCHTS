"""Truy xuất bảng ``settings`` (cặp khóa – giá trị cấu hình hệ thống)."""
from repositories.base_repository import BaseRepository
from utils.formatters import now_str


class SettingsRepository(BaseRepository):
    def get_all(self, conn=None) -> dict[str, str]:
        with self._read(conn) as c:
            rows = c.execute("SELECT setting_key, setting_value FROM settings").fetchall()
        return {r["setting_key"]: r["setting_value"] for r in rows}

    def get(self, key: str, default: str | None = None, conn=None) -> str | None:
        with self._read(conn) as c:
            row = c.execute("SELECT setting_value FROM settings WHERE setting_key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_many(self, values: dict[str, str], conn=None) -> None:
        timestamp = now_str()
        with self._write(conn) as c:
            c.executemany(
                """
                INSERT INTO settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE
                SET setting_value = excluded.setting_value, updated_at = excluded.updated_at
                """,
                [(key, str(value), timestamp) for key, value in values.items()],
            )
