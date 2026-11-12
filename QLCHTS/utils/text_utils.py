"""Xử lý chuỗi tiếng Việt phục vụ tìm kiếm không phân biệt hoa/thường và có dấu/không dấu."""
import unicodedata


def normalize_search(text) -> str:
    """Chuyển chuỗi về chữ thường, bỏ dấu tiếng Việt và gộp khoảng trắng.

    Ví dụ: "Nhẫn  Vàng 24K" -> "nhan vang 24k".
    Hàm này được đăng ký thành hàm SQL ``search_norm()`` trong SQLite (xem
    ``database.py``) để câu truy vấn tìm kiếm thực hiện ngay trong CSDL.
    """
    if text is None:
        return ""
    text = str(text).replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(without_marks.casefold().split())


def like_pattern(keyword: str) -> str:
    """Tạo mẫu ``%từ khóa%`` cho toán tử LIKE, thoát các ký tự đại diện ``%`` và ``_``.

    Dùng kèm ``ESCAPE '\\'`` trong câu SQL.
    """
    norm = normalize_search(keyword)
    escaped = norm.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def like_patterns(keyword: str) -> list[str]:
    """Tách từ khóa thành từng từ, mỗi từ một mẫu LIKE.

    Ví dụ "nhan vang" -> ['%nhan%', '%vang%'] để tìm được "Nhẫn trơn vàng 24K".
    """
    return [like_pattern(word) for word in normalize_search(keyword).split()]
