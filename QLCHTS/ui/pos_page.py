"""Phân hệ 2 – Bán hàng POS: chọn sản phẩm, giỏ hàng, chiết khấu, VAT và thanh toán."""
from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import config
from errors import PriceChangedError, ValidationError
from models.product import Product
from services.pos_service import Cart, calculate_totals
from ui.customer_dialog import CustomerDialog
from ui.image_loader import ImageLoader
from ui.invoice_dialog import open_invoice
from ui.widgets import (
    ALIGN_RIGHT,
    VN_LOCALE,
    BadgeLabel,
    BasePage,
    Card,
    EmptyState,
    MoneySpinBox,
    SearchBox,
    add_shadow,
    ask_confirm,
    divider,
    field_label,
    handle_exception,
    hide_spin_buttons,
    hint_label,
    make_button,
    make_combo,
    make_double_spin,
    make_spin,
    safe_slot,
    show_info,
    show_warning,
    theme,
)
from utils.formatters import format_money, format_weight

CARD_WIDTH = 196
CARD_HEIGHT = 306


class ProductCard(QFrame):
    """Thẻ sản phẩm trong lưới bán hàng."""

    add_requested = Signal(int)

    def __init__(self, product: Product, threshold: int, parent=None):
        super().__init__(parent)
        self.product = product
        self.setObjectName("ProductCard")
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"{product.product_name}\n{product.description}\n(Nhấn đúp để thêm vào giỏ)")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        self.image = QLabel()
        self.image.setFixedSize(CARD_WIDTH - 20, 118)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image)
        self.load_image()

        meta_row = QHBoxLayout()
        category = QLabel(product.category_name)
        category.setObjectName("ProductMeta")
        level = product.stock_level(threshold)
        badge_text = {"out": "Hết hàng", "low": f"Sắp hết: {product.stock_quantity}",
                      "ok": f"Tồn: {product.stock_quantity}"}[level]
        meta_row.addWidget(category, 1)
        meta_row.addWidget(BadgeLabel(badge_text, level))
        layout.addSpacing(2)
        layout.addLayout(meta_row)

        name = QLabel(product.product_name)
        name.setObjectName("ProductName")
        name.setWordWrap(True)
        name.setFixedHeight(40)
        name.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(name)
        sku = QLabel(f"SKU: {product.sku}")
        sku.setObjectName("ProductMeta")
        material = QLabel(f"{product.material}  •  {format_weight(product.weight, product.weight_unit)}")
        material.setObjectName("ProductMeta")
        material.setToolTip(format_weight(product.weight, product.weight_unit, with_grams=True))
        layout.addWidget(sku)
        layout.addWidget(material)
        layout.addStretch()

        bottom = QHBoxLayout()
        price = QLabel(format_money(product.selling_price))
        price.setObjectName("ProductPrice")
        bottom.addWidget(price, 1)
        self.add_button = QToolButton()
        self.add_button.setObjectName("QtyButton")
        self.add_button.setIconSize(QSize(18, 18))
        self.add_button.setFixedSize(34, 34)
        self.add_button.setToolTip("Thêm vào giỏ hàng")
        self.add_button.setIcon(theme().icon("plus", "gold"))
        self.add_button.setEnabled(product.stock_quantity > 0)
        self.add_button.clicked.connect(lambda: self.add_requested.emit(product.product_id))
        bottom.addWidget(self.add_button)
        layout.addLayout(bottom)

    def load_image(self) -> None:
        self.image.setPixmap(ImageLoader.instance().pixmap(self.product.image_path, CARD_WIDTH - 20, 118, 12))

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self.product.stock_quantity > 0:
            self.add_requested.emit(self.product.product_id)
        super().mouseDoubleClickEvent(event)


class ProductGrid(QWidget):
    """Lưới thẻ sản phẩm tự sắp xếp lại số cột theo chiều rộng cửa sổ."""

    add_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ScrollContent")
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(2, 2, 2, 2)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.cards: list[ProductCard] = []
        self.columns = 0

    def set_products(self, products: list[Product], threshold: int, width: int) -> None:
        for card in self.cards:
            card.setParent(None)
            card.deleteLater()
        self.cards = []
        for product in products:
            card = ProductCard(product, threshold)
            card.add_requested.connect(self.add_requested.emit)
            self.cards.append(card)
        self.columns = 0
        self.relayout(width)

    def relayout(self, width: int) -> None:
        # n thẻ cần: n × rộng thẻ + (n − 1) × khoảng cách + lề 4px
        columns = max(1, (width - 4 + 14) // (CARD_WIDTH + 14))
        if columns == self.columns:
            return
        self.columns = columns
        for card in self.cards:
            self.grid.removeWidget(card)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // columns, index % columns, Qt.AlignmentFlag.AlignTop)
        for column in range(self.grid.columnCount()):
            self.grid.setColumnStretch(column, 0)
        for row in range(self.grid.rowCount()):
            self.grid.setRowStretch(row, 0)
        self.grid.setColumnStretch(columns, 1)
        self.grid.setRowStretch((len(self.cards) + columns - 1) // columns, 1)

    def reload_images(self, source: str) -> None:
        for card in self.cards:
            if card.product.image_path == source:
                card.load_image()


class QuantityEditor(QWidget):
    """Ô số lượng có nút giảm/tăng, giới hạn theo tồn kho."""

    changed = Signal(int, int)  # product_id, số lượng mới

    def __init__(self, product_id: int, quantity: int, maximum: int, parent=None):
        super().__init__(parent)
        self.product_id = product_id
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.minus = QToolButton()
        self.minus.setObjectName("QtyButton")
        self.minus.setIcon(theme().icon("minus", "text"))
        self.plus = QToolButton()
        self.plus.setObjectName("QtyButton")
        self.plus.setIcon(theme().icon("plus", "text"))
        for button in (self.minus, self.plus):
            button.setFixedSize(26, 26)
            button.setIconSize(QSize(14, 14))
        self.spin = make_spin()
        self.spin.setMinimumHeight(28)
        self.spin.setRange(1, max(1, maximum))
        self.spin.setValue(min(quantity, max(1, maximum)))
        hide_spin_buttons(self.spin)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin.setFixedWidth(46)
        self.spin.setToolTip(f"Tồn kho tối đa: {maximum}")
        layout.addWidget(self.minus)
        layout.addWidget(self.spin)
        layout.addWidget(self.plus)
        self.minus.clicked.connect(self._decrease)
        self.plus.clicked.connect(self._increase)
        self.spin.valueChanged.connect(lambda value: self.changed.emit(self.product_id, value))

    def _decrease(self) -> None:
        if self.spin.value() <= 1:
            self.changed.emit(self.product_id, 0)  # giảm về 0 -> xóa khỏi giỏ
        else:
            self.spin.setValue(self.spin.value() - 1)

    def _increase(self) -> None:
        if self.spin.value() >= self.spin.maximum():
            show_warning(self, "Không đủ tồn kho",
                         f"Số lượng trong giỏ đã bằng tồn kho hiện có ({self.spin.maximum()}).")
            return
        self.spin.setValue(self.spin.value() + 1)


class CartRow(QFrame):
    """Một dòng trong giỏ hàng: tên sản phẩm, thông tin, số lượng và thành tiền."""

    def __init__(self, item, on_quantity, on_remove, parent=None):
        super().__init__(parent)
        self.setObjectName("CartRow")
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 8, 8, 10)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        name = QLabel(item.product_name)
        name.setObjectName("CartItemName")
        name.setWordWrap(True)
        remove = QToolButton()
        remove.setObjectName("DangerTool")
        remove.setToolTip("Xóa khỏi giỏ")
        remove.setIcon(theme().icon("trash", "danger"))
        remove.clicked.connect(lambda: on_remove(item.product_id))
        meta = QLabel(f"{item.sku}  •  {format_weight(item.weight, item.weight_unit)}\n"
                      f"Đơn giá: {format_money(item.unit_price)}")
        meta.setObjectName("CartItemMeta")
        self.editor = QuantityEditor(item.product_id, item.quantity, item.stock_available)
        self.editor.changed.connect(on_quantity)
        self.total = QLabel(format_money(item.line_total))
        self.total.setObjectName("CartLineTotal")
        self.total.setAlignment(ALIGN_RIGHT)
        self.total.setMinimumWidth(110)
        grid.addWidget(name, 0, 0, 1, 2)
        grid.addWidget(remove, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(meta, 1, 0)
        grid.addWidget(self.editor, 1, 1, Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.total, 1, 2, Qt.AlignmentFlag.AlignVCenter)
        grid.setColumnStretch(0, 1)


class PosPage(BasePage):
    title = "Bán hàng POS"
    subtitle = "Chọn sản phẩm, lập giỏ hàng và thanh toán – tồn kho chỉ bị trừ khi hóa đơn được lưu thành công"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.cart = Cart()
        self.products: list[Product] = []
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.addWidget(self._build_catalog())
        splitter.addWidget(self._build_cart_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([860, 450])
        self.root.addWidget(splitter)
        ImageLoader.instance().image_ready.connect(self.grid.reload_images)
        QShortcut(QKeySequence("F2"), self, activated=lambda: self.search.setFocus())
        QShortcut(QKeySequence("F9"), self, activated=self.checkout)
        self._render_cart()

    # ================================================================== dựng giao diện
    def _build_catalog(self) -> QWidget:
        card = Card("Danh mục sản phẩm", "Tìm theo tên, mã SKU, chất liệu hoặc danh mục (gõ không dấu cũng được) – F2")
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = SearchBox("Tìm sản phẩm: nhẫn, dây chuyền, BT-N24K, vàng 18K...")
        self.search.search_requested.connect(lambda _t: self.load_products())
        self.category_combo = make_combo([("Tất cả danh mục", None)])
        self.category_combo.setMinimumWidth(190)
        self.category_combo.currentIndexChanged.connect(lambda _i: self.load_products())
        self.in_stock_check = QCheckBox("Chỉ hiện còn hàng")
        self.in_stock_check.toggled.connect(lambda _c: self.load_products())
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.category_combo)
        toolbar.addWidget(self.in_stock_check)
        card.add_layout(toolbar)
        self.result_label = hint_label("")
        card.add(self.result_label)

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid = ProductGrid()
        self.grid.add_requested.connect(self.add_to_cart)
        self.grid_empty = EmptyState("search", "Không tìm thấy sản phẩm",
                                     "Thử từ khóa khác hoặc chọn \"Tất cả danh mục\".")
        self.grid_scroll.setWidget(self.grid)
        self.grid_scroll.viewport().installEventFilter(self)
        self.catalog_stack = QStackedWidget()
        self.catalog_stack.addWidget(self.grid_scroll)
        self.catalog_stack.addWidget(self.grid_empty)
        card.add(self.catalog_stack, 1)
        card.setMinimumWidth(CARD_WIDTH + 70)
        return card

    def _build_cart_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("CartPanel")
        panel.setMinimumWidth(430)
        panel.setMaximumWidth(560)
        add_shadow(panel, blur=30, offset_y=6, alpha=50)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("ScrollContent")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        header = QHBoxLayout()
        title = QLabel("Giỏ hàng")
        title.setObjectName("CardTitle")
        self.cart_badge = BadgeLabel("0 sản phẩm", "gold")
        clear_button = make_button("Xóa giỏ", "trash", "ghost", size="small")
        clear_button.clicked.connect(self.clear_cart)
        header.addWidget(title)
        header.addWidget(self.cart_badge)
        header.addStretch()
        header.addWidget(clear_button)
        layout.addLayout(header)

        # Khách hàng & nhân viên
        people = QGridLayout()
        people.setHorizontalSpacing(8)
        people.setVerticalSpacing(6)
        people.addWidget(field_label("Khách hàng"), 0, 0)
        self.customer_combo = make_combo(editable=True)
        self.customer_combo.setInsertPolicy(self.customer_combo.InsertPolicy.NoInsert)
        self.customer_combo.lineEdit().setPlaceholderText("Gõ tên hoặc SĐT để tìm khách hàng")
        completer = self.customer_combo.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        add_customer = QToolButton()
        add_customer.setToolTip("Thêm khách hàng mới")
        add_customer.setIconSize(QSize(20, 20))
        add_customer.setObjectName("QtyButton")
        add_customer.setFixedSize(36, 36)
        theme().bind_icon(add_customer, "user-plus", "gold")
        add_customer.clicked.connect(self.add_customer)
        customer_row = QHBoxLayout()
        customer_row.setSpacing(6)
        customer_row.addWidget(self.customer_combo, 1)
        customer_row.addWidget(add_customer)
        people.addLayout(customer_row, 1, 0)
        people.addWidget(field_label("Nhân viên bán hàng"), 0, 1)
        self.employee_combo = make_combo()
        self.employee_combo.setMinimumWidth(130)
        people.addWidget(self.employee_combo, 1, 1)
        people.setColumnStretch(0, 3)
        people.setColumnStretch(1, 2)
        layout.addLayout(people)

        # Danh sách sản phẩm trong giỏ
        self.cart_scroll = QScrollArea()
        self.cart_scroll.setWidgetResizable(True)
        self.cart_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cart_list = QWidget()
        self.cart_list.setObjectName("ScrollContent")
        self.cart_layout = QVBoxLayout(self.cart_list)
        self.cart_layout.setContentsMargins(0, 0, 4, 0)
        self.cart_layout.setSpacing(8)
        self.cart_layout.addStretch()
        self.cart_scroll.setWidget(self.cart_list)
        self.cart_rows: dict[int, CartRow] = {}
        self.cart_empty = EmptyState("cart", "Giỏ hàng đang trống",
                                     "Nhấn nút + hoặc nhấn đúp vào sản phẩm bên trái để thêm vào giỏ.")
        self.cart_stack = QStackedWidget()
        self.cart_stack.addWidget(self.cart_scroll)
        self.cart_stack.addWidget(self.cart_empty)
        self.cart_stack.setMinimumHeight(170)
        layout.addWidget(self.cart_stack, 1)

        # Tổng tiền
        totals = QFrame()
        totals.setObjectName("TotalsBox")
        grid = QGridLayout(totals)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        row = 0
        grid.addWidget(self._caption("Tổng tiền hàng"), row, 0)
        self.subtotal_label = self._value("0 ₫")
        grid.addWidget(self.subtotal_label, row, 2)
        row += 1
        grid.addWidget(self._caption("Chiết khấu"), row, 0)
        discount_box = QHBoxLayout()
        discount_box.setSpacing(4)
        self.discount_type = make_combo([("%", config.DISCOUNT_PERCENT), ("₫", config.DISCOUNT_AMOUNT)])
        self.discount_type.setFixedWidth(64)
        self.discount_value = make_double_spin()
        self.discount_value.setLocale(VN_LOCALE)
        self.discount_value.setGroupSeparatorShown(True)
        hide_spin_buttons(self.discount_value)
        self.discount_value.setAlignment(ALIGN_RIGHT)
        self.discount_value.setMinimumHeight(34)
        self.discount_value.setFixedWidth(120)
        discount_box.addWidget(self.discount_type)
        discount_box.addWidget(self.discount_value)
        grid.addLayout(discount_box, row, 1)
        self.discount_label = self._value("0 ₫", "DiscountValue")
        grid.addWidget(self.discount_label, row, 2)
        row += 1
        grid.addWidget(self._caption("Thuế VAT"), row, 0)
        self.vat_spin = make_double_spin()
        self.vat_spin.setRange(0, 100)
        self.vat_spin.setDecimals(1)
        self.vat_spin.setSuffix(" %")
        self.vat_spin.setAlignment(ALIGN_RIGHT)
        self.vat_spin.setMinimumHeight(34)
        self.vat_spin.setFixedWidth(120)
        self.vat_spin.setToolTip("Thuế suất VAT lấy từ Cài đặt hệ thống, có thể điều chỉnh cho từng hóa đơn")
        vat_box = QHBoxLayout()
        vat_box.addStretch()
        vat_box.addWidget(self.vat_spin)
        grid.addLayout(vat_box, row, 1)
        self.vat_label = self._value("0 ₫")
        grid.addWidget(self.vat_label, row, 2)
        row += 1
        grid.addWidget(divider(), row, 0, 1, 3)
        row += 1
        grand = QLabel("TỔNG THANH TOÁN")
        grand.setObjectName("GrandTotalCaption")
        grid.addWidget(grand, row, 0, 1, 2)
        self.total_label = QLabel("0 ₫")
        self.total_label.setObjectName("GrandTotal")
        self.total_label.setAlignment(ALIGN_RIGHT)
        grid.addWidget(self.total_label, row, 1, 1, 2)
        row += 1
        grid.addWidget(hint_label("Thành tiền = SL × Đơn giá  •  VAT = (Tiền hàng − Chiết khấu) × Thuế suất\n"
                                  "Tổng thanh toán = Tổng tiền hàng − Chiết khấu + VAT", "FormulaHint"),
                       row, 0, 1, 3)
        grid.setColumnStretch(2, 1)
        layout.addWidget(totals)
        self.error_label = hint_label("", "ErrorHint")
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Thanh toán
        pay = QGridLayout()
        pay.setHorizontalSpacing(8)
        pay.setVerticalSpacing(6)
        pay.addWidget(field_label("Phương thức thanh toán"), 0, 0)
        self.payment_combo = make_combo([(m, m) for m in config.PAYMENT_METHODS])
        pay.addWidget(self.payment_combo, 1, 0)
        pay.addWidget(field_label("Khách đưa (tiền mặt)"), 0, 1)
        received_row = QHBoxLayout()
        received_row.setSpacing(4)
        self.received_spin = MoneySpinBox()
        exact = make_button("Đủ", size="small", tooltip="Khách đưa đúng số tiền thanh toán")
        exact.clicked.connect(lambda: self.received_spin.setValue(self._summary_total()))
        received_row.addWidget(self.received_spin, 1)
        received_row.addWidget(exact)
        pay.addLayout(received_row, 1, 1)
        self.change_label = hint_label("Tiền thừa trả khách: 0 ₫", "SuccessHint")
        pay.addWidget(self.change_label, 2, 0, 1, 2)
        layout.addLayout(pay)
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("Ghi chú hóa đơn (không bắt buộc): khắc tên, hẹn lấy hàng...")
        self.note_edit.setMinimumHeight(36)
        layout.addWidget(self.note_edit)

        layout.addStretch()

        # Nút thanh toán luôn hiển thị ở đáy khung (không bị cuộn khuất)
        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(18, 6, 18, 14)
        self.checkout_button = make_button("Thanh toán  (F9)", "check", "primary", size="large")
        self.checkout_button.clicked.connect(self.checkout)
        footer_layout.addWidget(self.checkout_button)
        outer.addWidget(footer)

        self.discount_type.currentIndexChanged.connect(self._on_discount_type)
        self.discount_value.valueChanged.connect(lambda _v: self._update_totals())
        self.vat_spin.valueChanged.connect(lambda _v: self._update_totals())
        self.payment_combo.currentIndexChanged.connect(lambda _i: self._update_totals())
        self.received_spin.valueChanged.connect(lambda _v: self._update_change())
        self._on_discount_type()
        return panel

    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("TotalCaption")
        return label

    @staticmethod
    def _value(text: str, name: str = "TotalValue") -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setAlignment(ALIGN_RIGHT)
        return label

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is self.grid_scroll.viewport() and event.type() == QEvent.Type.Resize:
            self.grid.relayout(event.size().width())
        return super().eventFilter(watched, event)

    # ================================================================== dữ liệu
    def refresh(self) -> None:
        self._load_categories()
        self._load_people()
        if self.cart.is_empty:
            self.vat_spin.setValue(self.ctx.settings.vat_rate)
        else:
            messages = self.ctx.pos.refresh_cart(self.cart)
            if messages:
                show_info(self, "Giỏ hàng đã được cập nhật", "Dữ liệu sản phẩm vừa thay đổi:\n" + "\n".join(messages))
        self.load_products()
        self._render_cart()

    def _load_categories(self) -> None:
        current = self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("Tất cả danh mục", None)
        for category in self.ctx.products.list_categories():
            self.category_combo.addItem(f"{category.category_name} ({category.product_count})", category.category_id)
        index = self.category_combo.findData(current)
        self.category_combo.setCurrentIndex(max(index, 0))
        self.category_combo.blockSignals(False)

    def _load_people(self, select_customer: int | None = None) -> None:
        current_customer = select_customer if select_customer is not None else self.customer_combo.currentData()
        self.customer_combo.blockSignals(True)
        self.customer_combo.clear()
        self.customer_combo.addItem(f"{config.WALK_IN_CUSTOMER} (không lưu thông tin)", None)
        for customer in self.ctx.customers.search():
            self.customer_combo.addItem(customer.display_name, customer.customer_id)
        self.customer_combo.setCurrentIndex(max(self.customer_combo.findData(current_customer), 0))
        self.customer_combo.lineEdit().setCursorPosition(0)
        self.customer_combo.blockSignals(False)

        current_employee = self.employee_combo.currentData()
        self.employee_combo.clear()
        for employee in self.ctx.settings.employees(active_only=True):
            self.employee_combo.addItem(employee.employee_name, employee.employee_id)
        if current_employee is not None:
            self.employee_combo.setCurrentIndex(max(self.employee_combo.findData(current_employee), 0))

    def load_products(self) -> None:
        try:
            self.products = self.ctx.products.search(self.search.text(), self.category_combo.currentData(),
                                                     active=True, in_stock_only=self.in_stock_check.isChecked())
        except Exception as exc:  # noqa: BLE001
            handle_exception(self, exc)
            return
        threshold = self.ctx.settings.low_stock_threshold
        self.grid.set_products(self.products, threshold, self.grid_scroll.viewport().width())
        self.catalog_stack.setCurrentIndex(0 if self.products else 1)
        self.result_label.setText(f"Tìm thấy {len(self.products)} sản phẩm đang kinh doanh "
                                  "(dữ liệu truy vấn từ SQLite).")

    # ================================================================== giỏ hàng
    @safe_slot
    def add_to_cart(self, product_id: int) -> None:
        product = self.ctx.products.get(product_id)  # đọc tồn kho mới nhất từ CSDL
        item = self.cart.add(product, 1)
        self._render_cart()
        self.notify(f"Đã thêm \"{product.product_name}\" vào giỏ (SL: {item.quantity}).")

    def _render_cart(self) -> None:
        for row in self.cart_rows.values():
            row.setParent(None)
            row.deleteLater()
        self.cart_rows = {}
        for item in self.cart.items:
            row = CartRow(item, self._on_quantity_changed, self._remove_item)
            self.cart_layout.insertWidget(self.cart_layout.count() - 1, row)
            self.cart_rows[item.product_id] = row
        self.cart_stack.setCurrentIndex(0 if self.cart_rows else 1)
        self.cart_badge.set_kind("gold", f"{self.cart.total_quantity} sản phẩm")
        self._update_totals()

    def _on_quantity_changed(self, product_id: int, quantity: int) -> None:
        try:
            self.cart.set_quantity(product_id, quantity)
        except Exception as exc:  # noqa: BLE001
            handle_exception(self, exc)
        item = self.cart.get(product_id)
        if quantity <= 0 or item is None:
            self._render_cart()
            return
        self.cart_rows[product_id].total.setText(format_money(item.line_total))
        self.cart_badge.set_kind("gold", f"{self.cart.total_quantity} sản phẩm")
        self._update_totals()

    def _remove_item(self, product_id: int) -> None:
        self.cart.remove(product_id)
        self._render_cart()

    def clear_cart(self) -> None:
        if self.cart.is_empty:
            return
        if ask_confirm(self, "Xóa giỏ hàng", "Bạn có chắc muốn xóa toàn bộ sản phẩm trong giỏ hàng?", "Xóa giỏ",
                       danger=True):
            self._reset_after_sale()

    @safe_slot
    def add_customer(self) -> None:
        dialog = CustomerDialog(self.ctx, self)
        if dialog.exec() and dialog.customer_id:
            self._load_people(select_customer=dialog.customer_id)
            self.notify("Đã thêm khách hàng mới và chọn cho hóa đơn hiện tại.")

    # ================================================================== tính tiền
    def _on_discount_type(self) -> None:
        self.discount_value.blockSignals(True)
        if self.discount_type.currentData() == config.DISCOUNT_PERCENT:
            self.discount_value.setDecimals(2)
            self.discount_value.setRange(0, 100)
            self.discount_value.setSuffix(" %")
            self.discount_value.setSingleStep(1)
        else:
            self.discount_value.setDecimals(0)
            self.discount_value.setRange(0, 100_000_000_000)
            self.discount_value.setSuffix(" ₫")
            self.discount_value.setSingleStep(100_000)
        self.discount_value.setValue(0)
        self.discount_value.blockSignals(False)
        self._update_totals()

    def _current_summary(self):
        return calculate_totals(self.cart.subtotal, self.discount_type.currentData(), self.discount_value.value(),
                                self.vat_spin.value())

    def _summary_total(self) -> int:
        try:
            return self._current_summary().total
        except ValidationError:
            return 0

    def _update_totals(self) -> None:
        try:
            summary = self._current_summary()
        except ValidationError as exc:
            self.error_label.setText(exc.message)
            self.error_label.show()
            self.checkout_button.setEnabled(False)
            self.subtotal_label.setText(format_money(self.cart.subtotal))
            self.total_label.setText("—")
            return
        self.error_label.hide()
        self.subtotal_label.setText(format_money(summary.subtotal))
        self.discount_label.setText(f"− {format_money(summary.discount_amount)}")
        self.vat_label.setText(format_money(summary.vat_amount))
        self.total_label.setText(format_money(summary.total))
        self.checkout_button.setEnabled(not self.cart.is_empty)
        is_cash = self.payment_combo.currentData() == config.PAYMENT_CASH
        self.received_spin.setEnabled(is_cash)
        if not is_cash:
            self.received_spin.setValue(summary.total)
        self._update_change()

    def _update_change(self) -> None:
        total = self._summary_total()
        if self.payment_combo.currentData() != config.PAYMENT_CASH:
            self.change_label.setObjectName("Hint")
            self.change_label.setText("Thanh toán không dùng tiền mặt – ghi nhận đủ số tiền thanh toán.")
        else:
            change = self.received_spin.int_value() - total
            if self.received_spin.int_value() == 0:
                self.change_label.setObjectName("Hint")
                self.change_label.setText("Nhập số tiền khách đưa hoặc nhấn \"Đủ\".")
            elif change >= 0:
                self.change_label.setObjectName("SuccessHint")
                self.change_label.setText(f"Tiền thừa trả khách: {format_money(change)}")
            else:
                self.change_label.setObjectName("ErrorHint")
                self.change_label.setText(f"Khách đưa còn thiếu: {format_money(-change)}")
        self.change_label.style().unpolish(self.change_label)
        self.change_label.style().polish(self.change_label)

    # ================================================================== thanh toán
    @safe_slot
    def checkout(self) -> None:
        # 1. Giỏ hàng không rỗng
        if self.cart.is_empty:
            show_warning(self, "Giỏ hàng trống", "Vui lòng thêm sản phẩm vào giỏ trước khi thanh toán.")
            return
        # 2. Đồng bộ tồn kho/giá mới nhất (không bán vượt tồn kho)
        changes = self.ctx.pos.refresh_cart(self.cart)
        if changes:
            self._render_cart()
            show_info(self, "Giỏ hàng đã được cập nhật",
                      "Tồn kho hoặc giá đã thay đổi, vui lòng kiểm tra lại:\n" + "\n".join(changes))
            return
        # 3. Khách hàng, nhân viên, tiền thanh toán
        customer_index = self.customer_combo.findText(self.customer_combo.currentText())
        if customer_index < 0:
            show_warning(self, "Khách hàng không hợp lệ",
                         "Khách hàng đã nhập không có trong danh sách. Hãy chọn \"Khách lẻ\", chọn khách hàng có "
                         "sẵn hoặc nhấn nút thêm khách hàng mới.")
            return
        customer_id = self.customer_combo.itemData(customer_index)
        employee_id = self.employee_combo.currentData()
        if employee_id is None:
            show_warning(self, "Thiếu nhân viên bán hàng",
                         "Vui lòng chọn nhân viên bán hàng (thêm nhân viên tại Cài đặt hệ thống).")
            return
        summary = self._current_summary()
        payment = self.payment_combo.currentData()
        received = self.received_spin.int_value() if payment == config.PAYMENT_CASH else summary.total
        if payment == config.PAYMENT_CASH and received == 0:
            received = summary.total  # không nhập -> coi như khách đưa đủ
        if payment == config.PAYMENT_CASH and received < summary.total:
            show_warning(self, "Chưa đủ tiền", f"Khách đưa còn thiếu {format_money(summary.total - received)}.")
            return
        customer_name = self.customer_combo.itemText(customer_index).split(" – ")[0]
        if not ask_confirm(self, "Xác nhận thanh toán",
                           f"Khách hàng: {customer_name}\nSố sản phẩm: {self.cart.total_quantity}\n"
                           f"Tổng thanh toán: {format_money(summary.total)}\nPhương thức: {payment}\n\n"
                           "Xác nhận lập hóa đơn và trừ tồn kho?", "Thanh toán"):
            return
        # 4–8. Lập hóa đơn trong một transaction SQLite
        try:
            invoice = self.ctx.pos.checkout(
                self.cart, customer_id=customer_id, employee_id=employee_id,
                discount_type=summary.discount_type, discount_value=summary.discount_value,
                vat_rate=summary.vat_rate, payment_method=payment, amount_received=received,
                note=self.note_edit.text(),
            )
        except PriceChangedError as exc:
            self.ctx.pos.refresh_cart(self.cart)
            self._render_cart()
            show_warning(self, exc.title, exc.message)
            return
        # 9. Thông báo thành công, làm mới dữ liệu và 10. mở hóa đơn
        self._reset_after_sale()
        self.load_products()
        self.notify(f"Thanh toán thành công hóa đơn {invoice.invoice_code} – {format_money(invoice.total_amount)}")
        show_info(self, "Thanh toán thành công",
                  f"Đã lưu hóa đơn {invoice.invoice_code}.\nTổng thanh toán: {format_money(invoice.total_amount)}"
                  + (f"\nTiền thừa trả khách: {format_money(invoice.change_amount)}" if invoice.change_amount else ""))
        open_invoice(self, self.ctx, invoice.invoice_id)

    def _reset_after_sale(self) -> None:
        self.cart.clear()
        self.discount_type.setCurrentIndex(0)
        self.discount_value.setValue(0)
        self.vat_spin.setValue(self.ctx.settings.vat_rate)
        self.payment_combo.setCurrentIndex(0)
        self.received_spin.setValue(0)
        self.note_edit.clear()
        self.customer_combo.setCurrentIndex(0)
        self.customer_combo.lineEdit().setCursorPosition(0)
        self._render_cart()
