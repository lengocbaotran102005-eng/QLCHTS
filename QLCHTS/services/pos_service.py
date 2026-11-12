"""Nghiệp vụ bán hàng POS: giỏ hàng, tính tiền, thanh toán và hủy hóa đơn.

Công thức tính tiền (thống nhất trên giao diện, CSDL và hóa đơn):
    Thành tiền dòng   = Số lượng × Đơn giá
    Tổng tiền hàng    = Σ Thành tiền dòng
    Tiền chiết khấu   = Tổng tiền hàng × % chiết khấu        (chiết khấu theo %)
                      = Số tiền giảm trực tiếp               (chiết khấu theo số tiền)
    Giá trị tính thuế = Tổng tiền hàng − Tiền chiết khấu
    Tiền VAT          = Giá trị tính thuế × Thuế suất VAT
    Tổng thanh toán   = Tổng tiền hàng − Tiền chiết khấu + Tiền VAT
Các khoản tiền được làm tròn đến đơn vị đồng (làm tròn nửa lên).
"""
from contextlib import nullcontext
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import config
from database import Database
from errors import BusinessRuleError, NotFoundError, PriceChangedError, StockError, ValidationError
from models.invoice import Invoice, InvoiceDetail
from models.product import Product
from repositories.customer_repository import CustomerRepository
from repositories.employee_repository import EmployeeRepository
from repositories.inventory_repository import InventoryRepository
from repositories.invoice_repository import InvoiceRepository
from repositories.product_repository import ProductRepository
from utils.formatters import format_money, now_str, parse_db_datetime
from utils.validators import require_text


def _round_money(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Giỏ hàng (chỉ nằm trong bộ nhớ – KHÔNG trừ tồn kho khi thêm vào giỏ)
# ---------------------------------------------------------------------------
@dataclass
class CartItem:
    product_id: int
    sku: str
    product_name: str
    category_name: str
    material: str
    weight: float
    weight_unit: str
    unit_price: int
    quantity: int
    stock_available: int
    image_path: str = ""

    @property
    def line_total(self) -> int:
        return self.quantity * self.unit_price


class Cart:
    def __init__(self):
        self._items: dict[int, CartItem] = {}

    @property
    def items(self) -> list[CartItem]:
        return list(self._items.values())

    @property
    def is_empty(self) -> bool:
        return not self._items

    @property
    def subtotal(self) -> int:
        return sum(item.line_total for item in self._items.values())

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self._items.values())

    def get(self, product_id: int) -> CartItem | None:
        return self._items.get(product_id)

    def add(self, product: Product, quantity: int = 1) -> CartItem:
        """Thêm sản phẩm (hoặc tăng số lượng nếu đã có). Kiểm tra tồn kho hiện tại."""
        if not product.is_active:
            raise BusinessRuleError(f"Sản phẩm \"{product.product_name}\" đã ngừng kinh doanh.")
        if quantity <= 0:
            raise ValidationError("Số lượng thêm vào giỏ phải lớn hơn 0.")
        item = self._items.get(product.product_id)
        new_quantity = (item.quantity if item else 0) + quantity
        if new_quantity > product.stock_quantity:
            if product.stock_quantity <= 0:
                raise StockError(f"Sản phẩm \"{product.product_name}\" đã hết hàng.")
            raise StockError(
                f"Không thể thêm: \"{product.product_name}\" chỉ còn {product.stock_quantity} "
                f"trong kho (giỏ hàng đã có {item.quantity if item else 0})."
            )
        if item:
            item.quantity = new_quantity
            item.stock_available = product.stock_quantity
            item.unit_price = product.selling_price
        else:
            item = CartItem(
                product_id=product.product_id, sku=product.sku, product_name=product.product_name,
                category_name=product.category_name, material=product.material, weight=product.weight,
                weight_unit=product.weight_unit, unit_price=product.selling_price, quantity=quantity,
                stock_available=product.stock_quantity, image_path=product.image_path,
            )
            self._items[product.product_id] = item
        return item

    def set_quantity(self, product_id: int, quantity: int) -> None:
        item = self._items.get(product_id)
        if item is None:
            return
        if quantity <= 0:
            self.remove(product_id)
            return
        if quantity > item.stock_available:
            raise StockError(
                f"\"{item.product_name}\" chỉ còn {item.stock_available} trong kho, không thể bán {quantity}."
            )
        item.quantity = quantity

    def remove(self, product_id: int) -> None:
        self._items.pop(product_id, None)

    def clear(self) -> None:
        self._items.clear()

    def sync_with_products(self, products: dict[int, Product]) -> list[str]:
        """Cập nhật giá/tồn kho mới nhất từ CSDL cho các dòng trong giỏ. Trả về danh sách thay đổi."""
        messages = []
        for product_id, item in list(self._items.items()):
            product = products.get(product_id)
            if product is None or not product.is_active:
                messages.append(f"• Đã bỏ \"{item.product_name}\" khỏi giỏ (sản phẩm không còn kinh doanh).")
                self.remove(product_id)
                continue
            if product.selling_price != item.unit_price:
                messages.append(f"• Giá \"{item.product_name}\": {format_money(item.unit_price)} → "
                                f"{format_money(product.selling_price)}.")
                item.unit_price = product.selling_price
            item.stock_available = product.stock_quantity
            if item.quantity > product.stock_quantity:
                if product.stock_quantity <= 0:
                    messages.append(f"• Đã bỏ \"{item.product_name}\" khỏi giỏ (đã hết hàng).")
                    self.remove(product_id)
                else:
                    messages.append(f"• Giảm số lượng \"{item.product_name}\" còn {product.stock_quantity} "
                                    "(theo tồn kho).")
                    item.quantity = product.stock_quantity
        return messages


# ---------------------------------------------------------------------------
# Tính tiền
# ---------------------------------------------------------------------------
@dataclass
class PriceSummary:
    subtotal: int
    discount_type: str
    discount_value: float
    discount_amount: int
    taxable_amount: int
    vat_rate: float
    vat_amount: int
    total: int


def calculate_totals(subtotal: int, discount_type: str = config.DISCOUNT_AMOUNT, discount_value=0,
                     vat_rate=0.0) -> PriceSummary:
    """Tính chiết khấu, VAT và tổng thanh toán; ném ValidationError khi giá trị không hợp lệ."""
    subtotal = int(subtotal)
    if subtotal < 0:
        raise ValidationError("Tổng tiền hàng không hợp lệ.")
    try:
        discount_value = Decimal(str(discount_value or 0))
        vat = Decimal(str(vat_rate or 0))
    except Exception:
        raise ValidationError("Giá trị chiết khấu hoặc thuế suất không hợp lệ.") from None
    if discount_value < 0:
        raise ValidationError("Chiết khấu không được là số âm.")
    if not Decimal(0) <= vat <= Decimal(100):
        raise ValidationError("Thuế suất VAT phải nằm trong khoảng 0% – 100%.")

    if discount_type == config.DISCOUNT_PERCENT:
        if discount_value > 100:
            raise ValidationError("Chiết khấu theo phần trăm không được vượt quá 100%.")
        discount_amount = _round_money(Decimal(subtotal) * discount_value / Decimal(100))
    elif discount_type == config.DISCOUNT_AMOUNT:
        discount_amount = _round_money(discount_value)
        if discount_amount > subtotal:
            raise ValidationError(
                f"Tiền chiết khấu ({format_money(discount_amount)}) không được vượt quá tổng tiền hàng "
                f"({format_money(subtotal)})."
            )
    else:
        raise ValidationError("Hình thức chiết khấu không hợp lệ.")

    taxable = subtotal - discount_amount
    vat_amount = _round_money(Decimal(taxable) * vat / Decimal(100))
    return PriceSummary(
        subtotal=subtotal,
        discount_type=discount_type,
        discount_value=float(discount_value),
        discount_amount=discount_amount,
        taxable_amount=taxable,
        vat_rate=float(vat),
        vat_amount=vat_amount,
        total=taxable + vat_amount,
    )


# ---------------------------------------------------------------------------
# Thanh toán & hủy hóa đơn
# ---------------------------------------------------------------------------
class PosService:
    def __init__(self, db: Database, product_repo: ProductRepository, customer_repo: CustomerRepository,
                 employee_repo: EmployeeRepository, invoice_repo: InvoiceRepository,
                 inventory_repo: InventoryRepository):
        self.db = db
        self.products = product_repo
        self.customers = customer_repo
        self.employees = employee_repo
        self.invoices = invoice_repo
        self.inventory = inventory_repo

    def refresh_cart(self, cart: Cart) -> list[str]:
        """Đồng bộ giỏ hàng với giá và tồn kho hiện tại trong CSDL."""
        latest = {}
        for item in cart.items:
            product = self.products.get_by_id(item.product_id)
            if product:
                latest[product.product_id] = product
        return cart.sync_with_products(latest)

    def checkout(self, cart: Cart, *, customer_id: int | None = None, employee_id: int | None = None,
                 discount_type: str = config.DISCOUNT_AMOUNT, discount_value=0, vat_rate=0.0,
                 payment_method: str = config.PAYMENT_CASH, amount_received: int | None = None,
                 note: str = "", created_at: str | None = None, conn=None) -> Invoice:
        """Lập hóa đơn trong MỘT transaction:

        1. kiểm tra giỏ hàng, khách hàng, nhân viên, tồn kho, giá bán;
        2. sinh mã hóa đơn duy nhất; 3. ghi ``invoices``; 4. ghi ``invoice_details``;
        5. trừ tồn kho (UPDATE có điều kiện); 6. ghi ``inventory_transactions``.
        Lỗi ở bất kỳ bước nào -> ROLLBACK toàn bộ, tồn kho không bị trừ.
        ``conn`` cho phép tham gia một transaction lớn hơn (dùng khi tạo dữ liệu mẫu).
        """
        if cart.is_empty:
            raise BusinessRuleError("Giỏ hàng đang trống. Vui lòng chọn sản phẩm trước khi thanh toán.")
        if payment_method not in config.PAYMENT_METHODS:
            raise ValidationError("Vui lòng chọn phương thức thanh toán hợp lệ.")
        created_at = created_at or now_str()
        created_dt = parse_db_datetime(created_at)
        if created_dt is None:
            raise ValidationError("Thời điểm giao dịch không hợp lệ.")

        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as c:
            # --- Khách hàng (có thể là khách lẻ) ---
            invoice = Invoice(created_at=created_at, payment_method=payment_method,
                              note=(note or "").strip(), status=config.INVOICE_PAID)
            if customer_id:
                customer = self.customers.get_by_id(customer_id, conn=c)
                if customer is None:
                    raise NotFoundError("Khách hàng đã chọn không còn tồn tại. Vui lòng chọn lại.")
                invoice.customer_id = customer.customer_id
                invoice.customer_name = customer.customer_name
                invoice.customer_phone = customer.phone
                invoice.customer_address = customer.address
            else:
                invoice.customer_name = config.WALK_IN_CUSTOMER

            # --- Nhân viên bán hàng ---
            if employee_id:
                employee = self.employees.get_by_id(employee_id, conn=c)
                if employee is None:
                    raise NotFoundError("Nhân viên bán hàng không tồn tại.")
                invoice.employee_id = employee.employee_id
                invoice.employee_name = employee.employee_name

            # --- Kiểm tra từng sản phẩm với dữ liệu MỚI NHẤT trong CSDL ---
            lines: list[tuple[Product, int]] = []
            for item in cart.items:
                product = self.products.get_by_id(item.product_id, conn=c)
                if product is None:
                    raise NotFoundError(f"Sản phẩm {item.sku} không còn tồn tại trong cơ sở dữ liệu.")
                if not product.is_active:
                    raise BusinessRuleError(
                        f"Sản phẩm \"{product.product_name}\" ({product.sku}) đã ngừng kinh doanh. "
                        "Vui lòng xóa khỏi giỏ hàng."
                    )
                if item.quantity <= 0:
                    raise ValidationError(f"Số lượng của \"{product.product_name}\" không hợp lệ.")
                if item.quantity > product.stock_quantity:
                    raise StockError(
                        f"\"{product.product_name}\" chỉ còn {product.stock_quantity} trong kho, "
                        f"không đủ bán {item.quantity}."
                    )
                if product.selling_price != item.unit_price:
                    raise PriceChangedError(
                        f"Giá bán của \"{product.product_name}\" vừa thay đổi "
                        f"({format_money(item.unit_price)} → {format_money(product.selling_price)}). "
                        "Giỏ hàng sẽ được cập nhật giá mới, vui lòng kiểm tra lại trước khi thanh toán."
                    )
                lines.append((product, item.quantity))

            # --- Tính tiền ---
            subtotal = sum(p.selling_price * qty for p, qty in lines)
            summary = calculate_totals(subtotal, discount_type, discount_value, vat_rate)
            if payment_method == config.PAYMENT_CASH:
                received = summary.total if amount_received is None else int(amount_received)
                if received < summary.total:
                    raise ValidationError(
                        f"Số tiền khách đưa ({format_money(received)}) chưa đủ tổng thanh toán "
                        f"({format_money(summary.total)})."
                    )
            else:
                received = summary.total

            invoice.subtotal = summary.subtotal
            invoice.discount_type = summary.discount_type
            invoice.discount_value = summary.discount_value
            invoice.discount_amount = summary.discount_amount
            invoice.vat_rate = summary.vat_rate
            invoice.vat_amount = summary.vat_amount
            invoice.total_amount = summary.total
            invoice.amount_received = received
            invoice.change_amount = received - summary.total

            # --- Ghi hóa đơn, chi tiết, trừ kho, ghi lịch sử kho ---
            invoice.invoice_code = self.invoices.next_invoice_code(created_dt.strftime("%Y%m%d"), conn=c)
            invoice.invoice_id = self.invoices.insert_invoice(invoice, conn=c)
            for product, quantity in lines:
                self.invoices.insert_detail(invoice.invoice_id, product, quantity, conn=c)
                new_stock = self.products.change_stock(product.product_id, -quantity, conn=c)
                self.inventory.add(product.product_id, "SALE", -quantity, new_stock,
                                   reference_code=invoice.invoice_code,
                                   note=f"Xuất bán theo hóa đơn {invoice.invoice_code}",
                                   created_by=invoice.employee_name, created_at=created_at, conn=c)
        return invoice

    def cancel_invoice(self, invoice_id: int, reason: str, cancelled_by: str = "",
                       cancelled_at: str | None = None, conn=None) -> None:
        """Hủy hóa đơn đã thanh toán và hoàn trả tồn kho (trong một transaction).

        Hóa đơn đã hủy vẫn được lưu để tra cứu nhưng KHÔNG tính vào doanh thu.
        """
        reason = require_text(reason, "lý do hủy hóa đơn", 255)
        cancelled_at = cancelled_at or now_str()
        context = nullcontext(conn) if conn is not None else self.db.transaction()
        with context as c:
            invoice = self.invoices.get_by_id(invoice_id, conn=c)
            if invoice is None:
                raise NotFoundError("Hóa đơn không tồn tại.")
            if invoice.status != config.INVOICE_PAID:
                raise BusinessRuleError(f"Hóa đơn {invoice.invoice_code} đã được hủy trước đó.")
            details = self.invoices.get_details(invoice_id, conn=c)
            self.invoices.mark_cancelled(invoice_id, reason, cancelled_at, conn=c)
            for detail in details:
                new_stock = self.products.change_stock(detail.product_id, detail.quantity, conn=c)
                self.inventory.add(detail.product_id, "CANCEL", detail.quantity, new_stock,
                                   reference_code=invoice.invoice_code,
                                   note=f"Hoàn kho do hủy hóa đơn {invoice.invoice_code}: {reason}",
                                   created_by=cancelled_by, created_at=cancelled_at, conn=c)

    def get_invoice(self, invoice_id: int) -> tuple[Invoice, list[InvoiceDetail]]:
        """Đọc hóa đơn đã lưu (dùng cho xem trước, in lại, xuất PDF)."""
        invoice = self.invoices.get_by_id(invoice_id)
        if invoice is None:
            raise NotFoundError("Không tìm thấy hóa đơn trong cơ sở dữ liệu.")
        return invoice, self.invoices.get_details(invoice_id)

    def search_invoices(self, keyword: str = "", date_from: str | None = None, date_to: str | None = None,
                        status: str | None = None, limit: int = 1000) -> list[Invoice]:
        return self.invoices.search(keyword, date_from, date_to, status, limit=limit)
