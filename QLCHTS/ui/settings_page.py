"""Cài đặt hệ thống: thông tin cửa hàng, thuế & hóa đơn, nhân viên, giao diện và dữ liệu."""
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QRadioButton,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config
from database import TABLE_NAMES
from models.customer import Employee
from ui.widgets import (
    ALIGN_RIGHT,
    BasePage,
    Card,
    field_label,
    fill_table,
    hint_label,
    make_button,
    make_combo,
    make_double_spin,
    make_item,
    make_spin,
    safe_slot,
    select_by_id,
    selected_id,
    setup_table,
    show_info,
    theme,
)
from utils.formatters import format_datetime, format_number, now_str

TABLE_DESCRIPTIONS = {
    "categories": "Danh mục trang sức",
    "products": "Sản phẩm",
    "customers": "Khách hàng",
    "employees": "Nhân viên",
    "invoices": "Hóa đơn",
    "invoice_details": "Chi tiết hóa đơn",
    "inventory_transactions": "Lịch sử kho",
    "settings": "Cài đặt hệ thống",
}


class SettingsPage(BasePage):
    title = "Cài đặt hệ thống"
    subtitle = "Thông tin cửa hàng in trên hóa đơn, thuế suất VAT, nhân viên, giao diện và sao lưu dữ liệu"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._store_tab(), "Thông tin cửa hàng")
        self.tabs.addTab(self._invoice_tab(), "Thuế && hóa đơn")
        self.tabs.addTab(self._employee_tab(), "Nhân viên")
        self.tabs.addTab(self._system_tab(), "Giao diện && dữ liệu")
        self.root.addWidget(self.tabs, 1)
        self.current_employee: int | None = None

    # ------------------------------------------------------------------ tab: cửa hàng
    def _line(self, placeholder: str = "") -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setMinimumHeight(36)
        return edit

    def _store_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        card = Card("Thông tin hiển thị trên hóa đơn", "Do người quản lý cấu hình – lưu trong bảng settings")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)
        self.store_name = self._line("BẢO TRÂN JEWELRY")
        self.store_full_name = self._line("Cửa Hàng Trang Sức & Vàng Bạc Đá Quý Bảo Trân")
        self.store_address = self._line("Số nhà, đường, phường, quận, tỉnh/thành")
        self.store_phone = self._line("Số điện thoại / hotline")
        self.store_email = self._line("Email liên hệ (không bắt buộc)")
        self.store_tax_code = self._line("Mã số thuế (không bắt buộc)")
        form.addRow(field_label("Tên cửa hàng *"), self.store_name)
        form.addRow(field_label("Tên đầy đủ"), self.store_full_name)
        form.addRow(field_label("Địa chỉ"), self.store_address)
        form.addRow(field_label("Điện thoại"), self.store_phone)
        form.addRow(field_label("Email"), self.store_email)
        form.addRow(field_label("Mã số thuế"), self.store_tax_code)
        card.add_layout(form)
        save = make_button("Lưu thông tin cửa hàng", "save", "primary")
        save.clicked.connect(self.save_store)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(save)
        card.add_layout(row)
        layout.addWidget(card)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------ tab: thuế & hóa đơn
    def _invoice_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        card = Card("Thuế, tồn kho và nội dung hóa đơn")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)
        self.vat_spin = make_double_spin()
        self.vat_spin.setRange(0, 100)
        self.vat_spin.setDecimals(1)
        self.vat_spin.setSuffix(" %")
        self.vat_spin.setMinimumHeight(36)
        self.vat_spin.setMaximumWidth(180)
        self.threshold_spin = make_spin()
        self.threshold_spin.setRange(0, 100000)
        self.threshold_spin.setMinimumHeight(36)
        self.threshold_spin.setMaximumWidth(180)
        self.warranty_edit = QPlainTextEdit()
        self.warranty_edit.setFixedHeight(80)
        self.buyback_edit = QPlainTextEdit()
        self.buyback_edit.setFixedHeight(80)
        self.thanks_edit = self._line("Lời cảm ơn in cuối hóa đơn")
        form.addRow(field_label("Thuế suất VAT mặc định"), self.vat_spin)
        form.addRow("", hint_label("Thuế suất do cửa hàng cấu hình cho phần mềm và được in rõ trên từng hóa đơn. "
                                   "Phần mềm không khẳng định mọi loại trang sức đều chịu cùng một mức thuế suất "
                                   "pháp lý – người quản lý cần đối chiếu quy định hiện hành."))
        form.addRow(field_label("Ngưỡng tồn kho thấp"), self.threshold_spin)
        form.addRow(field_label("Thông tin bảo hành"), self.warranty_edit)
        form.addRow(field_label("Chính sách thu mua / đổi trả"), self.buyback_edit)
        form.addRow(field_label("Lời cảm ơn"), self.thanks_edit)
        card.add_layout(form)
        save = make_button("Lưu cài đặt hóa đơn", "save", "primary")
        save.clicked.connect(self.save_invoice_settings)
        row = QHBoxLayout()
        row.addWidget(hint_label(config.INVOICE_LEGAL_NOTE))
        row.addWidget(save)
        card.add_layout(row)
        layout.addWidget(card)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------ tab: nhân viên
    def _employee_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        list_card = Card("Danh sách nhân viên", "Nhân viên đang làm việc sẽ hiển thị ở màn hình Bán hàng")
        self.employee_table = QTableWidget()
        setup_table(self.employee_table, ["Mã NV", "Họ tên", "Chức vụ", "Điện thoại", "Trạng thái"], stretch=1)
        self.employee_table.itemSelectionChanged.connect(self._on_employee_selected)
        list_card.add(self.employee_table, 1)
        layout.addWidget(list_card, 3)

        form_card = Card("Thông tin nhân viên")
        form_card.setMaximumWidth(420)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.employee_name = self._line("Họ tên nhân viên")
        self.employee_role = make_combo([(r, r) for r in ("Nhân viên bán hàng", "Thu ngân", "Quản lý cửa hàng",
                                                          "Thủ kho", "Kế toán")], editable=True)
        self.employee_phone = self._line("10 chữ số")
        self.employee_active = QCheckBox("Đang làm việc")
        self.employee_active.setChecked(True)
        form.addRow(field_label("Họ tên *"), self.employee_name)
        form.addRow(field_label("Chức vụ *"), self.employee_role)
        form.addRow(field_label("Điện thoại"), self.employee_phone)
        form.addRow(field_label("Trạng thái"), self.employee_active)
        form_card.add_layout(form)
        buttons = QHBoxLayout()
        new = make_button("Thêm mới", "plus", "ghost")
        new.clicked.connect(self.new_employee)
        save = make_button("Lưu nhân viên", "save", "primary")
        save.clicked.connect(self.save_employee)
        buttons.addWidget(new)
        buttons.addStretch()
        buttons.addWidget(save)
        form_card.add_layout(buttons)
        form_card.add(hint_label("Nhân viên đã lập hóa đơn không bị xóa mà chuyển sang \"Nghỉ việc\" để giữ lịch sử."))
        form_card.layout_.addStretch()
        layout.addWidget(form_card, 2)
        return page

    # ------------------------------------------------------------------ tab: hệ thống
    def _system_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        left = QVBoxLayout()
        appearance = Card("Giao diện", "Chế độ được lưu lại cho lần mở sau")
        self.dark_radio = QRadioButton("Giao diện tối (Dark Mode) – đen than & vàng Champagne")
        self.light_radio = QRadioButton("Giao diện sáng (Light Mode) – ngà & vàng đồng")
        self.dark_radio.toggled.connect(lambda checked: checked and self._set_theme("dark"))
        self.light_radio.toggled.connect(lambda checked: checked and self._set_theme("light"))
        appearance.add(self.dark_radio)
        appearance.add(self.light_radio)
        left.addWidget(appearance)

        about = Card("Thông tin phần mềm")
        about.add(hint_label(f"{config.APP_TITLE}\nPhiên bản {config.APP_VERSION} – Python, PySide6, SQLite, "
                             "Matplotlib, Qt Print Support, Pillow.\n\n" + config.REVENUE_RULE, "MutedText"))
        left.addWidget(about)
        left.addStretch()
        layout.addLayout(left, 2)

        data_card = Card("Cơ sở dữ liệu SQLite", "Kiểm tra số bản ghi thực tế trong từng bảng")
        self.db_path_label = hint_label("", "MutedText")
        data_card.add(self.db_path_label)
        self.table_counts = QTableWidget()
        setup_table(self.table_counts, ["Bảng", "Mô tả", "Số bản ghi"], stretch=1, sortable=False)
        self.table_counts.setMinimumHeight(330)
        data_card.add(self.table_counts, 1)
        self.integrity_label = hint_label("")
        data_card.add(self.integrity_label)
        buttons = QHBoxLayout()
        check = make_button("Kiểm tra toàn vẹn", "shield")
        check.clicked.connect(self.check_integrity)
        backup = make_button("Sao lưu CSDL...", "database", "primary")
        backup.clicked.connect(self.backup_database)
        open_folder = make_button("Mở thư mục dữ liệu", "folder", "ghost")
        open_folder.clicked.connect(self.open_data_folder)
        buttons.addWidget(check)
        buttons.addWidget(open_folder)
        buttons.addStretch()
        buttons.addWidget(backup)
        data_card.add_layout(buttons)
        layout.addWidget(data_card, 3)
        return page

    # ------------------------------------------------------------------ nạp dữ liệu
    def refresh(self) -> None:
        values = self.ctx.settings.all()
        self.store_name.setText(values["store_name"])
        self.store_full_name.setText(values["store_full_name"])
        self.store_address.setText(values["store_address"])
        self.store_phone.setText(values["store_phone"])
        self.store_email.setText(values["store_email"])
        self.store_tax_code.setText(values["store_tax_code"])
        self.vat_spin.setValue(self.ctx.settings.vat_rate)
        self.threshold_spin.setValue(self.ctx.settings.low_stock_threshold)
        self.warranty_edit.setPlainText(values["warranty_info"])
        self.buyback_edit.setPlainText(values["buyback_policy"])
        self.thanks_edit.setText(values["thank_you_message"])
        for radio, mode in ((self.dark_radio, "dark"), (self.light_radio, "light")):
            radio.blockSignals(True)
            radio.setChecked(theme().mode == mode)
            radio.blockSignals(False)
        self._load_employees()
        self._load_db_info()

    def _load_employees(self) -> None:
        rows = []
        for e in self.ctx.settings.employees():
            rows.append([
                make_item(e.employee_code, data=e.employee_id),
                make_item(e.employee_name, bold=True),
                make_item(e.role),
                make_item(e.phone or "—"),
                make_item("Đang làm việc" if e.is_active else "Nghỉ việc", color="teal" if e.is_active else "text_faint"),
            ])
        self.employee_table.blockSignals(True)
        fill_table(self.employee_table, rows)
        select_by_id(self.employee_table, self.current_employee)
        self.employee_table.blockSignals(False)

    def _load_db_info(self) -> None:
        path = self.ctx.db.db_path
        size = path.stat().st_size / 1024 if path.exists() else 0
        self.db_path_label.setText(f"Tệp CSDL: {path}\nDung lượng: {format_number(size)} KB  •  "
                                   f"Cập nhật lúc {format_datetime(now_str())}")
        counts = self.ctx.db.table_counts()
        fill_table(self.table_counts, [[
            make_item(table, bold=True),
            make_item(TABLE_DESCRIPTIONS.get(table, "")),
            make_item(format_number(counts[table]), align=ALIGN_RIGHT),
        ] for table in TABLE_NAMES])

    # ------------------------------------------------------------------ thao tác
    @safe_slot
    def save_store(self) -> None:
        self.ctx.settings.save({
            "store_name": self.store_name.text(),
            "store_full_name": self.store_full_name.text(),
            "store_address": self.store_address.text(),
            "store_phone": self.store_phone.text(),
            "store_email": self.store_email.text(),
            "store_tax_code": self.store_tax_code.text(),
        })
        self.notify("Đã lưu thông tin cửa hàng.")
        show_info(self, "Đã lưu", "Thông tin cửa hàng đã được cập nhật và sẽ hiển thị trên các hóa đơn.")

    @safe_slot
    def save_invoice_settings(self) -> None:
        self.ctx.settings.save({
            "vat_rate": self.vat_spin.value(),
            "low_stock_threshold": self.threshold_spin.value(),
            "warranty_info": self.warranty_edit.toPlainText(),
            "buyback_policy": self.buyback_edit.toPlainText(),
            "thank_you_message": self.thanks_edit.text(),
        })
        self.notify("Đã lưu cài đặt thuế & hóa đơn.")
        show_info(self, "Đã lưu", "Cài đặt thuế suất, ngưỡng tồn kho và nội dung hóa đơn đã được cập nhật.\n"
                                  "Thuế suất mới áp dụng cho các hóa đơn lập sau thời điểm này.")

    def _on_employee_selected(self) -> None:
        employee_id = selected_id(self.employee_table)
        if employee_id is None:
            return
        employee = next((e for e in self.ctx.settings.employees() if e.employee_id == employee_id), None)
        if employee is None:
            return
        self.current_employee = employee.employee_id
        self.employee_name.setText(employee.employee_name)
        self.employee_role.setCurrentText(employee.role)
        self.employee_phone.setText(employee.phone)
        self.employee_active.setChecked(employee.is_active)

    def new_employee(self) -> None:
        self.current_employee = None
        self.employee_table.clearSelection()
        self.employee_name.clear()
        self.employee_role.setCurrentIndex(0)
        self.employee_phone.clear()
        self.employee_active.setChecked(True)
        self.employee_name.setFocus()

    @safe_slot
    def save_employee(self) -> None:
        employee = Employee(employee_id=self.current_employee, employee_name=self.employee_name.text(),
                            role=self.employee_role.currentText(), phone=self.employee_phone.text(),
                            is_active=self.employee_active.isChecked())
        self.current_employee = self.ctx.settings.save_employee(employee)
        self._load_employees()
        self._load_db_info()
        self.notify("Đã lưu thông tin nhân viên.")

    def _set_theme(self, mode: str) -> None:
        if theme().mode != mode:
            theme().apply(mode)
            self.ctx.settings.set_theme(mode)

    @safe_slot
    def check_integrity(self) -> None:
        result, fk_errors = self.ctx.db.integrity_check()
        ok = result == "ok" and fk_errors == 0
        self.integrity_label.setObjectName("SuccessHint" if ok else "ErrorHint")
        self.integrity_label.style().unpolish(self.integrity_label)
        self.integrity_label.style().polish(self.integrity_label)
        self.integrity_label.setText(f"PRAGMA integrity_check: {result}  •  Lỗi khóa ngoại: {fk_errors}")
        self._load_db_info()

    @safe_slot
    def backup_database(self) -> None:
        folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        default = f"{folder}/baotran_jewelry_backup_{now_str()[:10].replace('-', '')}.db"
        path, _ = QFileDialog.getSaveFileName(self, "Sao lưu cơ sở dữ liệu", default, "Tệp SQLite (*.db)")
        if not path:
            return
        self.ctx.db.backup_to(Path(path))
        self.notify(f"Đã sao lưu CSDL tới {path}")
        show_info(self, "Sao lưu thành công", f"Đã sao lưu toàn bộ dữ liệu tới:\n{path}")

    def open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.db.db_path.parent)))
