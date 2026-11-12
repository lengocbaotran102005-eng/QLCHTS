"""Hàm dùng chung để tạo đối tượng dataclass từ một dòng kết quả sqlite3.Row."""
from dataclasses import fields


def row_to_kwargs(cls, row) -> dict:
    """Lấy các cột trong ``row`` trùng tên với thuộc tính của dataclass ``cls``."""
    keys = set(row.keys())
    return {f.name: row[f.name] for f in fields(cls) if f.name in keys}
