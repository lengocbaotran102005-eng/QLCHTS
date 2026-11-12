"""Nghiệp vụ cấu hình hệ thống và quản lý nhân viên."""
import config
from errors import ValidationError
from models.customer import Employee
from repositories.employee_repository import EmployeeRepository
from repositories.settings_repository import SettingsRepository
from utils.validators import clean_phone, is_valid_email, is_valid_phone, require_number, require_text


class SettingsService:
    def __init__(self, settings_repo: SettingsRepository, employee_repo: EmployeeRepository):
        self.repo = settings_repo
        self.employee_repo = employee_repo

    # ------------------------------------------------------------- cài đặt
    def all(self) -> dict[str, str]:
        """Toàn bộ cài đặt, giá trị thiếu được bổ sung từ DEFAULT_SETTINGS."""
        values = dict(config.DEFAULT_SETTINGS)
        values.update(self.repo.get_all())
        return values

    def get(self, key: str) -> str:
        return self.repo.get(key, config.DEFAULT_SETTINGS.get(key, "")) or ""

    @property
    def vat_rate(self) -> float:
        try:
            return float(self.get("vat_rate"))
        except ValueError:
            return float(config.DEFAULT_SETTINGS["vat_rate"])

    @property
    def low_stock_threshold(self) -> int:
        try:
            return int(float(self.get("low_stock_threshold")))
        except ValueError:
            return int(config.DEFAULT_SETTINGS["low_stock_threshold"])

    @property
    def theme(self) -> str:
        return "light" if self.get("theme") == "light" else "dark"

    def set_theme(self, mode: str) -> None:
        self.repo.set_many({"theme": "light" if mode == "light" else "dark"})

    def save(self, values: dict[str, str]) -> None:
        """Kiểm tra và lưu các cài đặt cửa hàng / hóa đơn."""
        cleaned = {key: str(value).strip() for key, value in values.items()}
        if "store_name" in cleaned:
            require_text(cleaned["store_name"], "tên cửa hàng", 100)
        if "vat_rate" in cleaned:
            rate = require_number(cleaned["vat_rate"], "thuế suất VAT", minimum=0, maximum=100)
            cleaned["vat_rate"] = f"{rate:g}"
        if "low_stock_threshold" in cleaned:
            threshold = require_number(cleaned["low_stock_threshold"], "ngưỡng tồn kho thấp",
                                       minimum=0, maximum=100000)
            cleaned["low_stock_threshold"] = str(int(threshold))
        if cleaned.get("store_email") and not is_valid_email(cleaned["store_email"]):
            raise ValidationError("Email cửa hàng không đúng định dạng.")
        self.repo.set_many(cleaned)

    # ------------------------------------------------------------- nhân viên
    def employees(self, active_only: bool = False) -> list[Employee]:
        return self.employee_repo.get_all(active_only=active_only)

    def save_employee(self, employee: Employee) -> int:
        employee.employee_name = require_text(employee.employee_name, "họ tên nhân viên", 100)
        employee.role = require_text(employee.role, "chức vụ", 60)
        employee.phone = clean_phone(employee.phone)
        if employee.phone and not is_valid_phone(employee.phone):
            raise ValidationError("Số điện thoại nhân viên phải gồm 10 chữ số và bắt đầu bằng 0.")
        if employee.employee_id:
            self.employee_repo.update(employee)
            return employee.employee_id
        return self.employee_repo.insert(employee)
