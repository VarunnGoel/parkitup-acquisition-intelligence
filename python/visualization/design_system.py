"""Design tokens and layout primitives for the Power BI page previews.

the dashboard redesign introduced this module to fix one defect class that produced most of
the visual problems in the dashboard previews: charts were drawn directly into
the panel rectangle, so matplotlib rendered tick labels, axis labels and
legends *outside* that rectangle and they collided with neighbouring panels.

The rule enforced here is: a card is a background surface with its own axis
switched off, and every chart lives in an inset axes with explicit padding.
Anything matplotlib draws outside the plot box therefore lands on the card's
own padding instead of the next card.

Colour is semantic only. The four priority-segment colours come from
`DimPrioritySegment.segment_colour_hex`, so the dashboard, the theme file and
the data model cannot drift apart. No chart may introduce a decorative hue.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

# --- Ink and surfaces ---------------------------------------------------------
INK = "#1B2027"
INK_MUTED = "#69737F"
INK_FAINT = "#98A2AD"
BG = "#EDF0F3"
SURFACE = "#FFFFFF"
BORDER = "#DCE1E6"
ZEBRA = "#F5F7F9"

# --- Semantic palette (mirrors DimPrioritySegment.segment_colour_hex) ---------
PRIMARY = "#0B6E4F"      # positive / Acquire Now / brand
ACCENT = "#2563EB"       # accent / Develop
WARNING = "#D97706"      # warning / Pursue / constraint
NEUTRAL = "#6B7280"      # neutral / Avoid
NEGATIVE = "#B3261E"     # reserved for loss and drop-off only

PRIMARY_WASH = "#E4F0EA"
ACCENT_WASH = "#E7EEFD"
WARNING_WASH = "#FDF0DC"
NEUTRAL_WASH = "#F0F1F3"

SEGMENT_COLOURS = {
    "ACQUIRE_NOW": PRIMARY,
    "PURSUE": WARNING,
    "DEVELOP": ACCENT,
    "AVOID": NEUTRAL,
}
SEGMENT_WASHES = {
    "ACQUIRE_NOW": PRIMARY_WASH,
    "PURSUE": WARNING_WASH,
    "DEVELOP": ACCENT_WASH,
    "AVOID": NEUTRAL_WASH,
}
SEGMENT_ORDER = ["ACQUIRE_NOW", "PURSUE", "DEVELOP", "AVOID"]

# --- Type scale ---------------------------------------------------------------
T_PAGE_TITLE = 19.0
T_PAGE_QUESTION = 10.0
T_CARD_TITLE = 9.8
T_CARD_NOTE = 7.0
T_KPI_VALUE = 17.0
T_KPI_VALUE_SM = 12.5
T_KPI_LABEL = 7.3
T_BODY = 8.3
T_TABLE = 7.4
T_TABLE_HEAD = 6.9
T_TICK = 7.2
T_MICRO = 6.6

FONT_STACK = ["Lato", "Carlito", "DejaVu Sans"]

# --- Canvas geometry ---------------------------------------------------------
# A horizontal top nav is used rather than a left rail: the rail spent about an
# eighth of a 16:9 screen on four words, and the analytics need the width.
GUTTER = 0.008
CONTENT_L = 0.012
CONTENT_R = 0.988
BAND_TOP = 0.848        # below the nav strip
BAND_BOTTOM = 0.040     # above the source strip
HEADER_BOTTOM = 0.906   # title band sits above the nav strip

NAV_ITEMS = [
    "Overview",
    "Markets",
    "Acquisition",
    "Deep Dive",
    "BD Action",
]

GRID_COLS = 12
GRID_ROWS = 24


def apply_base_style() -> None:
    """Set the global matplotlib defaults every page inherits."""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": FONT_STACK,
            "text.color": INK,
            "axes.labelcolor": INK_MUTED,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "axes.edgecolor": BORDER,
            "axes.linewidth": 0.7,
            "xtick.major.size": 0,
            "ytick.major.size": 0,
            "xtick.major.pad": 3,
            "ytick.major.pad": 3,
            "legend.frameon": False,
            "figure.dpi": 120,
            "savefig.dpi": 120,
        }
    )


def rect(col: float, span_col: float, row: float, span_row: float) -> list[float]:
    """Return a figure-coordinate rect from a 12x24 content grid.

    `row` is counted downwards from the top of the content band, which matches
    how the page layouts are described in `dashboard/powerbi/page_*.md`.
    """
    unit_w = (CONTENT_R - CONTENT_L - GUTTER * (GRID_COLS - 1)) / GRID_COLS
    unit_h = (BAND_TOP - BAND_BOTTOM - GUTTER * (GRID_ROWS - 1)) / GRID_ROWS
    x = CONTENT_L + col * (unit_w + GUTTER)
    width = span_col * unit_w + (span_col - 1) * GUTTER
    height = span_row * unit_h + (span_row - 1) * GUTTER
    y = BAND_TOP - row * (unit_h + GUTTER) - height
    return [x, y, width, height]


def page(title: str, question: str, active: int, context: str = "Delhi NCR  ·  all parking types") -> Figure:
    """Create a 16:9 page with the title band and horizontal nav strip drawn."""
    apply_base_style()
    fig = plt.figure(figsize=(16, 9), facecolor=BG)

    header = fig.add_axes((0.0, HEADER_BOTTOM, 1.0, 1.0 - HEADER_BOTTOM))
    _blank(header, SURFACE)
    header.text(CONTENT_L, 0.66, "PARK It Up", color=INK, fontsize=15.0, fontweight="bold", va="center")
    header.text(CONTENT_L, 0.27, "ACQUISITION INTELLIGENCE", color=INK_FAINT, fontsize=6.2, va="center")
    header.plot([0.112, 0.112], [0.20, 0.80], color=BORDER, linewidth=0.9)
    header.text(0.126, 0.66, title, color=INK, fontsize=T_PAGE_TITLE, fontweight="bold", va="center")
    header.text(0.126, 0.26, question, color=INK_MUTED, fontsize=T_PAGE_QUESTION, va="center")
    header.text(CONTENT_R, 0.66, context, color=INK, fontsize=8.0, ha="right", va="center")

    nav = fig.add_axes((0.0, BAND_TOP + 0.006, 1.0, HEADER_BOTTOM - BAND_TOP - 0.006))
    _blank(nav, SURFACE)
    nav.plot([0.0, 1.0], [0.995, 0.995], color=BORDER, linewidth=0.9)
    for index, item in enumerate(NAV_ITEMS):
        x = CONTENT_L + index * 0.088
        current = index == active
        nav.text(
            x, 0.52, item,
            color=PRIMARY if current else INK_MUTED,
            fontsize=8.4, va="center",
            fontweight="bold" if current else "normal",
        )
        if current:
            width = 0.0062 * len(item)
            nav.add_patch(Rectangle((x, 0.10), width, 0.075, color=PRIMARY))
    nav.text(CONTENT_R, 0.52, "BASE CASE WEIGHTS   30 / 25 / 15 / 15 / 15",
             color=INK_MUTED, fontsize=7.0, ha="right", va="center")
    return fig


def _blank(ax: Axes, facecolor: str) -> Axes:
    ax.set_facecolor(facecolor)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return ax


def card(
    fig: Figure,
    box: list[float],
    title: str | None = None,
    note: str | None = None,
    facecolor: str = SURFACE,
) -> Axes:
    """Draw a card surface. The returned axes has no ticks; use `plot_area`."""
    ax = fig.add_axes(tuple(box))
    _blank(ax, facecolor)
    ax.set_label("card")  # layout_audit.py uses this to find card bounds
    ax.add_patch(
        Rectangle(
            (0, 0), 1, 1, transform=ax.transAxes, facecolor="none",
            edgecolor=BORDER, linewidth=0.8, zorder=0,
        )
    )
    height_in = box[3] * 9.0
    title_y = 1.0 - (0.20 / height_in)
    if title:
        ax.text(0.018, title_y, title, fontsize=T_CARD_TITLE, fontweight="bold", color=INK, va="center")
    if note:
        ax.text(0.982, title_y, note, fontsize=T_CARD_NOTE, color=INK_FAINT, ha="right", va="center")
    return ax


def plot_area(
    host: Axes,
    left: float = 0.075,
    bottom: float = 0.13,
    right: float = 0.025,
    top: float = 0.16,
) -> Axes:
    """Inset plot axes. Padding is what keeps tick labels inside the card."""
    ax = host.inset_axes((left, bottom, 1 - left - right, 1 - bottom - top))
    ax.set_facecolor("none")
    ax.tick_params(labelsize=T_TICK, length=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BORDER)
    return ax


def bare(ax: Axes) -> Axes:
    """Strip every frame element - used for value-labelled ranking bars."""
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    return ax


def kpi_strip(fig: Figure, box: list[float], items: list[tuple[str, str, str]], accents: list[str] | None = None) -> Axes:
    """One card holding 3-5 aligned KPI cells separated by hairline dividers.

    A single strip replaces the dashboard row of separately bordered cards, each
    of which carried its own accent colour and produced a rainbow header.
    """
    ax = card(fig, box)
    count = len(items)
    for index, (label, value, note) in enumerate(items):
        left = index / count
        if index:
            ax.plot([left, left], [0.16, 0.84], color=BORDER, linewidth=0.8)
        pad = 0.028 / count * 4
        colour = INK if accents is None else accents[index]
        size = T_KPI_VALUE if len(value) <= 9 else T_KPI_VALUE_SM
        ax.text(left + pad, 0.74, label.upper(), fontsize=T_KPI_LABEL, color=INK_MUTED, va="center")
        ax.text(left + pad, 0.44, value, fontsize=size, fontweight="bold", color=colour, va="center")
        ax.text(left + pad, 0.17, note, fontsize=T_MICRO, color=INK_FAINT, va="center")
    return ax


def data_table(
    host: Axes,
    headers: list[str],
    xs: list[float],
    aligns: list[str],
    rows: list[list[str]],
    colours: list[list[str]] | None = None,
    weights: list[list[str]] | None = None,
    top: float = 0.72,
    bottom: float = 0.06,
    fontsize: float = T_TABLE,
) -> None:
    """Render a zebra-striped table with evenly distributed row heights."""
    for x, header, align in zip(xs, headers, aligns):
        host.text(x, top + 0.075, header, fontsize=T_TABLE_HEAD, color=INK_MUTED,
                  fontweight="bold", ha=align, va="center")
    host.plot([0.018, 0.982], [top + 0.035, top + 0.035], color=BORDER, linewidth=0.8)
    step = (top - bottom) / max(len(rows), 1)
    for index, row in enumerate(rows):
        y = top - step * (index + 0.5)
        if index % 2 == 0:
            host.add_patch(Rectangle((0.018, y - step / 2), 0.964, step, color=ZEBRA, zorder=0))
        for column, (x, value, align) in enumerate(zip(xs, row, aligns)):
            host.text(
                x, y, value, fontsize=fontsize, ha=align, va="center",
                color=INK if colours is None else colours[index][column],
                fontweight="normal" if weights is None else weights[index][column],
            )


def chip_legend(
    host: Axes,
    entries: list[tuple[str, str]],
    y: float,
    x: float = 0.018,
    step: float = 0.115,
    fontsize: float = T_MICRO,
    ha: str = "left",
) -> None:
    """Inline swatch legend placed in reserved card padding, never over a plot."""
    cursor = x
    for label, colour in entries:
        host.add_patch(Rectangle((cursor, y - 0.011), 0.0115, 0.022, color=colour, clip_on=False))
        host.text(cursor + 0.019, y, label, fontsize=fontsize, color=INK_MUTED, va="center", ha=ha)
        cursor += step


def inr_lakh(value: float) -> str:
    """Every rupee figure on the dashboard uses one unit so columns compare."""
    return f"{float(value) / 100_000:.2f}L"


def inr_headline(value: float) -> str:
    value = float(value)
    if abs(value) >= 10_000_000:
        return f"INR {value / 10_000_000:.2f} Cr"
    return f"INR {value / 100_000:.1f} L"


def source_strip(fig: Figure, page_number: int, note: str) -> None:
    fig.text(CONTENT_L, 0.019, note, fontsize=T_MICRO, color=INK_FAINT)
    fig.text(CONTENT_R, 0.019, f"{page_number} / 5", fontsize=T_MICRO, color=INK_FAINT, ha="right")


def save(fig: Figure, path) -> str:
    fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches=None)
    plt.close(fig)
    return str(path)


def fit_geo_extent(fig: Figure, ax: Axes, lons, lats, pad: float = 0.10) -> None:
    """Give a lat/lon scatter a true equirectangular aspect with no letterbox.

    The visible window is expanded on whichever axis has slack so the plot box
    is filled completely while one degree of latitude keeps the same on-screen
    length as one degree of longitude at this latitude.
    """
    import numpy as np

    lon_lo, lon_hi = float(np.min(lons)), float(np.max(lons))
    lat_lo, lat_hi = float(np.min(lats)), float(np.max(lats))
    lon_mid, lat_mid = (lon_lo + lon_hi) / 2, (lat_lo + lat_hi) / 2
    scale = float(np.cos(np.deg2rad(lat_mid)))  # on-screen shrink of one lon degree
    lon_span = (lon_hi - lon_lo) * (1 + 2 * pad)
    lat_span = (lat_hi - lat_lo) * (1 + 2 * pad)
    box = ax.get_window_extent(fig.canvas.get_renderer())
    box_ratio = box.width / box.height
    if lon_span * scale / lat_span < box_ratio:
        lon_span = lat_span * box_ratio / scale
    else:
        lat_span = lon_span * scale / box_ratio
    ax.set_xlim(lon_mid - lon_span / 2, lon_mid + lon_span / 2)
    ax.set_ylim(lat_mid - lat_span / 2, lat_mid + lat_span / 2)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
