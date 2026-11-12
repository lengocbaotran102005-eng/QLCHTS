"""Xử lý hình ảnh sản phẩm bằng Pillow.

* Kiểm tra tệp ảnh, nhập ảnh từ máy tính vào ``assets/images/products``.
* Tải ảnh từ URL (có giới hạn thời gian chờ, xử lý mất mạng) và lưu bộ nhớ đệm.
* Tự vẽ ảnh minh họa trang sức mẫu, ảnh mặc định và logo khi thư mục ảnh chưa có
  (giúp phần mềm chạy được hoàn toàn offline).
"""
import hashlib
import io
import logging
import math
import re
import socket
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, UnidentifiedImageError

import config
from errors import ImageError
from utils.text_utils import normalize_search

log = logging.getLogger(__name__)

MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 1000
SUPPORTED_FILTER = "Ảnh (*.png *.jpg *.jpeg *.bmp *.webp *.gif)"


# ---------------------------------------------------------------------------
# Đường dẫn ảnh
# ---------------------------------------------------------------------------
def is_url(source: str) -> bool:
    return bool(source) and source.strip().lower().startswith(("http://", "https://"))


def resolve_local_path(source: str) -> Path:
    """Đường dẫn tương đối được tính từ thư mục dự án (để CSDL không phụ thuộc máy tính)."""
    path = Path(source.strip())
    return path if path.is_absolute() else config.BASE_DIR / path


def url_cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:24]
    return config.IMAGE_CACHE_DIR / f"{digest}.png"


def resolve_image_file(source: str) -> Path | None:
    """Trả về tệp ảnh cục bộ tương ứng với ``source`` (đường dẫn hoặc URL đã tải), hoặc None."""
    if not source:
        return None
    if is_url(source):
        cached = url_cache_path(source)
        return cached if cached.exists() else None
    path = resolve_local_path(source)
    return path if path.is_file() else None


def to_project_relative(path: Path) -> str:
    """Chuyển đường dẫn tuyệt đối thành tương đối với thư mục dự án nếu có thể."""
    try:
        return path.resolve().relative_to(config.BASE_DIR).as_posix()
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Kiểm tra / nhập / tải ảnh
# ---------------------------------------------------------------------------
def _open_verified(data_or_path) -> Image.Image:
    """Mở ảnh và kiểm tra tính toàn vẹn; ném ImageError nếu không phải ảnh hợp lệ."""
    try:
        with Image.open(data_or_path) as probe:
            probe.verify()
        if isinstance(data_or_path, io.BytesIO):
            data_or_path.seek(0)
        image = Image.open(data_or_path)
        image.load()
        return image
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ImageError("Tệp đã chọn không phải là ảnh hợp lệ hoặc đã bị hỏng.") from exc


def _normalize_image(image: Image.Image) -> Image.Image:
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() or image.mode == "P" else "RGB")
    image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
    return image


def check_image_source(source: str) -> tuple[bool, str]:
    """Kiểm tra nhanh đường dẫn ảnh, trả về (hợp lệ, thông báo)."""
    source = (source or "").strip()
    if not source:
        return True, "Chưa có ảnh – hệ thống sẽ dùng ảnh mặc định."
    if is_url(source):
        if url_cache_path(source).exists():
            return True, "Ảnh từ URL đã được tải về bộ nhớ đệm."
        return True, "Ảnh từ URL – sẽ được tải khi có kết nối Internet."
    path = resolve_local_path(source)
    if not path.is_file():
        return False, f"Không tìm thấy tệp ảnh: {path}"
    try:
        _open_verified(path).close()
    except ImageError as exc:
        return False, exc.message
    return True, "Đường dẫn ảnh hợp lệ."


def import_local_image(source_file: str | Path, name_hint: str = "") -> str:
    """Sao chép ảnh từ máy tính vào ``assets/images/products`` (chuẩn hóa sang PNG).

    Trả về đường dẫn tương đối để lưu vào cột ``products.image_path``.
    """
    source_file = Path(source_file)
    if not source_file.is_file():
        raise ImageError(f"Không tìm thấy tệp ảnh: {source_file}")
    image = _normalize_image(_open_verified(source_file))
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_search(name_hint or source_file.stem)).strip("-") or "anh"
    config.PRODUCT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    target = config.PRODUCT_IMAGES_DIR / f"{slug[:40]}_{datetime.now():%Y%m%d%H%M%S}.png"
    try:
        image.save(target, "PNG")
    except OSError as exc:
        raise ImageError(f"Không thể lưu ảnh vào thư mục dự án: {exc}") from exc
    return to_project_relative(target)


def download_image(url: str, timeout: float = 8.0) -> Path:
    """Tải ảnh từ Internet về bộ nhớ đệm; xử lý mất mạng, quá thời gian, tệp không phải ảnh."""
    url = url.strip()
    if not is_url(url):
        raise ImageError("URL ảnh phải bắt đầu bằng http:// hoặc https://")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 BaoTranJewelry/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise ImageError(f"Máy chủ ảnh trả về lỗi {exc.code}. Vui lòng kiểm tra lại URL.") from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
        raise ImageError(
            "Không thể tải ảnh từ Internet. Vui lòng kiểm tra kết nối mạng hoặc đường dẫn URL."
        ) from exc
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ImageError("Ảnh tải về vượt quá dung lượng cho phép (10 MB).")
    image = _normalize_image(_open_verified(io.BytesIO(data)))
    target = url_cache_path(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "PNG")
    return target


# ---------------------------------------------------------------------------
# Vẽ ảnh minh họa trang sức (chạy khi thiếu ảnh mẫu)
# ---------------------------------------------------------------------------
W, H = 640, 480
SS = 2  # vẽ ở độ phân giải gấp đôi rồi thu nhỏ để khử răng cưa

GOLD = ["#FFF6D2", "#F4CF6A", "#C9952F", "#8C621E", "#E8BD58", "#FFF0C0", "#B9862A"]
ROSE_GOLD = ["#FFE6DA", "#F0B39A", "#C27A5E", "#8E4E3A", "#E6A68A", "#FFE1D2"]
WHITE_GOLD = ["#FFFFFF", "#E3E5EB", "#A9ADB8", "#F5F6F9", "#8E929D", "#ECEEF2"]
DIAMOND = ["#FFFFFF", "#DDF3FF", "#9ED3F0", "#F7FCFF", "#B8E2F8"]
RUBY = ["#FFB0BC", "#E0304D", "#86102A", "#FF6A82", "#B0173A"]
SAPPHIRE = ["#B3D0FF", "#2E62D6", "#0D2B70", "#5B8FF2", "#1B45A8"]
PEARL = ["#FFFFFF", "#F6F0E6", "#D9CFC0", "#FFFDF8"]
CZ = ["#FFFFFF", "#EAF4FF", "#C3D7EA", "#FFFFFF"]


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _gradient(size: tuple[int, int], colors: list[str], angle: float = 35) -> Image.Image:
    """Ảnh gradient nhiều màu theo góc ``angle`` (tạo hiệu ứng ánh kim loại)."""
    w, h = size
    diag = int(math.hypot(w, h)) + 4
    strip = Image.new("RGB", (1, len(colors)))
    for i, c in enumerate(colors):
        strip.putpixel((0, i), _hex(c))
    band = strip.resize((diag, diag), Image.BICUBIC)
    band = band.rotate(angle, resample=Image.BICUBIC)
    left, top = (diag - w) // 2, (diag - h) // 2
    return band.crop((left, top, left + w, top + h))


def _canvas(dark: bool = True) -> Image.Image:
    w, h = W * SS, H * SS
    top, bottom = ("#2E2A25", "#121110") if dark else ("#F7F1E6", "#E2D5BF")
    base = _gradient((w, h), [top, bottom], angle=90)
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse((w * 0.18, h * 0.05, w * 0.82, h * 0.85), fill=120 if dark else 90)
    glow = glow.filter(ImageFilter.GaussianBlur(90 * SS))
    light = Image.new("RGB", (w, h), "#5A5045" if dark else "#FFFFFF")
    base.paste(light, (0, 0), glow)
    return base


def _shadow(img: Image.Image, box, blur: int = 18, opacity: int = 150) -> None:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=opacity)
    mask = mask.filter(ImageFilter.GaussianBlur(blur * SS))
    img.paste(Image.new("RGB", img.size, (0, 0, 0)), (0, 0), mask)


def _fill(img: Image.Image, mask: Image.Image, colors: list[str], angle: float = 35) -> None:
    img.paste(_gradient(img.size, colors, angle), (0, 0), mask)


def _highlight(img: Image.Image, draw_fn, blur: float = 2.5, opacity: int = 170) -> None:
    mask = Image.new("L", img.size, 0)
    draw_fn(ImageDraw.Draw(mask))
    mask = mask.filter(ImageFilter.GaussianBlur(blur * SS))
    mask = mask.point(lambda v: v * opacity // 255)
    img.paste(Image.new("RGB", img.size, (255, 255, 255)), (0, 0), mask)


def _ring(img, cx, cy, r, thickness, metal, tilt=0.88) -> None:
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((cx - r, cy - r * tilt, cx + r, cy + r * tilt), fill=255)
    ri = r - thickness
    d.ellipse((cx - ri, cy - ri * tilt * 0.94 - thickness * 0.12, cx + ri, cy + ri * tilt * 0.94 - thickness * 0.12),
              fill=0)
    _fill(img, mask, metal)
    _highlight(img, lambda dr: dr.arc((cx - r + thickness * 0.35, cy - r * tilt + thickness * 0.3,
                                       cx + r - thickness * 0.35, cy + r * tilt - thickness * 0.3),
                                      200, 290, fill=255, width=int(thickness * 0.22)))


def _gem_side(img, cx, cy, w, h, colors) -> None:
    """Viên đá cắt giác nhìn nghiêng (phần vương miện + phần đáy nhọn)."""
    crown_h, pav_h = h * 0.38, h * 0.62
    pts = [(cx - w / 2, cy), (cx - w * 0.3, cy - crown_h), (cx + w * 0.3, cy - crown_h), (cx + w / 2, cy),
           (cx, cy + pav_h)]
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon(pts, fill=255)
    _fill(img, mask, colors, angle=60)
    d = ImageDraw.Draw(img, "RGBA")
    line = (255, 255, 255, 150)
    width = max(1, SS)
    d.line([(cx - w / 2, cy), (cx + w / 2, cy)], fill=line, width=width)
    for fx in (-0.3, -0.1, 0.1, 0.3):
        d.line([(cx + w * fx, cy - crown_h), (cx + w * fx * 1.6, cy)], fill=line, width=width)
        d.line([(cx + w * fx * 1.6, cy), (cx, cy + pav_h)], fill=(255, 255, 255, 90), width=width)
    _highlight(img, lambda dr: dr.polygon([(cx - w * 0.22, cy - crown_h * 0.9), (cx - w * 0.05, cy - crown_h * 0.9),
                                           (cx - w * 0.15, cy - crown_h * 0.2)], fill=255), blur=1.5, opacity=200)


def _gem_round_top(img, cx, cy, r, colors) -> None:
    """Viên đá tròn nhìn từ trên xuống (giác cắt hình sao)."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).regular_polygon((cx, cy, r), 16, fill=255)
    _fill(img, mask, colors, angle=50)
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(8):
        a = math.pi * 2 * i / 8
        d.line([(cx + math.cos(a) * r * 0.45, cy + math.sin(a) * r * 0.45),
                (cx + math.cos(a + math.pi / 8) * r, cy + math.sin(a + math.pi / 8) * r)],
               fill=(255, 255, 255, 120), width=SS)
    d.regular_polygon((cx, cy, r * 0.45), 8, outline=(255, 255, 255, 160), width=SS)
    _highlight(img, lambda dr: dr.ellipse((cx - r * 0.5, cy - r * 0.62, cx - r * 0.1, cy - r * 0.3), fill=255),
               blur=2, opacity=220)


def _pearl(img, cx, cy, r) -> None:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    _fill(img, mask, PEARL, angle=120)
    _highlight(img, lambda dr: dr.ellipse((cx - r * 0.55, cy - r * 0.6, cx - r * 0.05, cy - r * 0.15), fill=255),
               blur=3, opacity=230)


def _chain_points(cx, top, width, depth, count):
    """Các điểm trên đường cong chữ U (dây chuyền)."""
    pts = []
    for i in range(count):
        t = i / (count - 1)
        x = cx - width / 2 + width * t
        y = top + depth * (1 - (2 * t - 1) ** 2)
        pts.append((x, y))
    return pts


def _chain(img, points, link, metal) -> None:
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    for i, (x, y) in enumerate(points):
        if i % 2 == 0:
            d.ellipse((x - link, y - link * 0.62, x + link, y + link * 0.62), outline=255, width=int(link * 0.45))
        else:
            d.ellipse((x - link * 0.5, y - link * 0.72, x + link * 0.5, y + link * 0.72), outline=255,
                      width=int(link * 0.4))
    _fill(img, mask, metal)


def _teardrop_mask(size, cx, cy, r, scale=1.0) -> Image.Image:
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    r *= scale
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    d.polygon([(cx - r * 0.93, cy - r * 0.35), (cx, cy - r * 2.1), (cx + r * 0.93, cy - r * 0.35)], fill=255)
    return mask


def _draw_sample(kind: str) -> Image.Image:
    img = _canvas(dark=True)
    w, h = img.size
    cx, cy = w / 2, h / 2
    s = SS
    if kind == "ring_24k":
        _shadow(img, (cx - 190 * s, cy + 120 * s, cx + 190 * s, cy + 175 * s))
        _ring(img, cx, cy, 160 * s, 46 * s, GOLD)
    elif kind == "ring_1luong":
        _shadow(img, (cx - 200 * s, cy + 125 * s, cx + 200 * s, cy + 185 * s))
        _ring(img, cx, cy, 165 * s, 64 * s, GOLD)
        _ring(img, cx, cy, 165 * s, 8 * s, ["#FFF8DC", "#F9DA7C", "#FFF3C4"])
    elif kind == "ring_18k_cz":
        _shadow(img, (cx - 170 * s, cy + 125 * s, cx + 170 * s, cy + 175 * s))
        _ring(img, cx, cy + 25 * s, 145 * s, 26 * s, GOLD)
        _gem_round_top(img, cx, cy - 118 * s, 44 * s, CZ)
        for dx in (-70, 70):
            _gem_round_top(img, cx + dx * s, cy - 98 * s, 16 * s, CZ)
    elif kind == "ring_diamond":
        _shadow(img, (cx - 170 * s, cy + 130 * s, cx + 170 * s, cy + 180 * s))
        _ring(img, cx, cy + 35 * s, 140 * s, 24 * s, WHITE_GOLD)
        prong = Image.new("L", img.size, 0)
        dp = ImageDraw.Draw(prong)
        for dx in (-44, -16, 16, 44):
            dp.rounded_rectangle((cx + dx * s - 6 * s, cy - 150 * s, cx + dx * s + 6 * s, cy - 92 * s),
                                 radius=5 * s, fill=255)
        _fill(img, prong, WHITE_GOLD)
        _gem_side(img, cx, cy - 140 * s, 130 * s, 120 * s, DIAMOND)
    elif kind == "wedding_rings":
        _shadow(img, (cx - 240 * s, cy + 110 * s, cx + 240 * s, cy + 170 * s))
        _ring(img, cx - 70 * s, cy, 125 * s, 30 * s, GOLD)
        _ring(img, cx + 80 * s, cy + 20 * s, 105 * s, 24 * s, WHITE_GOLD)
        _gem_round_top(img, cx + 80 * s, cy - 82 * s, 13 * s, CZ)
    elif kind in ("necklace_18k", "necklace_silver"):
        metal = GOLD if kind == "necklace_18k" else WHITE_GOLD
        pts = _chain_points(cx, 40 * s, 520 * s, 300 * s, 46)
        _chain(img, pts, 13 * s, metal)
        if kind == "necklace_silver":
            heart = Image.new("L", img.size, 0)
            dh = ImageDraw.Draw(heart)
            hx, hy, hr = cx, 380 * s, 34 * s
            dh.ellipse((hx - hr * 2, hy - hr, hx, hy + hr), fill=255)
            dh.ellipse((hx, hy - hr, hx + hr * 2, hy + hr), fill=255)
            dh.polygon([(hx - hr * 1.95, hy + hr * 0.3), (hx, hy + hr * 2.6), (hx + hr * 1.95, hy + hr * 0.3)],
                       fill=255)
            _fill(img, heart, WHITE_GOLD)
            _gem_round_top(img, hx, hy + 20 * s, 22 * s, CZ)
    elif kind in ("pendant_ruby", "pendant_sapphire"):
        gem = RUBY if kind == "pendant_ruby" else SAPPHIRE
        metal = GOLD if kind == "pendant_ruby" else WHITE_GOLD
        pts = _chain_points(cx, 20 * s, 440 * s, 190 * s, 60)
        _chain(img, pts, 6 * s, metal)
        gx, gy, gr = cx, 345 * s, 62 * s
        _shadow(img, (gx - 80 * s, gy + 50 * s, gx + 80 * s, gy + 90 * s), opacity=110)
        _fill(img, _teardrop_mask(img.size, gx, gy, gr, 1.18), metal)
        _fill(img, _teardrop_mask(img.size, gx, gy, gr, 1.0), gem, angle=70)
        _highlight(img, lambda dr: dr.ellipse((gx - gr * 0.55, gy - gr * 0.9, gx - gr * 0.1, gy - gr * 0.25),
                                              fill=255), blur=3, opacity=200)
        bail = Image.new("L", img.size, 0)
        ImageDraw.Draw(bail).ellipse((gx - 16 * s, gy - gr * 2.6 - 18 * s, gx + 16 * s, gy - gr * 2.4 + 14 * s),
                                     outline=255, width=8 * s)
        _fill(img, bail, metal)
    elif kind in ("bracelet_24k", "bracelet_silver"):
        metal = GOLD if kind == "bracelet_24k" else WHITE_GOLD
        _shadow(img, (cx - 250 * s, cy + 100 * s, cx + 250 * s, cy + 165 * s))
        pts = [(cx + math.cos(a) * 225 * s, cy + math.sin(a) * 110 * s)
               for a in [2 * math.pi * i / 64 for i in range(64)]]
        _chain(img, pts, 15 * s, metal)
        if kind == "bracelet_24k":
            for a in [2 * math.pi * i / 6 + 0.25 for i in range(6)]:
                fx, fy = cx + math.cos(a) * 225 * s, cy + math.sin(a) * 110 * s
                flower = Image.new("L", img.size, 0)
                df = ImageDraw.Draw(flower)
                for p in range(5):
                    pa = 2 * math.pi * p / 5 - math.pi / 2
                    px, py = fx + math.cos(pa) * 15 * s, fy + math.sin(pa) * 15 * s
                    df.ellipse((px - 12 * s, py - 12 * s, px + 12 * s, py + 12 * s), fill=255)
                _fill(img, flower, GOLD, angle=10)
                _gem_round_top(img, fx, fy, 7 * s, ["#FFF7D6", "#F2C14E", "#FFF7D6"])
    elif kind == "bangle_14k":
        _shadow(img, (cx - 250 * s, cy + 95 * s, cx + 250 * s, cy + 160 * s))
        mask = Image.new("L", img.size, 0)
        d = ImageDraw.Draw(mask)
        rx, ry, t = 235 * s, 125 * s, 42 * s
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
        d.ellipse((cx - rx + t, cy - ry + t * 0.55 - 10 * s, cx + rx - t, cy + ry - t * 0.95 - 10 * s), fill=0)
        _fill(img, mask, ROSE_GOLD[:2] + GOLD[1:5], angle=20)
        _highlight(img, lambda dr: dr.arc((cx - rx + 14 * s, cy - ry + 10 * s, cx + rx - 14 * s, cy + ry - 14 * s),
                                          195, 330, fill=255, width=9 * s))
    elif kind in ("earrings_pearl", "earrings_diamond"):
        for dx in (-110, 110):
            ex = cx + dx * s
            _shadow(img, (ex - 70 * s, cy + 150 * s, ex + 70 * s, cy + 185 * s), opacity=110)
            if kind == "earrings_pearl":
                hook = Image.new("L", img.size, 0)
                dh = ImageDraw.Draw(hook)
                dh.ellipse((ex - 22 * s, cy - 175 * s, ex + 22 * s, cy - 131 * s), fill=255)
                dh.line([(ex, cy - 140 * s), (ex, cy - 20 * s)], fill=255, width=7 * s)
                _fill(img, hook, GOLD)
                _gem_round_top(img, ex, cy - 153 * s, 14 * s, CZ)
                _pearl(img, ex, cy + 60 * s, 78 * s)
            else:
                setting = Image.new("L", img.size, 0)
                ImageDraw.Draw(setting).regular_polygon((ex, cy, 92 * s), 16, fill=255)
                _fill(img, setting, WHITE_GOLD)
                _gem_round_top(img, ex, cy, 78 * s, DIAMOND)
    else:
        raise ValueError(kind)
    return img.resize((W, H), Image.LANCZOS)


SAMPLE_KINDS = (
    "ring_24k", "ring_18k_cz", "necklace_18k", "bracelet_24k", "earrings_pearl", "bangle_14k",
    "ring_diamond", "pendant_ruby", "pendant_sapphire", "bracelet_silver", "ring_1luong",
    "wedding_rings", "earrings_diamond", "necklace_silver",
)


def _font(size: int):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_default_image() -> Image.Image:
    img = Image.new("RGB", (W * SS, H * SS), "#2A2A31")
    d = ImageDraw.Draw(img)
    cx, cy, s = W * SS / 2, H * SS / 2 - 30 * SS, SS
    gem = [(cx - 80 * s, cy - 20 * s), (cx - 45 * s, cy - 60 * s), (cx + 45 * s, cy - 60 * s), (cx + 80 * s, cy - 20 * s),
           (cx, cy + 75 * s)]
    d.polygon(gem, outline="#8C8778", width=5 * s)
    d.line([(cx - 80 * s, cy - 20 * s), (cx + 80 * s, cy - 20 * s)], fill="#8C8778", width=4 * s)
    d.line([(cx - 25 * s, cy - 60 * s), (cx, cy + 75 * s), (cx + 25 * s, cy - 60 * s)], fill="#8C8778", width=3 * s)
    text = "Chưa có hình ảnh"
    font = _font(30 * s)
    box = d.textbbox((0, 0), text, font=font)
    d.text((cx - (box[2] - box[0]) / 2, cy + 110 * s), text, fill="#A9A497", font=font)
    return img.resize((W, H), Image.LANCZOS)


def _draw_logo(size: int = 256) -> Image.Image:
    big = size * 4
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    disc = Image.new("L", img.size, 0)
    ImageDraw.Draw(disc).ellipse((8, 8, big - 8, big - 8), fill=255)
    img.paste(Image.new("RGBA", img.size, _hex("#16151A") + (255,)), (0, 0), disc)
    ring = Image.new("L", img.size, 0)
    ImageDraw.Draw(ring).ellipse((40, 40, big - 40, big - 40), outline=255, width=26)
    _fill(img, ring, GOLD)
    c = big / 2
    gem = Image.new("L", img.size, 0)
    pts = [(c - 300, c - 70), (c - 170, c - 250), (c + 170, c - 250), (c + 300, c - 70), (c, c + 310)]
    ImageDraw.Draw(gem).polygon(pts, outline=255, width=30)
    dg = ImageDraw.Draw(gem)
    dg.line([(c - 300, c - 70), (c + 300, c - 70)], fill=255, width=24)
    dg.line([(c - 90, c - 250), (c - 150, c - 70), (c, c + 310), (c + 150, c - 70), (c + 90, c - 250)],
            fill=255, width=20)
    dg.line([(c - 150, c - 70), (c, c - 250), (c + 150, c - 70)], fill=255, width=20)
    _fill(img, gem, GOLD, angle=60)
    return img.resize((size, size), Image.LANCZOS)


def ensure_default_images() -> None:
    """Tạo ảnh mặc định, logo và ảnh trang sức mẫu nếu chưa có (không ghi đè ảnh sẵn có)."""
    for folder in (config.IMAGES_DIR, config.SAMPLE_IMAGES_DIR, config.PRODUCT_IMAGES_DIR,
                   config.IMAGE_CACHE_DIR):
        folder.mkdir(parents=True, exist_ok=True)
    try:
        if not config.DEFAULT_IMAGE.exists():
            _draw_default_image().save(config.DEFAULT_IMAGE)
        if not config.LOGO_IMAGE.exists():
            _draw_logo().save(config.LOGO_IMAGE)
        for kind in SAMPLE_KINDS:
            target = config.SAMPLE_IMAGES_DIR / f"{kind}.png"
            if not target.exists():
                _draw_sample(kind).save(target, optimize=True)
    except OSError as exc:  # thiếu quyền ghi... -> phần mềm vẫn chạy với ảnh trống
        log.warning("Không thể tạo ảnh mẫu: %s", exc)
