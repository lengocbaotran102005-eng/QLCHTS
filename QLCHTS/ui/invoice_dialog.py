"""Hộp thoại "Hóa đơn thanh toán": xem trước, in hóa đơn và xuất PDF ngay trong ứng dụng desktop."""
import re

from PySide6.QtCore import QSize, QStandardPaths
from PySide6.QtGui import QGuiApplication
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewWidget
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QToolButton, QVBoxLayout

from printing.invoice_printer import InvoicePrinter, configure_printer, create_printer
from ui.widgets import BadgeLabel, handle_exception, make_button, safe_slot, show_info, theme
from utils.formatters import format_datetime, format_money


def default_pdf_name(invoice_code: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", invoice_code) + ".pdf"


def export_invoice_pdf(parent, ctx, invoice_id: int) -> None:
    """Hỏi vị trí lưu rồi xuất PDF hóa đơn (dữ liệu đọc lại từ CSDL)."""
    invoice, details = ctx.pos.get_invoice(invoice_id)
    folder = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    path, _ = QFileDialog.getSaveFileName(parent, "Xuất hóa đơn ra PDF", f"{folder}/{default_pdf_name(invoice.invoice_code)}",
                                          "Tệp PDF (*.pdf)")
    if not path:
        return
    saved = InvoicePrinter(invoice, details, ctx.settings.all()).export_pdf(path)
    ctx.notify(f"Đã xuất hóa đơn {invoice.invoice_code} ra {saved}")
    show_info(parent, "Xuất PDF thành công", f"Đã lưu hóa đơn {invoice.invoice_code} tại:\n{saved}")


class InvoiceDialog(QDialog):
    def __init__(self, ctx, invoice_id: int, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.invoice_id = invoice_id
        self.invoice, self.details = ctx.pos.get_invoice(invoice_id)
        self.renderer = InvoicePrinter(self.invoice, self.details, ctx.settings.all())
        self._render_error_shown = False

        self.setWindowTitle(f"Hóa đơn thanh toán – {self.invoice.invoice_code}")
        self.setModal(True)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(980, screen.width() - 80), min(920, screen.height() - 60))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(f"Hóa đơn {self.invoice.invoice_code}")
        title.setObjectName("CardTitle")
        subtitle = QLabel(f"{format_datetime(self.invoice.created_at)}  •  {self.invoice.customer_name}  •  "
                          f"Tổng thanh toán: {format_money(self.invoice.total_amount)}")
        subtitle.setObjectName("CardSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)
        status = BadgeLabel(self.invoice.status_label, "ok" if self.invoice.is_paid else "out")
        top.addWidget(status)
        layout.addLayout(top)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        for icon, tip, handler in (("zoom-out", "Thu nhỏ", self._zoom_out), ("zoom-in", "Phóng to", self._zoom_in),
                                   ("fit", "Vừa chiều rộng", self._fit_width)):
            button = QToolButton()
            button.setToolTip(tip)
            button.setIconSize(QSize(20, 20))
            theme().bind_icon(button, icon, "text")
            button.clicked.connect(handler)
            toolbar.addWidget(button)
        self.page_label = QLabel()
        self.page_label.setObjectName("MutedText")
        toolbar.addWidget(self.page_label)
        toolbar.addStretch()
        self.print_button = make_button("In hóa đơn", "printer", "teal")
        self.print_button.clicked.connect(self.print_invoice)
        self.pdf_button = make_button("Xuất PDF", "pdf", "primary")
        self.pdf_button.clicked.connect(self.export_pdf)
        close_button = make_button("Đóng", "close", "ghost")
        close_button.clicked.connect(self.accept)
        toolbar.addWidget(self.print_button)
        toolbar.addWidget(self.pdf_button)
        toolbar.addWidget(close_button)
        layout.addLayout(toolbar)

        # Xem trước đúng bố cục khi in (Qt Print Support)
        self.preview_printer = create_printer(self.invoice.invoice_code)
        self.preview = QPrintPreviewWidget(self.preview_printer, self)
        self.preview.paintRequested.connect(self._paint_preview)
        self.preview.previewChanged.connect(self._update_page_label)
        layout.addWidget(self.preview, 1)
        self.preview.fitToWidth()

    # ------------------------------------------------------------------ xem trước
    def _paint_preview(self, printer: QPrinter) -> None:
        try:
            self.renderer.render(printer)
        except Exception as exc:  # noqa: BLE001
            if not self._render_error_shown:
                self._render_error_shown = True
                handle_exception(self, exc)

    def _update_page_label(self) -> None:
        self.page_label.setText(f"   {self.preview.pageCount()} trang  •  Khổ A4")

    def _zoom_in(self) -> None:
        self.preview.zoomIn(1.15)

    def _zoom_out(self) -> None:
        self.preview.zoomOut(1.15)

    def _fit_width(self) -> None:
        self.preview.fitToWidth()

    # ------------------------------------------------------------------ in / PDF
    @safe_slot
    def print_invoice(self) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        configure_printer(printer, self.invoice.invoice_code)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("In hóa đơn")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.renderer.render(printer)
        self.ctx.notify(f"Đã gửi hóa đơn {self.invoice.invoice_code} tới máy in.")

    @safe_slot
    def export_pdf(self) -> None:
        export_invoice_pdf(self, self.ctx, self.invoice_id)


def open_invoice(parent, ctx, invoice_id: int) -> None:
    """Mở hộp thoại hóa đơn; lỗi đọc CSDL được hiển thị thay vì làm dừng chương trình."""
    try:
        InvoiceDialog(ctx, invoice_id, parent).exec()
    except Exception as exc:  # noqa: BLE001
        handle_exception(parent, exc)
