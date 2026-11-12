"""Các hàm kiểm tra dữ liệu nhập vào (dùng ở tầng nghiệp vụ)."""
import re

from errors import ValidationError

PHONE_PATTERN = re.compile(r"^0\d{9}$")
EMAIL_PATTERN = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
CODE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{2,30}$")


def clean_text(value) -> str:
    return " ".join(str(value or "").split())


def clean_phone(value) -> str:
    """Bỏ khoảng trắng, dấu chấm, gạch nối: '0901 234.567' -> '0901234567'."""
    return re.sub(r"[\s.\-()]", "", str(value or ""))


def is_valid_phone(phone: str) -> bool:
    return bool(PHONE_PATTERN.match(phone or ""))


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match(email or ""))


def require_text(value, field_label: str, max_length: int = 255) -> str:
    text = clean_text(value)
    if not text:
        raise ValidationError(f"Vui lòng nhập {field_label}.")
    if len(text) > max_length:
        raise ValidationError(f"{field_label.capitalize()} không được dài quá {max_length} ký tự.")
    return text


def require_code(value, field_label: str) -> str:
    code = str(value or "").strip().upper()
    if not code:
        raise ValidationError(f"Vui lòng nhập {field_label}.")
    if not CODE_PATTERN.match(code):
        raise ValidationError(
            f"{field_label.capitalize()} chỉ gồm chữ không dấu, chữ số, dấu chấm, gạch ngang/gạch dưới "
            "và dài từ 2 đến 30 ký tự."
        )
    return code


def require_number(value, field_label: str, *, minimum=None, maximum=None, allow_equal_min=True) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_label.capitalize()} phải là một số hợp lệ.") from None
    if minimum is not None:
        if allow_equal_min and number < minimum:
            raise ValidationError(f"{field_label.capitalize()} không được nhỏ hơn {minimum:g}.")
        if not allow_equal_min and number <= minimum:
            raise ValidationError(f"{field_label.capitalize()} phải lớn hơn {minimum:g}.")
    if maximum is not None and number > maximum:
        raise ValidationError(f"{field_label.capitalize()} không được lớn hơn {maximum:,.0f}.".replace(",", "."))
    return number


def require_int(value, field_label: str, *, minimum=None, maximum=None) -> int:
    number = require_number(value, field_label, minimum=minimum, maximum=maximum)
    if int(number) != number:
        raise ValidationError(f"{field_label.capitalize()} phải là số nguyên.")
    return int(number)
