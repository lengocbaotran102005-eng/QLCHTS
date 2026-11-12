"""Phân hệ 3 – Quản lý sản phẩm: xem, thêm, sửa, xóa / ngừng kinh doanh, quản lý ảnh."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import config
from errors import ProductInUseError
from models.product import Product
from ui.image_loader import ImageLoader
from ui.stock_dialog import StockDialog
from ui.widgets import (
    ALIGN_RIGHT,
    BasePage,
    Card,
    MoneySpinBox,
    SearchBox,
    ask_confirm,
    ask_text,
    field_label,
    fill_table,
    hint_label,
    make_button,
    make_combo,
    make_double_spin,
    make_item,
    make_spin,
    run_in_background,
    safe_slot,
    select_by_id,
    selected_id,
    setup_table,
    show_info,
    show_warning,
    theme,
)
from utils.formatters import format_decimal, format_money, format_weight, to_grams
from utils.image_utils import SUPPORTED_FILTER, check_image_source, download_image, import_local_image, is_url

COMMON_MATERIALS = [
    "Vàng 24K (9999)", "Vàng 18K (750)", "Vàng 14K (585)", "Vàng 10K (416)", "Vàng trắng 18K",
    "Vàng trắng 14K", "Vàng hồng 18K", "Bạc 925", "Bạch kim (Platinum)", "Vàng 18K & kim cương",
    "Vàng 18K & ngọc trai", "Vàng 18K & Ruby", "Vàng trắng 14K & Sapphire",
]


class ProductsPage(BasePage):
    title = "Quản lý sản phẩm"
    subtitle = "Thêm, sửa, ngừng kinh doanh sản phẩm – dữ liệu được lưu trực tiếp vào bảng products (SQLite)"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.current_id: int | None = None
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)
        splitter.addWidget(self._build_list())
        splitter.addWidget(self._build_form())
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([900, 430])
        self.root.addWidget(splitter)
        ImageLoader.instance().image_ready.connect(self._on_image_ready)

    # ================================================================== danh sách
    def _build_list(self) -> QWidget:
        card = Card("Danh sách sản phẩm", "Chọn một dòng để xem và chỉnh sửa thông tin ở biểu mẫu bên phải")
        add_button = make_button("Thêm sản phẩm", "plus", "primary")
        add_button.clicked.connect(self.new_product)
        card.add_header_widget(add_button)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search = SearchBox("Tìm theo tên, mã SKU, chất liệu, danh mục...")
        self.search.search_requested.connect(lambda _t: self.load_products())
        self.category_filter = make_combo([("Tất cả danh mục", None)])
        self.category_filter.setMinimumWidth(170)
        self.category_filter.currentIndexChanged.connect(lambda _i: self.load_products())
        self.status_filter = make_combo([("Tất cả trạng thái", None), ("Đang kinh doanh", True),
                                         ("Ngừng kinh doanh", False)])
        self.status_filter.currentIndexChanged.connect(lambda _i: self.load_products())
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.category_filter)
        toolbar.addWidget(self.status_filter)
        card.add_layout(toolbar)
        self.table = QTableWidget()
        setup_table(self.table, ["Mã SP", "Tên sản phẩm", "SKU", "Danh mục", "Chất liệu", "Trọng lượng",
                                 "Giá nhập", "Giá bán", "Tồn kho", "Trạng thái"], stretch=1, row_height=46)
        self.table.setIconSize(QSize(36, 36))
        self.table.itemSelectionChanged.connect(self._on_selection)
        card.add(self.table, 1)
        self.count_label = hint_label("")
        card.add(self.count_label)
        return card

    # ================================================================== biểu mẫu
    def _build_form(self) -> QWidget:
        outer = Card(margins=0)
        outer.setMinimumWidth(400)
        outer.setMaximumWidth(520)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("ScrollContent")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        scroll.setWidget(body)
        outer.add(scroll, 1)

        self.form_title = QLabel("Thêm sản phẩm mới")
        self.form_title.setObjectName("CardTitle")
        layout.addWidget(self.form_title)
        self.form_hint = hint_label("Nhập thông tin và nhấn \"Lưu sản phẩm\". Các trường có dấu * là bắt buộc.")
        layout.addWidget(self.form_hint)

        # Ảnh sản phẩm
        self.image_preview = QLabel()
        self.image_preview.setObjectName("ImagePreview")
        self.image_preview.setFixedHeight(190)
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_preview)
        image_buttons = QHBoxLayout()
        image_buttons.setSpacing(6)
        choose = make_button("Chọn ảnh từ máy", "image", size="small")
        choose.clicked.connect(self.choose_image)
        from_url = make_button("Tải từ URL", "link", size="small")
        from_url.clicked.connect(self.image_from_url)
        clear = make_button("Bỏ ảnh", "close", "ghost", size="small")
        clear.clicked.connect(lambda: self._set_image_path(""))
        image_buttons.addWidget(choose)
        image_buttons.addWidget(from_url)
        image_buttons.addWidget(clear)
        image_buttons.addStretch()
        layout.addLayout(image_buttons)
        self.image_edit = QLineEdit()
        self.image_edit.setPlaceholderText("Đường dẫn ảnh cục bộ hoặc URL http(s)://")
        self.image_edit.setMinimumHeight(34)
        self.image_edit.editingFinished.connect(lambda: self._set_image_path(self.image_edit.text()))
        layout.addWidget(self.image_edit)
        self.image_status = hint_label("")
        layout.addWidget(self.image_status)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        row = 0

        def add_field(label: str, widget, column: int = 0, span: int = 2):
            grid.addWidget(field_label(label), row, column, 1, span)
            grid.addWidget(widget, row + 1, column, 1, span)

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("Tự sinh, ví dụ SP0016")
        self.sku_edit = QLineEdit()
        self.sku_edit.setPlaceholderText("Ví dụ: BT-N24K-016")
        add_field("Mã sản phẩm", self.code_edit, 0, 1)
        add_field("Mã SKU *", self.sku_edit, 1, 1)
        row += 2
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Ví dụ: Nhẫn nữ vàng 18K đính đá")
        add_field("Tên sản phẩm *", self.name_edit)
        row += 2
        category_row = QWidget()
        category_layout = QHBoxLayout(category_row)
        category_layout.setContentsMargins(0, 0, 0, 0)
        category_layout.setSpacing(6)
        self.category_combo = make_combo()
        add_category = QToolButton()
        add_category.setObjectName("QtyButton")
        add_category.setToolTip("Thêm danh mục mới")
        add_category.setFixedSize(36, 36)
        theme().bind_icon(add_category, "plus", "gold")
        add_category.clicked.connect(self.add_category)
        category_layout.addWidget(self.category_combo, 1)
        category_layout.addWidget(add_category)
        add_field("Danh mục *", category_row)
        row += 2
        self.material_combo = make_combo([(m, m) for m in COMMON_MATERIALS], editable=True)
        add_field("Chất liệu *", self.material_combo)
        row += 2
        self.weight_spin = make_double_spin()
        self.weight_spin.setRange(0, 100000)
        self.weight_spin.setDecimals(3)
        self.weight_spin.setSingleStep(0.1)
        self.weight_spin.setMinimumHeight(36)
        self.unit_combo = make_combo([(u, u) for u in config.WEIGHT_UNITS])
        add_field("Trọng lượng *", self.weight_spin, 0, 1)
        add_field("Đơn vị trọng lượng", self.unit_combo, 1, 1)
        row += 2
        self.weight_hint = hint_label("")
        grid.addWidget(self.weight_hint, row, 0, 1, 2)
        row += 1
        self.cost_spin = MoneySpinBox()
        self.price_spin = MoneySpinBox()
        add_field("Giá nhập (₫)", self.cost_spin, 0, 1)
        add_field("Giá bán (₫) *", self.price_spin, 1, 1)
        row += 2
        self.margin_hint = hint_label("")
        grid.addWidget(self.margin_hint, row, 0, 1, 2)
        row += 1
        self.stock_spin = make_spin()
        self.stock_spin.setRange(0, 1_000_000)
        self.stock_spin.setMinimumHeight(36)
        self.active_check = QCheckBox("Đang kinh doanh")
        self.active_check.setChecked(True)
        add_field("Số lượng tồn kho", self.stock_spin, 0, 1)
        add_field("Trạng thái kinh doanh", self.active_check, 1, 1)
        row += 2
        self.stock_hint = hint_label("")
        grid.addWidget(self.stock_hint, row, 0, 1, 2)
        row += 1
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Mô tả kiểu dáng, kích thước, giấy kiểm định...")
        self.description_edit.setFixedHeight(80)
        add_field("Mô tả sản phẩm", self.description_edit)
        row += 2
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        for widget in (self.code_edit, self.sku_edit, self.name_edit):
            widget.setMinimumHeight(36)
        layout.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        reset = make_button("Làm mới", "refresh", "ghost")
        reset.clicked.connect(self.new_product)
        self.save_button = make_button("Lưu sản phẩm", "save", "primary")
        self.save_button.clicked.connect(self.save_product)
        actions.addWidget(reset)
        actions.addStretch()
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

        more = QHBoxLayout()
        more.setSpacing(8)
        self.toggle_button = make_button("Ngừng kinh doanh", "power", size="small")
        self.toggle_button.clicked.connect(self.toggle_active)
        self.stock_button = make_button("Điều chỉnh kho", "clipboard", size="small")
        self.stock_button.clicked.connect(self.adjust_stock)
        self.delete_button = make_button("Xóa", "trash", "danger", size="small")
        self.delete_button.clicked.connect(self.delete_product)
        more.addWidget(self.toggle_button)
        more.addWidget(self.stock_button)
        more.addStretch()
        more.addWidget(self.delete_button)
        layout.addLayout(more)
        layout.addStretch()

        self.weight_spin.valueChanged.connect(lambda _v: self._update_hints())
        self.unit_combo.currentIndexChanged.connect(lambda _i: self._update_hints())
        self.cost_spin.valueChanged.connect(lambda _v: self._update_hints())
        self.price_spin.valueChanged.connect(lambda _v: self._update_hints())
        return outer

    # ================================================================== dữ liệu
    def refresh(self) -> None:
        self._load_categories()
        self.load_products()
        if self.current_id is None and not self.code_edit.text():
            self.new_product()

    def _load_categories(self) -> None:
        categories = self.ctx.products.list_categories()
        for combo, first in ((self.category_filter, ("Tất cả danh mục", None)), (self.category_combo, None)):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            if first:
                combo.addItem(*first)
            for category in categories:
                combo.addItem(category.category_name, category.category_id)
            combo.setCurrentIndex(max(combo.findData(current), 0))
            combo.blockSignals(False)

    def load_products(self) -> None:
        products = self.ctx.products.search(self.search.text(), self.category_filter.currentData(),
                                            self.status_filter.currentData())
        threshold = self.ctx.settings.low_stock_threshold
        loader = ImageLoader.instance()
        rows = []
        for p in products:
            level = p.stock_level(threshold)
            stock_color = {"out": "danger", "low": "warning", "ok": None}[level]
            rows.append([
                make_item(p.product_code, data=p.product_id),
                make_item(p.product_name, bold=True, icon=QIcon(loader.pixmap(p.image_path, 36, 36, 8)),
                          tooltip=p.description or p.product_name),
                make_item(p.sku),
                make_item(p.category_name),
                make_item(p.material),
                make_item(format_weight(p.weight, p.weight_unit), sort=p.weight_in_grams,
                          tooltip=format_weight(p.weight, p.weight_unit, with_grams=True)),
                make_item(format_money(p.cost_price), align=ALIGN_RIGHT, sort=p.cost_price),
                make_item(format_money(p.selling_price), align=ALIGN_RIGHT, sort=p.selling_price, bold=True),
                make_item(str(p.stock_quantity), align=ALIGN_RIGHT, sort=p.stock_quantity, color=stock_color,
                          bold=level != "ok"),
                make_item(p.status_label, color="teal" if p.is_active else "text_faint"),
            ])
        fill_table(self.table, rows)
        active = sum(1 for p in products if p.is_active)
        self.count_label.setText(f"Hiển thị {len(products)} sản phẩm ({active} đang kinh doanh). "
                                 "Sản phẩm đã bán không thể xóa – hãy chuyển sang \"Ngừng kinh doanh\".")
        if self.current_id is not None:
            self.table.blockSignals(True)
            select_by_id(self.table, self.current_id)
            self.table.blockSignals(False)

    def _on_selection(self) -> None:
        product_id = selected_id(self.table)
        if product_id is None:
            return
        try:
            product = self.ctx.products.get(product_id)
        except Exception as exc:  # noqa: BLE001
            show_warning(self, "Không tìm thấy", str(exc))
            return
        self._fill_form(product)

    def _fill_form(self, product: Product) -> None:
        self.current_id = product.product_id
        self.form_title.setText("Cập nhật sản phẩm")
        self.form_hint.setText(f"Đang sửa: {product.product_name} (ID {product.product_id}). "
                               f"Cập nhật lần cuối: {product.updated_at}")
        self.code_edit.setText(product.product_code)
        self.sku_edit.setText(product.sku)
        self.name_edit.setText(product.product_name)
        self.category_combo.setCurrentIndex(max(self.category_combo.findData(product.category_id), 0))
        self.material_combo.setCurrentText(product.material)
        self.weight_spin.setValue(product.weight)
        self.unit_combo.setCurrentIndex(max(self.unit_combo.findData(product.weight_unit), 0))
        self.cost_spin.setValue(product.cost_price)
        self.price_spin.setValue(product.selling_price)
        self.stock_spin.setValue(product.stock_quantity)
        self.stock_spin.setEnabled(False)
        self.stock_hint.setText("Tồn kho chỉ thay đổi qua \"Điều chỉnh kho\" hoặc màn hình Quản lý kho hàng "
                                "để lưu lịch sử thay đổi.")
        self.active_check.setChecked(product.is_active)
        self.description_edit.setPlainText(product.description)
        self._set_image_path(product.image_path)
        self.toggle_button.setText("Ngừng kinh doanh" if product.is_active else "Mở bán lại")
        for button in (self.toggle_button, self.stock_button, self.delete_button):
            button.setEnabled(True)
        self._update_hints()

    @safe_slot
    def new_product(self) -> None:
        self.current_id = None
        self.table.clearSelection()
        self.form_title.setText("Thêm sản phẩm mới")
        self.form_hint.setText("Nhập thông tin và nhấn \"Lưu sản phẩm\". Các trường có dấu * là bắt buộc.")
        self.code_edit.setText(self.ctx.products.suggest_code())
        for widget in (self.sku_edit, self.name_edit):
            widget.clear()
        self.material_combo.setCurrentIndex(0)
        self.weight_spin.setValue(1)
        self.unit_combo.setCurrentIndex(0)
        self.cost_spin.setValue(0)
        self.price_spin.setValue(0)
        self.stock_spin.setEnabled(True)
        self.stock_spin.setValue(0)
        self.stock_hint.setText("Số lượng ban đầu được ghi thành phiếu \"Nhập kho\" trong lịch sử kho.")
        self.active_check.setChecked(True)
        self.description_edit.clear()
        self._set_image_path("")
        for button in (self.toggle_button, self.stock_button, self.delete_button):
            button.setEnabled(False)
        self._update_hints()
        self.sku_edit.setFocus()

    def _form_product(self) -> Product:
        return Product(
            product_id=self.current_id,
            product_code=self.code_edit.text().strip(),
            sku=self.sku_edit.text().strip(),
            product_name=self.name_edit.text(),
            category_id=self.category_combo.currentData(),
            material=self.material_combo.currentText(),
            weight=self.weight_spin.value(),
            weight_unit=self.unit_combo.currentData(),
            cost_price=self.cost_spin.int_value(),
            selling_price=self.price_spin.int_value(),
            stock_quantity=self.stock_spin.value(),
            image_path=self.image_edit.text().strip(),
            description=self.description_edit.toPlainText(),
            is_active=self.active_check.isChecked(),
        )

    def _update_hints(self) -> None:
        unit = self.unit_combo.currentData() or "gram"
        weight = self.weight_spin.value()
        self.weight_hint.setText(f"Quy đổi: {format_decimal(weight)} {unit} ≈ {format_decimal(to_grams(weight, unit), 3)} "
                                 "gram  (1 lượng = 10 chỉ = 37,5 g)")
        cost, price = self.cost_spin.int_value(), self.price_spin.int_value()
        if price > 0:
            margin = price - cost
            percent = margin / price * 100
            self.margin_hint.setText(f"Lãi gộp dự kiến: {format_money(margin)} ({format_decimal(percent, 1)}% giá bán)")
        else:
            self.margin_hint.setText("Giá bán phải lớn hơn 0.")

    # ================================================================== ảnh
    def _set_image_path(self, path: str) -> None:
        path = (path or "").strip()
        self.image_edit.setText(path)
        ImageLoader.instance().forget(path)
        width = max(self.image_preview.width() - 4, 300)
        self.image_preview.setPixmap(ImageLoader.instance().pixmap(path, width, 186, 12))
        ok, message = check_image_source(path)
        self.image_status.setObjectName("Hint" if ok else "ErrorHint")
        self.image_status.setText(message + ("" if ok else " – sẽ hiển thị ảnh mặc định."))
        self.image_status.style().unpolish(self.image_status)
        self.image_status.style().polish(self.image_status)

    def _on_image_ready(self, source: str) -> None:
        if source == self.image_edit.text().strip():
            self._set_image_path(source)

    @safe_slot
    def choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh sản phẩm", "", SUPPORTED_FILTER)
        if not path:
            return
        relative = import_local_image(path, self.sku_edit.text() or self.name_edit.text())
        self._set_image_path(relative)
        self.notify(f"Đã sao chép ảnh vào {relative}")

    @safe_slot
    def image_from_url(self) -> None:
        current = self.image_edit.text() if is_url(self.image_edit.text()) else ""
        url, ok = ask_text(self, "Ảnh từ Internet", "Nhập URL ảnh (http:// hoặc https://):", current)
        url = url.strip()
        if not ok or not url:
            return
        if not is_url(url):
            show_warning(self, "URL không hợp lệ", "URL ảnh phải bắt đầu bằng http:// hoặc https://")
            return
        self.image_edit.setText(url)
        self.image_status.setText("Đang tải ảnh từ Internet...")
        run_in_background(download_image, url, on_success=self._on_url_downloaded, on_error=self._on_url_failed)

    def _on_url_downloaded(self, _path) -> None:
        self._set_image_path(self.image_edit.text())
        self.notify("Đã tải ảnh từ URL và lưu vào bộ nhớ đệm.")

    def _on_url_failed(self, message: str) -> None:
        self._set_image_path(self.image_edit.text())
        show_warning(self, "Không tải được ảnh",
                     f"{message}\n\nURL vẫn được giữ lại; khi không có mạng, phần mềm sẽ hiển thị ảnh mặc định.")

    # ================================================================== thao tác
    @safe_slot
    def add_category(self) -> None:
        name, ok = ask_text(self, "Thêm danh mục", "Tên danh mục trang sức mới:")
        if not ok or not name.strip():
            return
        category_id = self.ctx.products.add_category(name)
        self._load_categories()
        self.category_combo.setCurrentIndex(max(self.category_combo.findData(category_id), 0))
        self.notify(f"Đã thêm danh mục \"{name.strip()}\".")

    @safe_slot
    def save_product(self) -> None:
        product = self._form_product()
        ok, message = check_image_source(product.image_path)
        if not ok and not ask_confirm(self, "Ảnh không hợp lệ",
                                      f"{message}\n\nVẫn lưu sản phẩm (sẽ hiển thị ảnh mặc định)?", "Vẫn lưu"):
            return
        if product.selling_price < product.cost_price and not ask_confirm(
                self, "Giá bán thấp hơn giá nhập", "Giá bán đang thấp hơn giá nhập. Bạn có chắc muốn lưu?", "Lưu"):
            return
        if self.current_id is None:
            new_id = self.ctx.products.create(product, initial_stock=product.stock_quantity)
            self.current_id = new_id
            self.notify(f"Đã thêm sản phẩm \"{product.product_name}\" vào CSDL (ID {new_id}).")
            show_info(self, "Thêm sản phẩm thành công", f"Đã lưu sản phẩm \"{product.product_name}\" vào SQLite.")
        else:
            self.ctx.products.update(product)
            self.notify(f"Đã cập nhật sản phẩm \"{product.product_name}\".")
            show_info(self, "Cập nhật thành công", f"Đã lưu thay đổi của \"{product.product_name}\".")
        self.load_products()
        self._fill_form(self.ctx.products.get(self.current_id))

    @safe_slot
    def toggle_active(self) -> None:
        if self.current_id is None:
            return
        product = self.ctx.products.get(self.current_id)
        target = not product.is_active
        action = "mở bán lại" if target else "ngừng kinh doanh"
        if not ask_confirm(self, "Đổi trạng thái kinh doanh",
                           f"Xác nhận {action} sản phẩm \"{product.product_name}\"?\n"
                           "Sản phẩm ngừng kinh doanh sẽ không hiển thị ở màn hình Bán hàng nhưng vẫn giữ "
                           "nguyên trong các hóa đơn cũ."):
            return
        self.ctx.products.set_active(product.product_id, target)
        self.notify(f"Đã {action} sản phẩm \"{product.product_name}\".")
        self.load_products()
        self._fill_form(self.ctx.products.get(product.product_id))

    @safe_slot
    def adjust_stock(self) -> None:
        if self.current_id is None:
            return
        dialog = StockDialog(self.ctx, self.ctx.products.get(self.current_id), "adjust", self)
        if dialog.exec():
            self.notify(f"Đã điều chỉnh tồn kho, tồn mới: {dialog.new_stock}.")
            self.load_products()
            self._fill_form(self.ctx.products.get(self.current_id))

    @safe_slot
    def delete_product(self) -> None:
        if self.current_id is None:
            return
        product = self.ctx.products.get(self.current_id)
        if not ask_confirm(self, "Xóa sản phẩm",
                           f"Bạn có chắc muốn xóa vĩnh viễn sản phẩm \"{product.product_name}\" ({product.sku})?",
                           "Xóa", danger=True):
            return
        try:
            self.ctx.products.delete(product.product_id)
        except ProductInUseError as exc:
            if product.is_active and ask_confirm(
                    self, "Không thể xóa sản phẩm đã bán",
                    f"{exc.message}\n\nĐể bảo toàn lịch sử hóa đơn, bạn có muốn chuyển sản phẩm sang "
                    "\"Ngừng kinh doanh\" không?", "Ngừng kinh doanh"):
                self.ctx.products.set_active(product.product_id, False)
                self.notify(f"Đã chuyển \"{product.product_name}\" sang Ngừng kinh doanh.")
                self.load_products()
                self._fill_form(self.ctx.products.get(product.product_id))
            elif not product.is_active:
                show_info(self, "Không thể xóa", f"{exc.message}\nSản phẩm đã ở trạng thái Ngừng kinh doanh.")
            return
        self.notify(f"Đã xóa sản phẩm \"{product.product_name}\".")
        self.current_id = None
        self.load_products()
        self.new_product()
