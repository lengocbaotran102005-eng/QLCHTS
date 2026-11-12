# BẢO TRÂN JEWELRY – Phần mềm quản lý cửa hàng trang sức

Đồ án tốt nghiệp: **Xây dựng phần mềm quản lý cửa hàng trang sức Bảo Trân Jewelry bằng Python và cơ sở dữ liệu SQLite.**

Ứng dụng **desktop** viết bằng **Python 3 + PySide6 (Qt)**, lưu dữ liệu trong tệp **SQLite** `baotran_jewelry.db`.
Khi nhấn **Run** trong PyCharm (hoặc chạy `python main.py`), chương trình mở một **cửa sổ ứng dụng trên Windows** –
không dùng web server, không dùng trình duyệt, không dùng HTML/CSS/JavaScript.

---

## 1. Công nghệ sử dụng

| Thành phần | Vai trò | Ghi chú |
|---|---|---|
| Python 3.10 – 3.14 (khuyến nghị **3.12**) | Ngôn ngữ chính | Dự án đã chạy thử trên Python 3.14.7 |
| **PySide6-Essentials** | Giao diện desktop Qt: cửa sổ, bảng, hộp thoại, QSS, SVG icon, **Qt Print Support** (xem trước, in, xuất PDF) | Cài qua `pip` |
| **sqlite3** | Kết nối, truy vấn, transaction với SQLite | **Có sẵn trong Python**, không cần cài |
| **Matplotlib** | Biểu đồ doanh thu nhúng vào cửa sổ PySide6 (`FigureCanvasQTAgg`) | Cài qua `pip` |
| **Pillow** | Kiểm tra/chuẩn hóa ảnh sản phẩm, tải ảnh URL, tự vẽ ảnh minh họa khi thiếu ảnh | Cài qua `pip` |
| QSS (Qt Style Sheets) | Giao diện sáng/tối, màu đen than – vàng Champagne – xanh ngọc | Nằm trong `ui/theme.py` |

Không dùng ReportLab: hóa đơn được vẽ bằng `QPainter` lên `QPrinter` (Qt Print Support) nên hỗ trợ tiếng Việt có dấu
mà không cần cài thêm thư viện hay đăng ký phông chữ.

---

## 2. Kiến trúc tổng thể

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ui/  (PySide6)  – Cửa sổ chính, 8 phân hệ, hộp thoại, theme QSS, biểu đồ │
└──────────────┬──────────────────────────────────────────┬────────────────┘
               │ gọi phương thức nghiệp vụ                  │ in / xuất PDF
┌──────────────▼──────────────────────────┐   ┌──────────▼───────────────┐
│ services/ – Quy tắc nghiệp vụ           │   │ printing/ – QPainter vẽ  │
│ (kiểm tra dữ liệu, tính tiền, thanh     │   │ hóa đơn lên QPrinter/PDF │
│  toán, kho, báo cáo, transaction)       │   └──────────────────────────┘
└──────────────┬──────────────────────────┘
               │ gọi repository (có thể chung 1 transaction)
┌──────────────▼──────────────────────────┐   models/  – dataclass ánh xạ bảng
│ repositories/ – Toàn bộ câu lệnh SQL    │   utils/   – định dạng tiền, kiểm tra,
│ (SELECT/INSERT/UPDATE/DELETE, JOIN,     │              tìm kiếm không dấu, ảnh
│  SUM, COUNT, GROUP BY – có tham số ?)   │   errors.py – ngoại lệ có thông báo
└──────────────┬──────────────────────────┘              tiếng Việt
               │ sqlite3 (PRAGMA foreign_keys = ON)
┌──────────────▼──────────────────────────┐
│ database.py – kết nối, schema, BEGIN/   │──▶  baotran_jewelry.db
│ COMMIT/ROLLBACK, sao lưu, kiểm tra CSDL │
└─────────────────────────────────────────┘
```

* **Giao diện không viết SQL**; mọi dữ liệu hiển thị đều được truy vấn lại từ SQLite.
* `app_context.py` khởi tạo và gom các repository/service để truyền cho giao diện.
* `seed_data.py` tạo dữ liệu mẫu **đúng một lần**, trong một transaction.

### Cấu trúc thư mục

```
QLCH_TrangSucBT/                  (thư mục dự án – tương ứng BaoTranJewelry/)
├── main.py                       Điểm khởi động – nhấn Run tệp này
├── config.py                     Đường dẫn, hằng số nghiệp vụ, cài đặt mặc định
├── database.py                   Kết nối SQLite, tạo bảng, transaction, sao lưu
├── seed_data.py                  Dữ liệu mẫu (15 sản phẩm, 7 khách hàng, 34 hóa đơn)
├── app_context.py                Khởi tạo repository + service
├── errors.py                     Các ngoại lệ nghiệp vụ (thông báo tiếng Việt)
├── requirements.txt
├── README.md
├── baotran_jewelry.db            (tự tạo khi chạy lần đầu)
├── models/                       Lớp dữ liệu: product, customer (+employee), invoice, inventory
├── repositories/                 SQL cho từng bảng: product, category, customer, employee,
│                                 invoice, inventory, settings (+ base_repository)
├── services/                     pos_service (giỏ hàng, tính tiền, thanh toán, hủy HĐ),
│                                 product_service, customer_service, inventory_service,
│                                 report_service, settings_service
├── printing/
│   └── invoice_printer.py        Vẽ hóa đơn A4 (QPainter) – xem trước, in, xuất PDF
├── ui/
│   ├── main_window.py            Cửa sổ chính: thanh điều hướng, tiêu đề, các trang
│   ├── dashboard_page.py         Tổng quan
│   ├── pos_page.py               Bán hàng POS
│   ├── products_page.py          Quản lý sản phẩm (CRUD + ảnh)
│   ├── inventory_page.py         Quản lý kho hàng
│   ├── customers_page.py         Quản lý khách hàng
│   ├── invoices_page.py          Lịch sử giao dịch
│   ├── reports_page.py           Báo cáo thống kê
│   ├── settings_page.py          Cài đặt hệ thống
│   ├── invoice_dialog.py         Hóa đơn thanh toán: xem trước / in / PDF
│   ├── customer_dialog.py        Biểu mẫu khách hàng
│   ├── stock_dialog.py           Nhập kho / điều chỉnh tồn kho
│   ├── chart_widget.py           Biểu đồ Matplotlib nhúng PySide6
│   ├── theme.py                  Bảng màu + QSS sáng/tối
│   ├── icons.py, image_loader.py, widgets.py   Icon SVG, nạp ảnh, thành phần dùng chung
├── utils/                        formatters, validators, text_utils, image_utils
├── assets/
│   ├── icons/                    45 icon SVG (+ thư mục theme/ tự sinh)
│   └── images/                   logo.png, no_image.png, samples/ (14 ảnh trang sức),
│                                 products/ (ảnh người dùng chọn), cache/ (ảnh tải từ URL)
└── tests/
    └── test_core.py              22 bài kiểm thử tự động (unittest)
```

---

## 3. Thiết kế cơ sở dữ liệu SQLite

```
categories 1───n products 1───n invoice_details n───1 invoices n───1 customers
                     │                                     │
                     └──1───n inventory_transactions        └──n───1 employees
settings (khóa – giá trị cấu hình)
```

| Bảng | Nội dung chính | Ràng buộc |
|---|---|---|
| `categories` | Danh mục trang sức | `category_name` UNIQUE |
| `products` | Mã SP, **SKU**, tên, danh mục, chất liệu, **trọng lượng + đơn vị (chỉ/lượng/gram)**, giá nhập, giá bán, tồn kho, ảnh, mô tả, trạng thái, ngày tạo/cập nhật | SKU UNIQUE, FK → categories, CHECK giá > 0, tồn ≥ 0, đơn vị ∈ {chỉ, lượng, gram} |
| `customers` | Mã KH, tên, SĐT, email, địa chỉ, ghi chú | SĐT UNIQUE |
| `employees` | Nhân viên bán hàng | – |
| `invoices` | Mã HĐ, khách hàng (có thể NULL = khách lẻ), **snapshot tên/SĐT/địa chỉ**, nhân viên, thời điểm, tổng tiền hàng, chiết khấu (loại, giá trị, số tiền), thuế suất, tiền VAT, tổng thanh toán, khách đưa, tiền thừa, phương thức, trạng thái, lý do hủy | `invoice_code` UNIQUE, CHECK `total = subtotal − discount + vat`, CHECK chiết khấu ≤ tiền hàng, status ∈ {PAID, CANCELLED} |
| `invoice_details` | **Snapshot** tên, SKU, danh mục, chất liệu, trọng lượng, đơn vị, đơn giá, giá vốn tại thời điểm bán; số lượng; thành tiền | FK → invoices, products; CHECK `line_total = quantity × unit_price` |
| `inventory_transactions` | Lịch sử kho: IMPORT (nhập), SALE (xuất bán), ADJUST (điều chỉnh), CANCEL (hoàn kho khi hủy HĐ), số lượng thay đổi, tồn sau, mã tham chiếu, lý do, người thực hiện, thời điểm | FK → products |
| `settings` | Thông tin cửa hàng, thuế suất VAT, ngưỡng tồn kho thấp, bảo hành, chính sách thu mua, giao diện | – |

**Đáp ứng yêu cầu truy xuất CSDL:** tạo bảng `CREATE TABLE IF NOT EXISTS`; `SELECT`/`INSERT`/`UPDATE`/`DELETE`;
`JOIN` (sản phẩm–danh mục, khách hàng–hóa đơn, chi tiết–hóa đơn–sản phẩm); `SUM`, `COUNT`, `GROUP BY` trong báo cáo;
khóa chính, khóa ngoại, `UNIQUE`, `CHECK`; `PRAGMA foreign_keys = ON` cho **mọi** kết nối; **truy vấn có tham số `?`**
(không ghép chuỗi dữ liệu người dùng); mỗi thao tác mở – đóng kết nối; `BEGIN IMMEDIATE … COMMIT/ROLLBACK`.

### Quy tắc tính tiền (dùng thống nhất trên giao diện, CSDL và hóa đơn)

```
Thành tiền dòng   = Số lượng × Đơn giá
Tổng tiền hàng    = Σ Thành tiền dòng
Tiền chiết khấu   = Tổng tiền hàng × %CK   (theo %)   hoặc   số tiền giảm trực tiếp (theo ₫)
Giá trị tính thuế = Tổng tiền hàng − Tiền chiết khấu
Tiền VAT          = Giá trị tính thuế × Thuế suất VAT (cấu hình trong Cài đặt, có thể chỉnh cho từng HĐ)
Tổng thanh toán   = Tổng tiền hàng − Tiền chiết khấu + Tiền VAT
```
Tiền được làm tròn đến đồng. Chiết khấu âm, > 100% hoặc lớn hơn tổng tiền hàng đều bị từ chối.

### Quy tắc doanh thu

**Doanh thu thực thu** = tổng "Tổng thanh toán" của các hóa đơn có trạng thái **Đã thanh toán**.
Hóa đơn **Đã hủy** vẫn được lưu để tra cứu nhưng **không** tính vào doanh thu và số đơn hàng (tồn kho được hoàn lại khi hủy).
POS chỉ ghi hóa đơn khi thanh toán thành công nên không tồn tại hóa đơn "chưa thanh toán".

### Thanh toán an toàn bằng transaction

`PosService.checkout()` thực hiện trong **một** transaction: kiểm tra giỏ hàng, khách hàng, nhân viên → đọc lại tồn kho
và giá mới nhất → sinh mã hóa đơn duy nhất (`HDyyyymmdd-0001`) → ghi `invoices` → ghi `invoice_details` →
trừ kho bằng `UPDATE … WHERE stock_quantity + ? >= 0` → ghi `inventory_transactions`. Lỗi ở bất kỳ bước nào ⇒ **ROLLBACK**,
không có chuyện đã trừ kho mà chưa có hóa đơn. Thêm vào giỏ **không** trừ kho.

---

## 4. Hướng dẫn cài đặt và chạy trên PyCharm (Windows)

### Bước 1 – Cài Python
1. Tải **Python 3.12** tại <https://www.python.org/downloads/windows/> (bản *Windows installer 64-bit*).
2. Khi cài, **tích chọn "Add python.exe to PATH"** rồi nhấn *Install Now*.
3. Kiểm tra: mở *Command Prompt* gõ `python --version` → hiện `Python 3.12.x`.

### Bước 2 – Cài PyCharm
Tải **PyCharm Community** (miễn phí) tại <https://www.jetbrains.com/pycharm/download/> và cài đặt mặc định.

### Bước 3 – Mở dự án
1. Giải nén/đặt thư mục dự án, ví dụ `D:\QLCH_TrangSucBT` (đường dẫn nên tránh ký tự đặc biệt).
2. PyCharm → **File → Open…** → chọn thư mục `QLCH_TrangSucBT` → **OK** → chọn **Trust Project**.
3. Đảm bảo các tệp nằm đúng như mục *Cấu trúc thư mục* (tệp `main.py` ở ngay thư mục gốc).

### Bước 4 – Chọn Python Interpreter (môi trường ảo)
1. **File → Settings → Project: QLCH_TrangSucBT → Python Interpreter**.
2. Nhấn **Add Interpreter → Add Local Interpreter… → Virtualenv Environment**.
   * Nếu thư mục `.venv` **đã có**: chọn *Existing* → trỏ tới `D:\QLCH_TrangSucBT\.venv\Scripts\python.exe`.
   * Nếu **chưa có**: chọn *New*, *Location* = `D:\QLCH_TrangSucBT\.venv`, *Base interpreter* = Python 3.12.
3. Nhấn **OK** – góc dưới phải PyCharm hiện `Python 3.12 (QLCH_TrangSucBT)`.

### Bước 5 – Cài thư viện
Mở **Terminal** trong PyCharm (`Alt+F12`, đảm bảo đầu dòng có `(.venv)`) và chạy:

```bash
pip install -r requirements.txt
```

Lệnh này cài PySide6-Essentials, Matplotlib, Pillow. `sqlite3` có sẵn trong Python nên không cần cài.
(PyCharm cũng có thể hiện thông báo *Install requirements* khi mở `requirements.txt` – bấm vào là được.)

### Bước 6 – Khởi tạo cơ sở dữ liệu
Không cần làm thủ công. **Lần chạy đầu tiên**, `main.py` tự động:
* tạo tệp `baotran_jewelry.db` và toàn bộ bảng;
* ghi cài đặt mặc định;
* thêm dữ liệu mẫu **một lần duy nhất** (8 danh mục, 15 sản phẩm, 7 khách hàng, 3 nhân viên, 34 hóa đơn trong 60 ngày gần nhất, trong đó 1 hóa đơn đã hủy).

Muốn tạo lại dữ liệu mẫu mới: **đóng chương trình → xóa tệp `baotran_jewelry.db` → chạy lại**.

### Bước 7 – Chạy chương trình
* Mở `main.py` → nhấn nút **Run ▶** màu xanh (hoặc chuột phải → *Run 'main'*, phím `Shift+F10`).
* Hoặc trong Terminal: `python main.py`.

Cửa sổ **BẢO TRÂN JEWELRY** mở trên Desktop. Console của PyCharm hiển thị nhật ký, ví dụ:
`[INFO] database: CSDL sẵn sàng: ...\baotran_jewelry.db (tạo mới)`.

Phím tắt: `Ctrl+1 … Ctrl+8` chuyển phân hệ, `F5` tải lại dữ liệu, trong POS: `F2` tìm sản phẩm, `F9` thanh toán.

### Bước 8 – Kiểm tra dữ liệu trong `baotran_jewelry.db`
* **Trong phần mềm:** *Cài đặt hệ thống → Giao diện & dữ liệu* hiển thị số bản ghi thực tế của từng bảng, nút
  *Kiểm tra toàn vẹn* (`PRAGMA integrity_check`, `foreign_key_check`) và *Sao lưu CSDL*.
* **DB Browser for SQLite** (miễn phí, <https://sqlitebrowser.org>): *Open Database* → chọn `baotran_jewelry.db` →
  tab *Browse Data* để xem bảng, tab *Execute SQL* để chạy truy vấn. *(Đóng DB Browser trước khi ghi dữ liệu bằng phần mềm
  để tránh khóa tệp.)*
* **PyCharm Professional:** cửa sổ *Database → + → Data Source → SQLite* → chọn tệp.
* **Python Console** của PyCharm:
  ```python
  import sqlite3
  conn = sqlite3.connect("baotran_jewelry.db")
  for row in conn.execute("SELECT invoice_code, created_at, total_amount, status FROM invoices ORDER BY invoice_id DESC LIMIT 5"):
      print(row)
  conn.close()
  ```

### Bước 9 – Chạy kiểm thử tự động (không bắt buộc)
Chuột phải thư mục `tests` → *Run 'Python tests in tests'*, hoặc:
```bash
python -m unittest discover -s tests -v
```
Các bài kiểm thử dùng tệp CSDL tạm, **không** ảnh hưởng `baotran_jewelry.db`.

### Khắc phục lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `ModuleNotFoundError: No module named 'PySide6'` (hoặc matplotlib, PIL) | Interpreter chưa đúng `.venv` hoặc chưa cài thư viện → làm lại Bước 4, 5. Console cũng in hướng dẫn này. |
| `qt.qpa.plugin: Could not load the Qt platform plugin "windows"` | Cài lại: `pip install --force-reinstall PySide6-Essentials`; không cài lẫn PyQt5/PyQt6 trong cùng môi trường. |
| `SyntaxError` ở chú thích kiểu `int \| None` | Python quá cũ – cần Python ≥ 3.10. |
| `pip` báo timeout / chậm | `pip install -r requirements.txt --default-timeout=120` hoặc kiểm tra mạng. |
| "database is locked" / không lưu được | Đóng DB Browser (hoặc bấm *Write Changes/Close Database*), không mở 2 cửa sổ phần mềm cùng lúc. |
| Xuất PDF báo lỗi | Tệp PDF cùng tên đang mở trong trình đọc PDF → đóng lại hoặc lưu tên khác; chọn thư mục có quyền ghi. |
| Ảnh sản phẩm không hiển thị | Đường dẫn sai hoặc không có mạng (ảnh URL) → phần mềm tự dùng ảnh mặc định, có thể chọn lại ảnh trong *Quản lý sản phẩm*. |
| Muốn dữ liệu sạch | Đóng phần mềm, xóa `baotran_jewelry.db`, chạy lại (sẽ tạo lại dữ liệu mẫu). |
| Màn hình nhỏ (1366×768) | Cửa sổ tự phóng to; các khung có thanh cuộn và có thể kéo thanh chia (splitter) để đổi kích thước. |

---

## 5. Các phân hệ và chức năng

1. **Tổng quan:** 5 thẻ KPI truy vấn từ SQLite (doanh thu thực thu, số đơn đã thanh toán, số sản phẩm, tổng tồn kho, số khách hàng,
   kèm số liệu hôm nay); biểu đồ doanh thu Matplotlib theo **ngày/tháng/khoảng thời gian**, dạng **cột hoặc đường**, kèm số giao dịch;
   cảnh báo tồn kho thấp; giao dịch gần đây (nhấn đúp → xem hóa đơn); trạng thái rỗng thân thiện khi chưa có dữ liệu.
2. **Bán hàng POS:** lưới thẻ sản phẩm (ảnh, SKU, tên, danh mục, chất liệu, trọng lượng, giá, tồn kho); tìm kiếm **không dấu,
   không phân biệt hoa thường**, nhiều từ; lọc danh mục, chỉ còn hàng; giỏ hàng tăng/giảm/xóa, **không cho vượt tồn kho**;
   chọn khách hàng có sẵn / **khách lẻ** / thêm nhanh khách mới; nhân viên bán hàng; chiết khấu **% hoặc ₫**; VAT cấu hình được;
   công thức hiển thị trên màn hình; tiền mặt (khách đưa, tiền thừa) và các phương thức khác; thanh toán bằng transaction →
   thông báo → mở hóa đơn.
3. **Quản lý sản phẩm:** thêm/sửa với kiểm tra dữ liệu, SKU không trùng, quy đổi trọng lượng (chỉ/lượng/gram), lãi gộp dự kiến;
   ảnh: chọn từ máy (sao chép vào `assets/images/products`), tải từ URL (luồng nền, xử lý mất mạng), xem trước, ảnh mặc định;
   thêm danh mục; xóa sản phẩm **chưa bán**; sản phẩm **đã bán** → đề nghị **Ngừng kinh doanh**; mở bán lại.
4. **Quản lý kho hàng:** KPI tồn kho, giá trị tồn; lọc sắp hết/hết hàng; **Nhập kho** (mã phiếu, ghi chú) và **Điều chỉnh tồn kho**
   (số thực tế + lý do bắt buộc); lịch sử nhập–xuất–điều chỉnh–hoàn kho theo sản phẩm, loại, thời gian.
5. **Quản lý khách hàng:** thêm/sửa/xóa (không xóa khách đã có hóa đơn), tìm kiếm, số đơn, tổng mua, lần mua gần nhất,
   lịch sử mua hàng (nhấn đúp mở hóa đơn).
6. **Lịch sử giao dịch:** tìm theo mã HĐ/khách hàng/SĐT/nhân viên, lọc ngày & trạng thái; xem chi tiết dòng hàng (snapshot);
   **xem lại, in lại, xuất lại PDF**; **hủy hóa đơn** (bắt buộc lý do, hoàn kho, không tính doanh thu).
7. **Hóa đơn bán hàng:** mẫu A4 phong cách tiệm vàng: logo, tên/địa chỉ/SĐT cửa hàng (cấu hình), mã HĐ, ngày giờ, khách hàng,
   nhân viên, bảng sản phẩm (SKU, chất liệu, trọng lượng + quy đổi gram, SL, đơn giá, thành tiền), tổng tiền hàng, chiết khấu,
   **thuế suất & tiền thuế**, tổng thanh toán, **số tiền bằng chữ**, phương thức thanh toán, khách đưa/tiền thừa, bảo hành,
   chính sách thu mua/đổi trả, lời cảm ơn, chữ ký; tự **sang trang** và lặp tiêu đề bảng; dấu "ĐÃ HỦY" với hóa đơn hủy;
   ghi chú *hóa đơn nội bộ – không thay thế hóa đơn điện tử/GTGT*.
8. **Báo cáo thống kê:** doanh thu theo ngày, theo tháng, số giao dịch, giá trị trung bình, lợi nhuận gộp ước tính (theo giá vốn
   snapshot), sản phẩm bán chạy, doanh số theo danh mục, tồn kho thấp; biểu đồ Matplotlib; **xuất CSV** (mở bằng Excel).
9. **Cài đặt hệ thống:** thông tin cửa hàng in trên hóa đơn, thuế suất VAT mặc định, ngưỡng tồn kho thấp, nội dung bảo hành/chính
   sách, quản lý nhân viên, **giao diện sáng/tối** (lưu lại cho lần sau), số bản ghi từng bảng, kiểm tra toàn vẹn, sao lưu CSDL.

---

## 6. Kịch bản nghiệm thu gợi ý (thực hiện khi bảo vệ)

| # | Thao tác | Kết quả mong đợi |
|---|---|---|
| 1 | Xóa `baotran_jewelry.db` (nếu có), nhấn Run `main.py` | Cửa sổ desktop mở; tệp `baotran_jewelry.db` được tạo; Dashboard có số liệu |
| 2 | Đóng và chạy lại | Số sản phẩm/hóa đơn **không tăng** (dữ liệu mẫu chỉ thêm 1 lần) |
| 3 | *Cài đặt → Giao diện & dữ liệu* | Thấy số bản ghi 8 bảng; *Kiểm tra toàn vẹn* = ok, 0 lỗi khóa ngoại |
| 4 | *Quản lý sản phẩm → Thêm sản phẩm*, nhập SKU mới, tồn 5, Lưu | Sản phẩm xuất hiện trong bảng; DB Browser thấy dòng mới trong `products` và phiếu IMPORT trong `inventory_transactions` |
| 5 | Nhập lại SKU đã có (khác hoa/thường) | Báo "Mã SKU … đã tồn tại", không lưu |
| 6 | Sửa giá bán sản phẩm, Lưu | Giá thay đổi trong bảng và trong SQLite (`updated_at` cập nhật) |
| 7 | *Bán hàng POS*: gõ `nhan vang` (không dấu) | Kết quả gồm "Nhẫn trơn vàng 24K", "Nhẫn nữ vàng 18K…" |
| 8 | Thêm sản phẩm vào giỏ vượt tồn kho | Báo "Không đủ tồn kho", số lượng giữ nguyên |
| 9 | Chọn chiết khấu 5%, VAT 10% | Tiền CK, VAT, tổng thanh toán đúng công thức hiển thị |
| 10 | Nhấn *Thanh toán* với giỏ trống | Báo "Giỏ hàng trống" |
| 11 | Thanh toán giỏ hợp lệ | Thông báo thành công + mã HĐ; mở xem trước hóa đơn; tồn kho giảm; HĐ có trong *Lịch sử giao dịch*; KPI Dashboard tăng |
| 12 | Trong hóa đơn: *Xuất PDF*, *In hóa đơn* | Tệp PDF được lưu ở vị trí đã chọn; hộp thoại in của Windows mở |
| 13 | Đổi tên/giá sản phẩm vừa bán rồi mở lại hóa đơn cũ | Hóa đơn cũ giữ nguyên tên và đơn giá lúc bán |
| 14 | Xóa sản phẩm đã bán | Không cho xóa, đề nghị chuyển *Ngừng kinh doanh*; sản phẩm biến mất khỏi POS nhưng hóa đơn cũ vẫn đúng |
| 15 | *Lịch sử giao dịch → Hủy hóa đơn* | Trạng thái "Đã hủy", tồn kho hoàn lại, doanh thu Dashboard/Báo cáo giảm tương ứng |
| 16 | *Quản lý kho → Điều chỉnh tồn kho* không nhập lý do | Không cho lưu; có lý do → lịch sử kho ghi nhận ADJUST |
| 17 | *Báo cáo thống kê*: chọn khoảng thời gian không có giao dịch | Biểu đồ hiển thị "Chưa có dữ liệu…", không báo lỗi |
| 18 | Nhấn biểu tượng mặt trời/mặt trăng | Chuyển giao diện sáng ↔ tối; mở lại phần mềm vẫn giữ lựa chọn |

---

## 7. Kết quả kiểm thử đã thực hiện

* **22 bài kiểm thử tự động** (`tests/test_core.py`) – tất cả **đạt**: tạo bảng & khóa ngoại, dữ liệu mẫu chỉ thêm 1 lần và còn
  sau khi mở lại CSDL, CRUD sản phẩm, SKU trùng, quy tắc xóa/ngừng kinh doanh, tìm kiếm không dấu, công thức chiết khấu/VAT/làm tròn,
  không bán vượt tồn kho, **rollback** khi lỗi giữa transaction và khi tồn kho thay đổi, snapshot hóa đơn, hủy hóa đơn hoàn kho và
  loại khỏi doanh thu, kiểm tra khách hàng, lịch sử kho, báo cáo khớp nhau, báo cáo khi không có giao dịch, đọc số thành chữ, xuất PDF.
* **Kiểm thử giao diện tự động** (chạy cửa sổ thật ở chế độ ẩn): thêm vào giỏ, chặn vượt tồn kho, chiết khấu theo số tiền,
  thanh toán qua màn hình POS, KPI Dashboard cập nhật, thêm/sửa sản phẩm qua biểu mẫu, chặn SKU trùng, xóa sản phẩm đã bán →
  ngừng kinh doanh, hủy hóa đơn, dựng bản xem trước hóa đơn, ảnh không tồn tại, đổi giao diện sáng/tối.
* Đã kiểm tra trực quan giao diện 8 phân hệ ở 1440×900 và 1366×728, cả giao diện sáng và tối; kiểm tra tệp PDF hóa đơn
  (1 trang và nhiều trang).
* **Chưa kiểm tra được:** in ra máy in vật lý (môi trường phát triển không có máy in – chức năng dùng hộp thoại in chuẩn của
  Windows), và chưa chạy trên Python 3.12 cụ thể (đã chạy trên Python 3.14.7 với PySide6 6.12, Matplotlib 3.11, Pillow 13).

---

## 8. Giới hạn hiện tại và hướng phát triển

* Ứng dụng **một máy, một người dùng** (SQLite cục bộ); chưa có đăng nhập/phân quyền – nhân viên được chọn khi bán hàng.
* Giá vàng không tự cập nhật theo thị trường; giá bán do người quản lý nhập.
* Một thuế suất VAT cho mỗi hóa đơn (cấu hình được), chưa tách thuế suất theo từng mặt hàng; chưa tính VAT theo phương pháp
  trực tiếp trên giá trị gia tăng của vàng.
* Hủy hóa đơn là hủy toàn bộ; chưa có nghiệp vụ đổi/trả một phần hoặc thu mua lại vàng cũ.
* Chưa tích hợp máy quét mã vạch/máy in nhiệt (máy quét dạng bàn phím vẫn nhập được SKU vào ô tìm kiếm).
* Hóa đơn là **hóa đơn bán hàng nội bộ** phục vụ mô phỏng – không thay thế hóa đơn điện tử/hóa đơn GTGT theo quy định.
* Ảnh sản phẩm mẫu là **ảnh minh họa do chương trình tự vẽ** (Pillow) để chạy được offline; có thể thay bằng ảnh thật trong
  *Quản lý sản phẩm*.
