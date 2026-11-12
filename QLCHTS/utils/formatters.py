"""Định dạng hiển thị: tiền VNĐ, số thập phân, trọng lượng, ngày giờ và đọc số tiền bằng chữ."""
from datetime import date, datetime

import config

DB_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


# ---------------------------------------------------------------------------
# Số và tiền tệ
# ---------------------------------------------------------------------------
def format_number(value) -> str:
    """12500000 -> '12.500.000' (dấu chấm phân cách hàng nghìn theo kiểu Việt Nam)."""
    try:
        number = int(round(float(value or 0)))
    except (TypeError, ValueError):
        number = 0
    text = f"{abs(number):,}".replace(",", ".")
    return f"-{text}" if number < 0 else text


def format_money(value) -> str:
    """12500000 -> '12.500.000 ₫'."""
    return f"{format_number(value)} ₫"


def format_decimal(value, max_decimals: int = 3) -> str:
    """1.2 -> '1,2'; 15.0 -> '15' (dấu phẩy thập phân, bỏ số 0 thừa)."""
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0.0
    text = f"{number:.{max_decimals}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if text not in ("", "-0") else "0"


def format_percent(value) -> str:
    return f"{format_decimal(value, 2)}%"


# ---------------------------------------------------------------------------
# Trọng lượng
# ---------------------------------------------------------------------------
def to_grams(weight, unit: str) -> float:
    """Quy đổi trọng lượng về gram (1 chỉ = 3,75 g; 1 lượng = 37,5 g)."""
    return float(weight or 0) * config.GRAMS_PER_UNIT.get(unit, 1.0)


def format_weight(weight, unit: str, with_grams: bool = False) -> str:
    """'1,2 chỉ' hoặc '1,2 chỉ (4,5 g)' khi with_grams=True."""
    if weight is None:
        return "—"
    text = f"{format_decimal(weight)} {unit or ''}".strip()
    if with_grams and unit and unit != "gram":
        text += f" ({format_decimal(to_grams(weight, unit), 2)} g)"
    return text


# ---------------------------------------------------------------------------
# Ngày giờ
# ---------------------------------------------------------------------------
def now_str() -> str:
    """Thời điểm hiện tại (giờ máy tính) theo định dạng lưu trong CSDL."""
    return datetime.now().strftime(DB_DATETIME_FORMAT)


def parse_db_datetime(text) -> datetime | None:
    if not text:
        return None
    for fmt in (DB_DATETIME_FORMAT, "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(text), fmt)
        except ValueError:
            continue
    return None


def format_datetime(text) -> str:
    """'2026-10-21 14:35:00' -> '21/10/2026 14:35'."""
    value = parse_db_datetime(text)
    return value.strftime("%d/%m/%Y %H:%M") if value else (text or "")


def format_date(value) -> str:
    """Nhận chuỗi CSDL hoặc đối tượng date, trả về 'dd/mm/yyyy'."""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    parsed = parse_db_datetime(value)
    return parsed.strftime("%d/%m/%Y") if parsed else (value or "")


# ---------------------------------------------------------------------------
# Đọc số tiền bằng chữ (dùng trên hóa đơn)
# ---------------------------------------------------------------------------
_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _read_three_digits(number: int, full: bool) -> list[str]:
    """Đọc nhóm 3 chữ số. full=True khi nhóm không đứng đầu (phải đọc cả 'không trăm')."""
    hundreds, rest = divmod(number, 100)
    tens, units = divmod(rest, 10)
    words: list[str] = []
    if full or hundreds:
        words += [_DIGITS[hundreds], "trăm"]
    if tens == 0:
        if units:
            if full or hundreds:
                words.append("linh")
            words.append(_DIGITS[units])
    elif tens == 1:
        words.append("mười")
        if units == 5:
            words.append("lăm")
        elif units:
            words.append(_DIGITS[units])
    else:
        words += [_DIGITS[tens], "mươi"]
        if units == 1:
            words.append("mốt")
        elif units == 4:
            words.append("tư")
        elif units == 5:
            words.append("lăm")
        elif units:
            words.append(_DIGITS[units])
    return words


def _read_below_billion(number: int, full: bool) -> list[str]:
    groups = [(number // 1_000_000, "triệu"), (number // 1000 % 1000, "nghìn"), (number % 1000, "")]
    words: list[str] = []
    started = full
    for value, unit in groups:
        if value == 0:
            continue
        words += _read_three_digits(value, full=started)
        if unit:
            words.append(unit)
        started = True
    return words


def number_to_words_vi(number) -> str:
    """Đọc số nguyên thành chữ tiếng Việt. Ví dụ 12500000 -> 'mười hai triệu năm trăm nghìn'."""
    number = int(number)
    if number == 0:
        return "không"
    if number < 0:
        return "âm " + number_to_words_vi(-number)
    billions, rest = divmod(number, 1_000_000_000)
    words: list[str] = []
    if billions:
        words += [number_to_words_vi(billions), "tỷ"]
    if rest:
        words += _read_below_billion(rest, full=bool(billions))
    return " ".join(words)


def money_in_words(amount) -> str:
    """12500000 -> 'Mười hai triệu năm trăm nghìn đồng'."""
    text = number_to_words_vi(int(round(float(amount or 0))))
    return text[:1].upper() + text[1:] + " đồng"
