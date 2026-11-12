"""Tạo dữ liệu mẫu cho lần chạy đầu tiên.

Cơ chế chống trùng lặp:
* Chỉ chạy khi bảng ``settings`` CHƯA có khóa ``sample_data_seeded`` VÀ bảng
  ``products`` đang trống.
* Toàn bộ dữ liệu mẫu được ghi trong MỘT transaction: nếu lỗi giữa chừng thì
  ROLLBACK, lần chạy sau sẽ tạo lại từ đầu, không bao giờ bị nhân đôi.
Các hóa đơn mẫu được tạo bằng chính hàm ``PosService.checkout`` nên tồn kho,
chi tiết hóa đơn và lịch sử kho luôn nhất quán.
"""
import logging
import random
from datetime import date, datetime, timedelta

import config
from database import Database
from errors import AppError
from models.customer import Customer, Employee
from models.product import Product
from repositories import (
    CategoryRepository,
    CustomerRepository,
    EmployeeRepository,
    InventoryRepository,
    InvoiceRepository,
    ProductRepository,
    SettingsRepository,
)
from services.pos_service import Cart, PosService
from utils.formatters import DB_DATETIME_FORMAT

log = logging.getLogger(__name__)

SEED_FLAG = "sample_data_seeded"
SAMPLE_DIR = "assets/images/samples"

CATEGORIES = [
    ("Nhẫn", "Nhẫn vàng, nhẫn cưới, nhẫn thời trang"),
    ("Dây chuyền", "Dây chuyền vàng, bạc các loại"),
    ("Lắc tay", "Lắc tay vàng, bạc"),
    ("Bông tai", "Bông tai, hoa tai"),
    ("Vòng tay", "Vòng tay, kiềng"),
    ("Mặt dây chuyền", "Mặt dây chuyền vàng, đá quý"),
    ("Trang sức kim cương", "Trang sức gắn kim cương tự nhiên"),
    ("Vàng tích trữ", "Nhẫn tròn trơn, vàng tích trữ 9999"),
]

# (mã SP, SKU, tên, danh mục, chất liệu, trọng lượng, đơn vị, giá nhập, giá bán, tồn kho, ảnh, mô tả, đang KD)
PRODUCTS = [
    ("SP0001", "BT-N24K-001", "Nhẫn trơn vàng 24K", "Nhẫn", "Vàng 24K (9999)", 1, "chỉ",
     11_850_000, 12_350_000, 14, "ring_24k.png", "Nhẫn trơn ép vỉ, vàng 9999, phù hợp làm quà tặng.", True),
    ("SP0002", "BT-N18K-002", "Nhẫn nữ vàng 18K đính đá CZ", "Nhẫn", "Vàng 18K (750)", 1.2, "chỉ",
     8_200_000, 9_650_000, 10, "ring_18k_cz.png", "Thiết kế ổ chấu tinh tế, đá CZ trắng sáng.", True),
    ("SP0003", "BT-DC18-003", "Dây chuyền vàng 18K mắt xích Ý", "Dây chuyền", "Vàng 18K (750)", 3, "chỉ",
     21_600_000, 24_900_000, 7, "necklace_18k.png", "Dây mắt xích kiểu Ý, dài 45 cm.", True),
    ("SP0004", "BT-LT24-004", "Lắc tay vàng 24K hoa mai", "Lắc tay", "Vàng 24K (9999)", 2, "chỉ",
     23_700_000, 25_200_000, 6, "bracelet_24k.png", "Lắc tay họa tiết hoa mai truyền thống.", True),
    ("SP0005", "BT-BT18-005", "Bông tai vàng 18K ngọc trai", "Bông tai", "Vàng 18K & ngọc trai", 0.8, "chỉ",
     5_400_000, 6_750_000, 12, "earrings_pearl.png", "Ngọc trai nước ngọt 8 ly, khóa bấm an toàn.", True),
    ("SP0006", "BT-VT14-006", "Vòng tay vàng 14K kiểu Ý", "Vòng tay", "Vàng 14K (585)", 15.5, "gram",
     19_800_000, 23_500_000, 5, "bangle_14k.png", "Vòng tay bản tròn, đánh bóng gương.", True),
    ("SP0007", "BT-KC18-007", "Nhẫn kim cương 5.4 ly vàng trắng 18K", "Trang sức kim cương",
     "Vàng trắng 18K & kim cương", 2.8, "gram", 38_500_000, 45_900_000, 4, "ring_diamond.png",
     "Kim cương tự nhiên 5.4 ly, nước D, độ sạch VS1, kèm giấy kiểm định.", True),
    ("SP0008", "BT-MDR-008", "Mặt dây chuyền đá Ruby vàng 18K", "Mặt dây chuyền", "Vàng 18K & Ruby", 1.6,
     "gram", 7_900_000, 9_800_000, 7, "pendant_ruby.png", "Ruby thiên nhiên hình giọt nước.", True),
    ("SP0009", "BT-MDS-009", "Mặt dây chuyền Sapphire vàng trắng 14K", "Mặt dây chuyền",
     "Vàng trắng 14K & Sapphire", 1.9, "gram", 9_200_000, 11_600_000, 5, "pendant_sapphire.png",
     "Sapphire xanh hoàng gia, viền đá tấm.", True),
    ("SP0010", "BT-LTB-010", "Lắc tay bạc Ý 925", "Lắc tay", "Bạc 925", 8.2, "gram",
     780_000, 1_250_000, 22, "bracelet_silver.png", "Bạc Ý 925 xi rhodium chống xỉn.", True),
    ("SP0011", "BT-NTR-011", "Nhẫn tròn trơn vàng 9999 – 1 lượng", "Vàng tích trữ", "Vàng 24K (9999)", 1,
     "lượng", 118_500_000, 122_000_000, 4, "ring_1luong.png", "Nhẫn tròn trơn tích trữ, trọng lượng 1 lượng.",
     True),
    ("SP0012", "BT-NC18-012", "Cặp nhẫn cưới vàng 18K khắc tên", "Nhẫn", "Vàng 18K (750)", 2.5, "chỉ",
     17_500_000, 21_800_000, 4, "wedding_rings.png", "Cặp nhẫn cưới, miễn phí khắc tên.", True),
    ("SP0013", "BT-BKC-013", "Bông tai kim cương vàng trắng 18K", "Trang sức kim cương",
     "Vàng trắng 18K & kim cương", 1.4, "gram", 16_800_000, 19_900_000, 5, "earrings_diamond.png",
     "Cặp bông tai kim cương 3.6 ly, kiểu nụ.", True),
    ("SP0014", "BT-DCB-014", "Dây chuyền bạc 925 mặt trái tim", "Dây chuyền", "Bạc 925 & đá CZ", 4.5, "gram",
     420_000, 790_000, 16, "necklace_silver.png", "Dây chuyền bạc kèm mặt trái tim đính đá.", True),
    ("SP0015", "BT-N10K-015", "Nhẫn vàng 10K kiểu cũ", "Nhẫn", "Vàng 10K (416)", 1, "chỉ",
     3_900_000, 4_600_000, 2, "", "Mẫu cũ – đã ngừng kinh doanh (minh họa trạng thái).", False),
]

CUSTOMERS = [
    ("Nguyễn Thị Thu Hà", "0903123456", "thuha.nguyen@gmail.com", "12 Nguyễn Trãi, Quận 1, TP. Hồ Chí Minh"),
    ("Trần Minh Khoa", "0918234567", "", "45 Lý Thường Kiệt, Quận 10, TP. Hồ Chí Minh"),
    ("Lê Ngọc Bảo Anh", "0937345678", "baoanh.le@gmail.com", "88 Cách Mạng Tháng 8, Quận 3, TP. Hồ Chí Minh"),
    ("Phạm Quốc Huy", "0989456789", "", "21 Phan Đăng Lưu, Quận Bình Thạnh, TP. Hồ Chí Minh"),
    ("Võ Thị Mỹ Linh", "0902567890", "mylinh.vo@gmail.com", "7 Hùng Vương, TP. Thủ Dầu Một, Bình Dương"),
    ("Đặng Gia Hân", "0976678901", "", "156 Trần Phú, TP. Nha Trang, Khánh Hòa"),
    ("Huỳnh Tấn Phát", "0965789012", "", "34 Võ Văn Tần, Quận 3, TP. Hồ Chí Minh"),
]

EMPLOYEES = [
    ("Trần Bảo Ngọc", "Quản lý cửa hàng", "0908111222"),
    ("Lý Thanh Tâm", "Nhân viên bán hàng", "0908333444"),
    ("Hồ Ngọc Diễm", "Thu ngân", "0908555666"),
]


def seed_sample_data(db: Database, days: int = 60, invoice_count: int = 34, rng_seed: int = 2026) -> bool:
    """Thêm dữ liệu mẫu nếu CSDL chưa có dữ liệu. Trả về True nếu đã thêm."""
    settings_repo = SettingsRepository(db)
    if settings_repo.get(SEED_FLAG) == "1":
        return False
    product_repo = ProductRepository(db)
    with db.connection() as conn:
        has_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0
    if has_products:
        # CSDL đã có dữ liệu do người dùng nhập -> không thêm mẫu, chỉ đánh dấu
        settings_repo.set_many({SEED_FLAG: "1"})
        return False

    category_repo = CategoryRepository(db)
    customer_repo = CustomerRepository(db)
    employee_repo = EmployeeRepository(db)
    invoice_repo = InvoiceRepository(db)
    inventory_repo = InventoryRepository(db)
    pos = PosService(db, product_repo, customer_repo, employee_repo, invoice_repo, inventory_repo)
    rng = random.Random(rng_seed)
    today = date.today()
    opening_time = datetime.combine(today - timedelta(days=days + 5), datetime.min.time()).replace(hour=8)
    opening_str = opening_time.strftime(DB_DATETIME_FORMAT)

    with db.transaction() as conn:
        # 1. Danh mục
        category_ids = {}
        for name, description in CATEGORIES:
            existing = category_repo.get_by_name(name, conn=conn)
            category_ids[name] = existing.category_id if existing else category_repo.insert(name, description, conn=conn)

        # 2. Sản phẩm + phiếu nhập kho đầu kỳ
        product_ids = []
        for (code, sku, name, category, material, weight, unit, cost, price, stock, image, description,
             active) in PRODUCTS:
            product = Product(
                product_code=code, sku=sku, product_name=name, category_id=category_ids[category],
                material=material, weight=weight, weight_unit=unit, cost_price=cost, selling_price=price,
                stock_quantity=stock, image_path=f"{SAMPLE_DIR}/{image}" if image else "",
                description=description, is_active=active,
            )
            product_id = product_repo.insert(product, conn=conn)
            inventory_repo.add(product_id, "IMPORT", stock, stock, reference_code="PN-DAUKY",
                               note="Tồn kho đầu kỳ (dữ liệu mẫu)", created_by="Hệ thống",
                               created_at=opening_str, conn=conn)
            if active:
                product_ids.append(product_id)

        # 3. Khách hàng (2 khách tạo trong tháng hiện tại để minh họa "khách mới")
        customers_created: list[tuple[int, date]] = []
        for index, (name, phone, email, address) in enumerate(CUSTOMERS):
            created = today - timedelta(days=(days + 10 - index * 9) if index < 5 else index - 5)
            customer_id = customer_repo.insert(
                Customer(customer_name=name, phone=phone, email=email, address=address,
                         created_at=created.strftime("%Y-%m-%d") + " 08:00:00"), conn=conn)
            customers_created.append((customer_id, created))

        # 4. Nhân viên
        employee_ids = [employee_repo.insert(Employee(employee_name=n, role=r, phone=p), conn=conn)
                        for n, r, p in EMPLOYEES]

        # 5. Hóa đơn mẫu trải đều trong `days` ngày gần đây (có 2 hóa đơn trong hôm nay)
        timestamps = []
        for _ in range(invoice_count - 2):
            day = today - timedelta(days=rng.randint(1, days))
            timestamps.append(datetime.combine(day, datetime.min.time())
                              + timedelta(hours=rng.randint(8, 20), minutes=rng.randint(0, 59)))
        now = datetime.now()
        for minutes_ago in (95, 35):
            timestamps.append(max(datetime.combine(today, datetime.min.time()), now - timedelta(minutes=minutes_ago)))
        timestamps.sort()

        vat_rate = float(config.DEFAULT_SETTINGS["vat_rate"])
        created_invoices = []
        for moment in timestamps:
            cart = Cart()
            for product_id in rng.sample(product_ids, k=rng.choice([1, 1, 1, 2, 2, 3])):
                product = product_repo.get_by_id(product_id, conn=conn)
                quantity = 2 if product.selling_price < 2_000_000 and rng.random() < 0.4 else 1
                try:
                    cart.add(product, quantity)
                except AppError:
                    continue  # hết hàng -> bỏ qua sản phẩm này
            if cart.is_empty:
                continue
            discount_type, discount_value = config.DISCOUNT_AMOUNT, 0
            roll = rng.random()
            if roll < 0.2:
                discount_type, discount_value = config.DISCOUNT_PERCENT, rng.choice([2, 3, 5])
            elif roll < 0.35 and cart.subtotal > 5_000_000:
                discount_type, discount_value = config.DISCOUNT_AMOUNT, rng.choice([200_000, 500_000, 1_000_000])
            # Chỉ chọn khách hàng đã được tạo trước thời điểm mua hàng
            eligible = [cid for cid, created in customers_created if created <= moment.date()]
            customer_id = rng.choice(eligible) if eligible and rng.random() < 0.7 else None
            payment = rng.choice(config.PAYMENT_METHODS)
            invoice = pos.checkout(
                cart, customer_id=customer_id, employee_id=rng.choice(employee_ids),
                discount_type=discount_type, discount_value=discount_value, vat_rate=vat_rate,
                payment_method=payment, amount_received=None,
                note="", created_at=moment.strftime(DB_DATETIME_FORMAT), conn=conn,
            )
            created_invoices.append(invoice)

        # 6. Một hóa đơn bị hủy để minh họa quy tắc doanh thu (không tính hóa đơn hủy)
        if len(created_invoices) > 3:
            cancelled = created_invoices[-4]
            cancel_time = datetime.strptime(cancelled.created_at, DB_DATETIME_FORMAT) + timedelta(hours=1)
            pos.cancel_invoice(cancelled.invoice_id, "Khách đổi ý, cửa hàng đã hoàn tiền (dữ liệu mẫu)",
                               cancelled_by="Trần Bảo Ngọc",
                               cancelled_at=cancel_time.strftime(DB_DATETIME_FORMAT), conn=conn)

        settings_repo.set_many({SEED_FLAG: "1"}, conn=conn)

    log.info("Đã tạo dữ liệu mẫu: %d sản phẩm, %d khách hàng, %d hóa đơn.",
             len(PRODUCTS), len(CUSTOMERS), len(created_invoices))
    return True
