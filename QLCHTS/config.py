"""Cấu hình chung của ứng dụng: đường dẫn thư mục, hằng số nghiệp vụ và giá trị mặc định."""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Đường dẫn (luôn tính theo vị trí tệp này nên chạy từ thư mục nào cũng đúng)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

# Có thể đổi vị trí CSDL bằng biến môi trường BAOTRAN_DB_PATH (dùng khi kiểm thử)
DB_PATH = Path(os.environ.get("BAOTRAN_DB_PATH", BASE_DIR / "baotran_jewelry.db"))

ASSETS_DIR = BASE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
THEME_ICONS_DIR = ICONS_DIR / "theme"
IMAGES_DIR = ASSETS_DIR / "images"
SAMPLE_IMAGES_DIR = IMAGES_DIR / "samples"
PRODUCT_IMAGES_DIR = IMAGES_DIR / "products"
IMAGE_CACHE_DIR = IMAGES_DIR / "cache"
DEFAULT_IMAGE = IMAGES_DIR / "no_image.png"
LOGO_IMAGE = IMAGES_DIR / "logo.png"

# ---------------------------------------------------------------------------
# Thông tin ứng dụng
# ---------------------------------------------------------------------------
APP_NAME = "Bảo Trân Jewelry"
APP_TITLE = "BẢO TRÂN JEWELRY – Phần mềm quản lý cửa hàng trang sức"
APP_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Hằng số nghiệp vụ
# ---------------------------------------------------------------------------
# Đơn vị trọng lượng: 1 lượng (cây) = 10 chỉ = 37,5 gram; 1 chỉ = 3,75 gram
WEIGHT_UNITS = ("chỉ", "lượng", "gram")
GRAMS_PER_UNIT = {"chỉ": 3.75, "lượng": 37.5, "gram": 1.0}

PAYMENT_CASH = "Tiền mặt"
PAYMENT_METHODS = (PAYMENT_CASH, "Chuyển khoản", "Thẻ ngân hàng", "Ví điện tử")

DISCOUNT_PERCENT = "percent"
DISCOUNT_AMOUNT = "amount"

INVOICE_PAID = "PAID"
INVOICE_CANCELLED = "CANCELLED"
INVOICE_STATUS_LABELS = {INVOICE_PAID: "Đã thanh toán", INVOICE_CANCELLED: "Đã hủy"}

WALK_IN_CUSTOMER = "Khách lẻ"

INVENTORY_TYPE_LABELS = {
    "IMPORT": "Nhập kho",
    "SALE": "Xuất bán",
    "ADJUST": "Điều chỉnh",
    "CANCEL": "Hoàn kho (hủy HĐ)",
}

# Quy tắc tính doanh thu dùng thống nhất cho Dashboard và Báo cáo
REVENUE_RULE = (
    "Doanh thu thực thu = tổng \"Tổng thanh toán\" (sau chiết khấu, đã gồm VAT) của các hóa đơn "
    "có trạng thái \"Đã thanh toán\". Hóa đơn đã hủy không được tính vào doanh thu và số đơn hàng."
)

INVOICE_LEGAL_NOTE = (
    "Hóa đơn bán hàng nội bộ của cửa hàng (phục vụ quản lý, mô phỏng trong đồ án) – "
    "không thay thế hóa đơn điện tử/hóa đơn GTGT theo quy định pháp luật."
)

# Giá trị cài đặt mặc định – được ghi vào bảng `settings` khi khởi tạo CSDL lần đầu.
# Người quản lý có thể thay đổi trong màn hình "Cài đặt hệ thống".
DEFAULT_SETTINGS = {
    "store_name": "BẢO TRÂN JEWELRY",
    "store_full_name": "Cửa Hàng Trang Sức & Vàng Bạc Đá Quý Bảo Trân",
    "store_address": "Số 88 Đường Trần Hưng Đạo, Phường 1, Quận 5, TP. Hồ Chí Minh",
    "store_phone": "0901 234 567",
    "store_email": "",
    "store_tax_code": "",
    "vat_rate": "10",
    "low_stock_threshold": "3",
    "warranty_info": (
        "Bảo hành đánh bóng, làm mới miễn phí trọn đời sản phẩm. Bảo hành gắn lại đá tấm miễn phí "
        "trong 12 tháng (không áp dụng cho đá chủ, kim cương). Vui lòng mang theo hóa đơn khi bảo hành."
    ),
    "buyback_policy": (
        "Thu mua lại trang sức vàng theo giá niêm yết của cửa hàng tại thời điểm thu mua, trừ tiền công "
        "chế tác theo quy định. Đổi sản phẩm trong vòng 48 giờ nếu còn nguyên tem, chưa qua sử dụng."
    ),
    "thank_you_message": "Cảm ơn Quý khách đã tin tưởng lựa chọn Bảo Trân Jewelry!",
    "theme": "dark",
}
