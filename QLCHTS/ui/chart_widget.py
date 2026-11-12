"""Biểu đồ Matplotlib nhúng trực tiếp vào cửa sổ PySide6 (FigureCanvasQTAgg)."""
import matplotlib

matplotlib.use("QtAgg")

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402
from PySide6.QtWidgets import QSizePolicy  # noqa: E402

from ui.theme import ThemeManager  # noqa: E402
from utils.formatters import format_decimal  # noqa: E402

matplotlib.rcParams["font.family"] = "sans-serif"
matplotlib.rcParams["font.sans-serif"] = ["Segoe UI", "DejaVu Sans", "Arial"]
matplotlib.rcParams["font.size"] = 9
matplotlib.rcParams["axes.unicode_minus"] = False


def short_money(value, _pos=None) -> str:
    """Rút gọn số tiền trên trục: 1.250.000.000 -> '1,25 tỷ'; 12.500.000 -> '12,5 tr'."""
    value = float(value)
    if abs(value) >= 1e9:
        return f"{format_decimal(value / 1e9, 2)} tỷ"
    if abs(value) >= 1e6:
        return f"{format_decimal(value / 1e6, 1)} tr"
    if abs(value) >= 1e3:
        return f"{format_decimal(value / 1e3, 0)} k"
    return format_decimal(value, 0)


class ChartWidget(FigureCanvasQTAgg):
    def __init__(self, parent=None, min_height: int = 260):
        self.figure = Figure(figsize=(6, 3), layout="constrained")
        super().__init__(self.figure)
        if parent is not None:
            self.setParent(parent)
        self.setMinimumHeight(min_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._last = None  # (hàm vẽ, tham số) để vẽ lại khi đổi giao diện sáng/tối
        ThemeManager.instance().theme_changed.connect(self._replot)

    # ------------------------------------------------------------------ nội bộ
    @property
    def _p(self) -> dict:
        return ThemeManager.instance().palette

    def _replot(self, _mode=None) -> None:
        if self._last:
            func, args, kwargs = self._last
            func(*args, **kwargs)

    def _new_axes(self):
        p = self._p
        self.figure.clear()
        self.figure.set_facecolor(p["chart_bg"])
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(p["chart_bg"])
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(p["border_strong"])
        ax.tick_params(colors=p["text_muted"], labelsize=8.5)
        ax.grid(axis="y", color=p["chart_grid"], linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        return ax

    @staticmethod
    def _thin_labels(ax, labels: list[str], max_labels: int = 14) -> None:
        step = max(1, (len(labels) + max_labels - 1) // max_labels)
        positions = list(range(0, len(labels), step))
        ax.set_xticks(positions)
        ax.set_xticklabels([labels[i] for i in positions], rotation=0)

    # ------------------------------------------------------------------ vẽ
    def show_empty(self, message: str = "Chưa có dữ liệu trong khoảng thời gian đã chọn") -> None:
        self._last = (self.show_empty, (message,), {})
        p = self._p
        self.figure.clear()
        self.figure.set_facecolor(p["chart_bg"])
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(p["chart_bg"])
        ax.axis("off")
        ax.text(0.5, 0.56, "◇", ha="center", va="center", fontsize=30, color=p["gold"], transform=ax.transAxes)
        ax.text(0.5, 0.38, message, ha="center", va="center", fontsize=10, color=p["text_muted"],
                transform=ax.transAxes, wrap=True)
        self.draw_idle()

    def plot_revenue(self, labels: list[str], revenues: list[float], counts: list[int] | None = None,
                     kind: str = "bar") -> None:
        """Doanh thu (cột hoặc đường) kèm số giao dịch trên trục phụ."""
        self._last = (self.plot_revenue, (labels, revenues, counts), {"kind": kind})
        if not labels or not any(revenues):
            self.show_empty()
            self._last = (self.plot_revenue, (labels, revenues, counts), {"kind": kind})
            return
        p = self._p
        ax = self._new_axes()
        x = list(range(len(labels)))
        if kind == "line":
            ax.plot(x, revenues, color=p["gold"], linewidth=2.2, marker="o", markersize=4, zorder=3,
                    label="Doanh thu")
            ax.fill_between(x, revenues, color=p["gold"], alpha=0.14, zorder=2)
        else:
            ax.bar(x, revenues, color=p["gold"], width=0.62, zorder=3, label="Doanh thu")
        ax.yaxis.set_major_formatter(FuncFormatter(short_money))
        ax.set_ylim(bottom=0)
        ax.set_xlim(-0.6, len(labels) - 0.4)
        self._thin_labels(ax, labels)
        ax.set_ylabel("Doanh thu (VNĐ)", color=p["text_muted"], fontsize=8.5)
        handles, names = ax.get_legend_handles_labels()
        if counts is not None:
            ax2 = ax.twinx()
            ax2.plot(x, counts, color=p["teal"], linewidth=1.6, marker="o", markersize=3.5, zorder=4,
                     label="Số giao dịch")
            ax2.yaxis.set_major_locator(MaxNLocator(integer=True))
            ax2.set_ylim(bottom=0, top=max(max(counts) * 1.3, 1))
            ax2.tick_params(colors=p["text_muted"], labelsize=8.5)
            for side in ("top", "left", "bottom"):
                ax2.spines[side].set_visible(False)
            ax2.spines["right"].set_color(p["border_strong"])
            ax2.set_ylabel("Số giao dịch", color=p["text_muted"], fontsize=8.5)
            h2, n2 = ax2.get_legend_handles_labels()
            handles, names = handles + h2, names + n2
        legend = ax.legend(handles, names, loc="upper left", frameon=False, fontsize=8.5)
        for text in legend.get_texts():
            text.set_color(p["text_muted"])
        self.draw_idle()

    def plot_hbar(self, labels: list[str], values: list[float], value_suffix: str = "") -> None:
        """Biểu đồ thanh ngang (sản phẩm bán chạy)."""
        self._last = (self.plot_hbar, (labels, values), {"value_suffix": value_suffix})
        if not labels:
            self.show_empty("Chưa có sản phẩm nào được bán trong khoảng thời gian này")
            self._last = (self.plot_hbar, (labels, values), {"value_suffix": value_suffix})
            return
        p = self._p
        ax = self._new_axes()
        ax.grid(axis="x", color=p["chart_grid"], linewidth=0.8)
        ax.grid(axis="y", visible=False)
        short = [label if len(label) <= 34 else label[:32] + "…" for label in labels]
        y = list(range(len(labels)))[::-1]
        colors = [p["gold"] if i == 0 else p["teal"] for i in range(len(labels))]
        bars = ax.barh(y, values, color=colors, height=0.6, zorder=3)
        ax.set_yticks(y)
        ax.set_yticklabels(short)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        for bar, value in zip(bars, values):
            ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f"  {format_decimal(value)}{value_suffix}",
                    va="center", fontsize=8.5, color=p["text"])
        ax.set_xlim(0, max(values) * 1.18 if values else 1)
        self.draw_idle()

    def plot_donut(self, labels: list[str], values: list[float]) -> None:
        """Biểu đồ vành khuyên tỷ trọng doanh số theo danh mục."""
        self._last = (self.plot_donut, (labels, values), {})
        if not labels or not any(values):
            self.show_empty()
            self._last = (self.plot_donut, (labels, values), {})
            return
        p = self._p
        self.figure.clear()
        self.figure.set_facecolor(p["chart_bg"])
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(p["chart_bg"])
        palette = [p["gold"], p["teal"], p["rose"], p["sky"], p["warning"], p["gold_dark"], p["text_muted"],
                   p["success"], p["danger"]]
        total = sum(values)
        wedges, _ = ax.pie(values, colors=palette[:len(values)], startangle=90, counterclock=False,
                           wedgeprops={"width": 0.38, "edgecolor": p["chart_bg"], "linewidth": 2})
        ax.text(0, 0.08, short_money(total), ha="center", va="center", fontsize=13, fontweight="bold",
                color=p["text"])
        ax.text(0, -0.16, "Tổng doanh số", ha="center", va="center", fontsize=8.5, color=p["text_muted"])
        legend = ax.legend(wedges, [f"{lbl} ({v / total * 100:.1f}%)".replace(".", ",") for lbl, v in
                                    zip(labels, values)],
                           loc="center left", bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=8.5)
        for text in legend.get_texts():
            text.set_color(p["text"])
        ax.set_aspect("equal")
        self.draw_idle()
