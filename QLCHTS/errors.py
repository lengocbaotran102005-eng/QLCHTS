"""Các lớp ngoại lệ nghiệp vụ.

Mỗi ngoại lệ mang theo thông báo tiếng Việt để giao diện hiển thị trực tiếp cho
người dùng thay vì để chương trình bị dừng đột ngột.
"""


class AppError(Exception):
    """Lỗi nghiệp vụ có thông báo thân thiện cho người dùng."""

    title = "Thông báo"

    def __init__(self, message: str, *, title: str | None = None):
        super().__init__(message)
        self.message = message
        if title:
            self.title = title


class ValidationError(AppError):
    """Dữ liệu nhập vào không hợp lệ (thiếu trường bắt buộc, sai định dạng...)."""

    title = "Dữ liệu không hợp lệ"


class BusinessRuleError(AppError):
    """Thao tác vi phạm quy tắc nghiệp vụ."""

    title = "Không thể thực hiện"


class StockError(BusinessRuleError):
    """Số lượng vượt quá tồn kho."""

    title = "Không đủ tồn kho"


class PriceChangedError(BusinessRuleError):
    """Giá bán trong CSDL đã thay đổi so với giá trong giỏ hàng."""

    title = "Giá sản phẩm đã thay đổi"


class NotFoundError(AppError):
    """Không tìm thấy bản ghi trong CSDL."""

    title = "Không tìm thấy dữ liệu"


class ProductInUseError(BusinessRuleError):
    """Sản phẩm đã phát sinh giao dịch nên không được xóa."""

    def __init__(self, message: str, sales_count: int):
        super().__init__(message)
        self.sales_count = sales_count


class ImageError(AppError):
    """Lỗi khi đọc, tải hoặc lưu hình ảnh."""

    title = "Lỗi hình ảnh"


class PrintError(AppError):
    """Lỗi khi in hoặc xuất PDF."""

    title = "Lỗi in / xuất PDF"
