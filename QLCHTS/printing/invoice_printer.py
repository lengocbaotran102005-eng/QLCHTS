"""Vẽ hóa đơn bán hàng bằng QPainter lên QPrinter (dùng chung cho xem trước, in và xuất PDF).

Bố cục khổ A4 dọc, tự động sang trang khi danh sách sản phẩm dài (lặp lại tiêu đề
bảng), đánh số "Trang x/y". Mọi dữ liệu lấy từ hóa đơn đã lưu trong CSDL.
"""
from pathlib import Path

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPageLayout, QPageSize, QPainter, QPen
from PySide6.QtPrintSupport import QPrinter

import config
from errors import PrintError
from models.invoice import Invoice, InvoiceDetail
from utils.formatters import (
    format_datetime,
    format_decimal,
    format_money,
    format_number,
    format_percent,
    money_in_words,
    to_grams,
)

INK = QColor("#1F1D1A")
MUTED = QColor("#6B655C")
GOLD = QColor("#9C7430")
LINE = QColor("#DCCDB1")
SOFT = QColor("#FAF6EE")
HEADER_BG = QColor("#EFE3CC")
DANGER = QColor("#C0392B")

LEFT = Qt.AlignmentFlag.AlignLeft.value
RIGHT = Qt.AlignmentFlag.AlignRight.value
HCENTER = Qt.AlignmentFlag.AlignHCenter.value
TOP = Qt.AlignmentFlag.AlignTop.value
VCENTER = Qt.AlignmentFlag.AlignVCenter.value
WRAP = Qt.TextFlag.TextWordWrap.value


def _pick_family(candidates: list[str]) -> str:
    families = set(QFontDatabase.families())
    return next((name for name in candidates if name in families), candidates[-1])


def configure_printer(printer: QPrinter, title: str) -> None:
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    printer.setPageOrientation(QPageLayout.Orientation.Portrait)
    printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
    printer.setDocName(title)
    printer.setCreator(config.APP_NAME)


def create_printer(title: str) -> QPrinter:
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    configure_printer(printer, title)
    return printer


class InvoicePrinter:
    # (tiêu đề cột, độ rộng mm, căn lề) – tổng 186 mm = A4 (210) trừ lề 2 × 12 mm
    COLUMNS = [
        ("STT", 9, HCENTER),
        ("Sản phẩm / Mã SKU", 57, LEFT),
        ("Chất liệu", 31, LEFT),
        ("Trọng lượng", 24, HCENTER),
        ("SL", 10, HCENTER),
        ("Đơn giá (₫)", 27, RIGHT),
        ("Thành tiền (₫)", 28, RIGHT),
    ]

    def __init__(self, invoice: Invoice, details: list[InvoiceDetail], settings: dict):
        self.invoice = invoice
        self.details = details
        self.settings = settings
        self.sans = _pick_family(["Segoe UI", "Arial", "DejaVu Sans"])
        self.serif = _pick_family(["Palatino Linotype", "Cambria", "Times New Roman", "DejaVu Serif"])

    # ================================================================== API
    def render(self, printer: QPrinter) -> None:
        """Vẽ hóa đơn lên máy in / tệp PDF / màn hình xem trước."""
        painter = QPainter()
        if not painter.begin(printer):
            raise PrintError("Không thể khởi tạo thiết bị in hoặc tệp PDF. Nếu đang xuất PDF, hãy kiểm tra "
                             "tệp không bị mở bởi chương trình khác và thư mục có quyền ghi.")
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            # Lượt 1: chỉ tính bố cục để biết tổng số trang; lượt 2: vẽ thật
            pages = self._layout(painter, printer, draw=False, total_pages=1)
            self._layout(painter, printer, draw=True, total_pages=pages)
        finally:
            painter.end()

    def export_pdf(self, file_path: str | Path) -> Path:
        path = Path(file_path)
        if path.suffix.lower() != ".pdf":
            path = path.with_suffix(".pdf")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PrintError(f"Không thể tạo thư mục lưu PDF: {exc}") from exc
        printer = create_printer(self.invoice.invoice_code)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(path))
        self.render(printer)
        if not path.exists() or path.stat().st_size == 0:
            raise PrintError("Xuất PDF không thành công. Vui lòng chọn thư mục khác hoặc đóng tệp PDF đang mở.")
        return path

    # ================================================================== bố cục
    def _layout(self, painter: QPainter, printer: QPrinter, draw: bool, total_pages: int) -> int:
        self.p = painter
        self.printer = printer
        self.draw = draw
        self.total_pages = total_pages
        self.page = 1
        rect = printer.pageLayout().paintRectPixels(printer.resolution())
        self.mm = printer.resolution() / 25.4
        self.W = float(rect.width())
        self.H = float(rect.height())
        self.bottom = self.H - 11 * self.mm  # chừa chỗ cho chân trang

        self._begin_page()
        y = self._header(0.0)
        y = self._info_box(y)
        y = self._table(y)
        y = self._totals(y)
        y = self._policies(y)
        self._signatures(y)
        self._footer()
        return self.page

    def _begin_page(self) -> None:
        if self.draw and self.invoice.status == config.INVOICE_CANCELLED:
            self.p.save()
            self.p.translate(self.W / 2, self.H / 2)
            self.p.rotate(-30)
            color = QColor(DANGER)
            color.setAlpha(38)
            self.p.setPen(color)
            self.p.setFont(self._font(72, bold=True))
            self.p.drawText(QRectF(-self.W, -60 * self.mm, 2 * self.W, 120 * self.mm), HCENTER | VCENTER, "ĐÃ HỦY")
            self.p.restore()

    def _new_page(self) -> float:
        self._footer()
        if self.draw:
            self.printer.newPage()
        self.page += 1
        self._begin_page()
        h = self._text(QRectF(0, 0, self.W, 8 * self.mm),
                       f"Hóa đơn {self.invoice.invoice_code} (tiếp theo)", self._font(9, bold=True), MUTED)
        return h + 3 * self.mm

    def _ensure_space(self, y: float, needed: float) -> float:
        return self._new_page() if y + needed > self.bottom else y

    # ================================================================== tiện ích vẽ
    def _font(self, size: float, bold: bool = False, italic: bool = False, serif: bool = False) -> QFont:
        font = QFont(self.serif if serif else self.sans)
        font.setPointSizeF(size)
        font.setBold(bold)
        font.setItalic(italic)
        return font

    def _measure(self, width: float, text: str, font: QFont, flags: int = LEFT | TOP | WRAP) -> float:
        self.p.setFont(font)
        return self.p.boundingRect(QRectF(0, 0, width, 10_000), flags, text).height()

    def _text(self, rect: QRectF, text: str, font: QFont, color: QColor = INK,
              flags: int = LEFT | TOP | WRAP) -> float:
        self.p.setFont(font)
        height = self.p.boundingRect(QRectF(rect.x(), rect.y(), rect.width(), 10_000), flags, text).height()
        if self.draw:
            self.p.setPen(color)
            self.p.drawText(QRectF(rect.x(), rect.y(), rect.width(), max(rect.height(), height)), flags, text)
        return height

    def _line(self, x1: float, y1: float, x2: float, y2: float, color: QColor = LINE, width_mm: float = 0.25) -> None:
        if self.draw:
            self.p.setPen(QPen(color, width_mm * self.mm))
            self.p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    def _box(self, rect: QRectF, fill: QColor, border: QColor | None = None, radius_mm: float = 2.0) -> None:
        if self.draw:
            self.p.setPen(QPen(border, 0.25 * self.mm) if border else Qt.PenStyle.NoPen)
            self.p.setBrush(fill)
            self.p.drawRoundedRect(rect, radius_mm * self.mm, radius_mm * self.mm)
            self.p.setBrush(Qt.BrushStyle.NoBrush)

    # ================================================================== các phần của hóa đơn
    def _header(self, y: float) -> float:
        mm, s, inv = self.mm, self.settings, self.invoice
        logo_size = 21 * mm
        if self.draw and config.LOGO_IMAGE.exists():
            logo = QImage(str(config.LOGO_IMAGE))
            if not logo.isNull():
                self.p.drawImage(QRectF(0, y, logo_size, logo_size), logo)
        x = logo_size + 4 * mm
        left_w = self.W * 0.58 - x
        h = self._text(QRectF(x, y, left_w, 0), s.get("store_name", ""), self._font(19, bold=True, serif=True), GOLD)
        h += self._text(QRectF(x, y + h, left_w, 0), s.get("store_full_name", "").upper(), self._font(8.5, bold=True))
        h += 1 * mm
        contact_lines = [f"Địa chỉ: {s.get('store_address', '')}"]
        phone_line = f"Điện thoại: {s.get('store_phone', '')}"
        if s.get("store_email"):
            phone_line += f"   •   Email: {s['store_email']}"
        contact_lines.append(phone_line)
        if s.get("store_tax_code"):
            contact_lines.append(f"Mã số thuế: {s['store_tax_code']}")
        h += self._text(QRectF(x, y + h, left_w, 0), "\n".join(contact_lines), self._font(8), MUTED)

        right_x, right_w = self.W * 0.6, self.W * 0.4
        rh = self._text(QRectF(right_x, y, right_w, 0), "HÓA ĐƠN BÁN HÀNG", self._font(15, bold=True, serif=True),
                        INK, RIGHT | TOP)
        rh += 1 * mm
        rh += self._text(QRectF(right_x, y + rh, right_w, 0), f"Số: {inv.invoice_code}", self._font(10, bold=True),
                         GOLD, RIGHT | TOP)
        rh += self._text(QRectF(right_x, y + rh, right_w, 0), f"Ngày lập: {format_datetime(inv.created_at)}",
                         self._font(8.5), INK, RIGHT | TOP)
        status_color = DANGER if inv.status == config.INVOICE_CANCELLED else QColor("#16806F")
        rh += self._text(QRectF(right_x, y + rh, right_w, 0), f"Trạng thái: {inv.status_label}",
                         self._font(8.5, bold=True), status_color, RIGHT | TOP)

        y += max(h, rh, logo_size) + 3 * mm
        self._line(0, y, self.W, y, GOLD, 0.6)
        self._line(0, y + 0.9 * mm, self.W, y + 0.9 * mm, GOLD, 0.15)
        return y + 4 * mm

    def _info_box(self, y: float) -> float:
        mm, inv = self.mm, self.invoice
        pad = 3 * mm
        col_w = (self.W - 3 * pad) / 2
        customer = inv.customer_name + (f"  (Mã KH: {inv.customer_code})" if inv.customer_code else "")
        left = [("Khách hàng", customer), ("Điện thoại", inv.customer_phone or "—"),
                ("Địa chỉ", inv.customer_address or "—")]
        right = [("Nhân viên bán hàng", inv.employee_name or "—"), ("Phương thức thanh toán", inv.payment_method),
                 ("Ghi chú", inv.note or "—")]
        label_widths = (24 * mm, 40 * mm)

        def row_height(label, value, label_w):
            return max(self._measure(label_w, f"{label}:", self._font(8.5)),
                       self._measure(col_w - label_w, value, self._font(9, bold=(label == "Khách hàng"))),
                       4.6 * mm) + 0.8 * mm

        box_h = max(sum(row_height(lbl, val, label_widths[i]) for lbl, val in rows)
                    for i, rows in enumerate((left, right))) + 2 * pad
        y = self._ensure_space(y, box_h)
        self._box(QRectF(0, y, self.W, box_h), SOFT, LINE)
        for index, rows in enumerate((left, right)):
            x = pad + index * (col_w + pad)
            label_w = label_widths[index]
            yy = y + pad
            for label, value in rows:
                self._text(QRectF(x, yy, label_w, 0), f"{label}:", self._font(8.5), MUTED)
                self._text(QRectF(x + label_w, yy, col_w - label_w, 0), value,
                           self._font(9, bold=(label == "Khách hàng")))
                yy += row_height(label, value, label_w)
        return y + box_h + 5 * mm

    def _table_header(self, y: float) -> float:
        mm = self.mm
        height = 8 * mm
        self._box(QRectF(0, y, self.W, height), HEADER_BG, None, 1.2)
        x = 0.0
        for title, width, align in self.COLUMNS:
            self._text(QRectF(x + 1.5 * mm, y, width * mm - 3 * mm, height), title, self._font(8, bold=True), INK,
                       align | VCENTER)
            x += width * mm
        return y + height

    def _table(self, y: float) -> float:
        mm = self.mm
        y = self._ensure_space(y, 20 * mm)
        y = self._table_header(y)
        pad = 1.8 * mm
        for index, d in enumerate(self.details, start=1):
            widths = [w * mm - 3 * mm for _t, w, _a in self.COLUMNS]
            name_h = self._measure(widths[1], d.product_name, self._font(9, bold=True))
            sku_h = self._measure(widths[1], f"SKU: {d.sku}", self._font(7.5))
            weight_text = f"{format_decimal(d.weight)} {d.weight_unit}"
            if d.weight_unit and d.weight_unit != "gram":
                weight_text += f"\n({format_decimal(to_grams(d.weight, d.weight_unit), 2)} g)"
            cells = [str(index), None, d.material or "—", weight_text, str(d.quantity),
                     format_number(d.unit_price), format_number(d.line_total)]
            heights = [name_h + sku_h]
            for col, text in enumerate(cells):
                if text is not None:
                    heights.append(self._measure(widths[col], text, self._font(8.5)))
            row_h = max(heights) + 2 * pad
            if y + row_h > self.bottom:
                y = self._new_page()
                y = self._table_header(y)
            if index % 2 == 0:
                self._box(QRectF(0, y, self.W, row_h), QColor("#FCFAF5"), None, 0)
            x = 0.0
            for col, (_title, width, align) in enumerate(self.COLUMNS):
                rect = QRectF(x + 1.5 * mm, y + pad, widths[col], row_h - 2 * pad)
                if col == 1:
                    self._text(rect, d.product_name, self._font(9, bold=True))
                    self._text(QRectF(rect.x(), rect.y() + name_h, rect.width(), 0), f"SKU: {d.sku}",
                               self._font(7.5), MUTED)
                else:
                    bold = col == 6
                    self._text(rect, cells[col], self._font(8.5, bold=bold), INK, align | TOP | WRAP)
                x += width * mm
            y += row_h
            self._line(0, y, self.W, y, LINE, 0.2)
        if not self.details:
            self._text(QRectF(0, y + 2 * mm, self.W, 8 * mm), "(Hóa đơn không có dòng sản phẩm)", self._font(9),
                       MUTED, HCENTER | TOP)
            y += 10 * mm
        return y + 4 * mm

    def _totals(self, y: float) -> float:
        mm, inv = self.mm, self.invoice
        rows = [("Tổng tiền hàng", format_money(inv.subtotal), False)]
        if inv.discount_amount > 0:
            label = "Chiết khấu"
            if inv.discount_type == config.DISCOUNT_PERCENT:
                label += f" ({format_percent(inv.discount_value)})"
            rows.append((label, f"− {format_money(inv.discount_amount)}", False))
        else:
            rows.append(("Chiết khấu", format_money(0), False))
        rows.append(("Giá trị tính thuế", format_money(inv.taxable_amount), False))
        rows.append((f"Thuế VAT ({format_percent(inv.vat_rate)})", format_money(inv.vat_amount), False))
        rows.append(("TỔNG THANH TOÁN", format_money(inv.total_amount), True))
        if inv.payment_method == config.PAYMENT_CASH:
            rows.append(("Khách đưa", format_money(inv.amount_received), False))
            rows.append(("Tiền thừa trả khách", format_money(inv.change_amount), False))

        block_w = 92 * mm
        left_w = self.W - block_w - 8 * mm
        row_h = 5.8 * mm
        words = money_in_words(inv.total_amount)
        words_h = self._measure(left_w - 6 * mm, words, self._font(9.5, italic=True))
        needed = max(len(rows) * row_h + 6 * mm, words_h + 26 * mm)
        y = self._ensure_space(y, needed)

        # Bên trái: số tiền bằng chữ + ghi chú thuế suất
        self._box(QRectF(0, y, left_w, needed - 2 * mm), SOFT, LINE)
        yy = y + 3 * mm
        yy += self._text(QRectF(3 * mm, yy, left_w - 6 * mm, 0), "Số tiền bằng chữ:", self._font(8.5, bold=True), MUTED)
        yy += self._text(QRectF(3 * mm, yy, left_w - 6 * mm, 0), words, self._font(9.5, italic=True, bold=True), INK)
        yy += 2 * mm
        self._text(QRectF(3 * mm, yy, left_w - 6 * mm, 0),
                   f"Thuế suất VAT áp dụng theo cấu hình phần mềm: {format_percent(inv.vat_rate)}. "
                   "Tổng thanh toán = Tổng tiền hàng − Chiết khấu + Thuế VAT.",
                   self._font(7.5), MUTED)

        # Bên phải: bảng tổng tiền
        x = self.W - block_w
        yy = y
        for label, value, strong in rows:
            if strong:
                self._line(x, yy + 0.8 * mm, self.W, yy + 0.8 * mm, GOLD, 0.35)
                yy += 1.6 * mm
                font_l, font_v, color = self._font(10, bold=True), self._font(12, bold=True), GOLD
            else:
                font_l, font_v, color = self._font(9), self._font(9, bold=True), INK
            self._text(QRectF(x, yy, block_w * 0.55, row_h), label, font_l, INK if not strong else GOLD,
                       LEFT | VCENTER)
            self._text(QRectF(x + block_w * 0.4, yy, block_w * 0.6, row_h), value, font_v, color, RIGHT | VCENTER)
            yy += row_h + (1.2 * mm if strong else 0)
        return y + needed + 3 * mm

    def _policies(self, y: float) -> float:
        mm, s, inv = self.mm, self.settings, self.invoice
        sections = [("Thông tin bảo hành", s.get("warranty_info", "")),
                    ("Chính sách thu mua / đổi trả", s.get("buyback_policy", ""))]
        if inv.status == config.INVOICE_CANCELLED:
            sections.append(("Thông tin hủy hóa đơn",
                             f"Hủy lúc {format_datetime(inv.cancelled_at)}. Lý do: {inv.cancel_reason or '—'}"))
        sections = [(title, text) for title, text in sections if text.strip()]
        for title, text in sections:
            needed = self._measure(self.W, text, self._font(8.5)) + 7 * mm
            y = self._ensure_space(y, needed)
            color = DANGER if title.startswith("Thông tin hủy") else GOLD
            y += self._text(QRectF(0, y, self.W, 0), title.upper(), self._font(8.5, bold=True), color)
            y += self._text(QRectF(0, y + 0.5 * mm, self.W, 0), text, self._font(8.5), INK) + 3 * mm
        thanks = s.get("thank_you_message", "")
        if thanks:
            y = self._ensure_space(y, 10 * mm)
            y += self._text(QRectF(0, y + 1 * mm, self.W, 0), thanks, self._font(11, italic=True, serif=True), GOLD,
                            HCENTER | TOP | WRAP) + 5 * mm
        return y

    def _signatures(self, y: float) -> float:
        mm, inv = self.mm, self.invoice
        y = self._ensure_space(y, 32 * mm)
        half = self.W / 2
        for i, (title, name) in enumerate((("KHÁCH HÀNG", "" if inv.customer_name == config.WALK_IN_CUSTOMER
                                             else inv.customer_name),
                                            ("NHÂN VIÊN BÁN HÀNG", inv.employee_name))):
            x = i * half
            self._text(QRectF(x, y, half, 0), title, self._font(9, bold=True), INK, HCENTER | TOP)
            self._text(QRectF(x, y + 5 * mm, half, 0), "(Ký, ghi rõ họ tên)", self._font(8, italic=True), MUTED,
                       HCENTER | TOP)
            if name:
                self._text(QRectF(x, y + 24 * mm, half, 0), name, self._font(9, bold=True), INK, HCENTER | TOP)
        return y + 32 * mm

    def _footer(self) -> None:
        if not self.draw:
            return
        mm = self.mm
        y = self.H - 8 * mm
        self._line(0, y, self.W, y, LINE, 0.2)
        self._text(QRectF(0, y + 1.5 * mm, self.W - 25 * mm, 6 * mm), config.INVOICE_LEGAL_NOTE, self._font(7),
                   MUTED, LEFT | TOP | WRAP)
        self._text(QRectF(self.W - 25 * mm, y + 1.5 * mm, 25 * mm, 6 * mm), f"Trang {self.page}/{self.total_pages}",
                   self._font(7.5, bold=True), MUTED, RIGHT | TOP)
