"""Generate the five Power BI page previews from the actual project data.

These are implementation previews, not screenshots of a PBIX file: Power BI
Desktop is unavailable in this environment, so page design, field mapping,
number formatting and visual hierarchy are made reviewable by rendering the
same measures onto the same 16:9 canvas. Every figure shown is read from
`data/powerbi/*.csv`, which `python/analysis/prepare_powerbi.py` reconciles
against the PostgreSQL views.

Layout primitives live in `design_system`; this module contains only page
composition, so a layout defect is fixed once rather than five times.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from python.config import REPO_ROOT
from python.visualization import design_system as ds

DATA_DIR = REPO_ROOT / "data" / "powerbi"
OUTPUT_DIR = REPO_ROOT / "dashboard" / "powerbi" / "screenshots"

SOURCE_NOTE = (
    "Modelled 120-lot Delhi NCR dataset  ·  operational and economic figures are synthetic, not observed"
)

SEGMENT_LABELS = {
    "ACQUIRE_NOW": "Acquire Now",
    "PURSUE": "Pursue",
    "DEVELOP": "Develop",
    "AVOID": "Avoid",
}
SEGMENT_LEGEND = [(SEGMENT_LABELS[code], ds.SEGMENT_COLOURS[code]) for code in ds.SEGMENT_ORDER]

# Segmentation cuts are read from DimPrioritySegment at render time rather than
# restated here. They are recalibrated from the observed score distribution on
# every scoring run, so a hard-coded copy would silently draw the quadrant washes
# in the wrong place the first time the distribution moved. Populated by
# read_model(); the module-level values are only a fallback for a direct import.
ATTRACTIVENESS_CUT = 46.66
FEASIBILITY_CUT = 57.55
DEVELOP_FLOOR = 33.42


def _refresh_segment_cuts(segment: pd.DataFrame) -> None:
    """Bind the quadrant thresholds to what DimPrioritySegment actually records."""
    global ATTRACTIVENESS_CUT, FEASIBILITY_CUT, DEVELOP_FLOOR
    rules = segment.set_index("segment_code")
    ATTRACTIVENESS_CUT = float(rules.loc["ACQUIRE_NOW", "min_attractiveness"])
    FEASIBILITY_CUT = float(rules.loc["ACQUIRE_NOW", "min_feasibility"])
    DEVELOP_FLOOR = float(rules.loc["DEVELOP", "min_attractiveness"])


def _load(name: str, **kwargs: object) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run: make powerbi-data")
    return pd.read_csv(path, **kwargs)


def read_model() -> dict[str, pd.DataFrame]:
    model = {
        "parking": _load("DimParking"),
        "locality": _load("DimLocality"),
        "score": _load("FactAcquisitionScore"),
        "component": _load("FactScoreComponent"),
        "dimension": _load("DimScoreDimension"),
        "segment": _load("DimPrioritySegment"),
        "hourly": _load("FactHourlyProfile"),
        "outreach": _load("FactOutreach"),
        "funnel": _load("AggBDFunnel"),
    }
    _refresh_segment_cuts(model["segment"])
    return model


def joined(model: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return (
        model["parking"]
        .merge(model["score"], on="parking_id", validate="one_to_one")
        .merge(
            model["locality"][["locality_id", "locality_name", "market_class"]],
            on="locality_id",
            validate="many_to_one",
        )
    )


def _short(text: object, width: int) -> str:
    return textwrap.shorten(str(text), width=width, placeholder="...")


def lot_label(name: object, width: int = 34) -> str:
    """Shorten a lot label for a table cell.

    Business-facing pages now read `parking_display_name`, which DimParking
    derives from the OSM name where one exists and otherwise from parking type
    plus locality. The legacy branch below stays because `lot_name` is still the
    raw source column, and a page rendered against an extract built before that
    change would otherwise print "OSM Parking node-786590777" verbatim.
    """
    text = str(name)
    if text.startswith("OSM Parking "):
        kind, _, ident = text.replace("OSM Parking ", "").partition("-")
        if ident:
            return f"OSM {kind} {ident}"
    return _short(text, width)


def place_labels(fig, ax, points: list[tuple[float, float, str, bool]], fontsize: float = 7.1) -> None:
    """Annotate map clusters, choosing the first offset that avoids a collision.

    The synthetic localities sit close together in central Delhi, so fixed
    offsets hid the largest market behind its neighbour.
    """
    vertical = [(0, 15), (0, -19), (0, 30), (0, -34), (0, 46), (0, -50)]
    box_axes = ax.get_window_extent(fig.canvas.get_renderer())
    placed: list[tuple[float, float, float, float]] = []
    for lon, lat, text, emphasise in points:
        x, y = ax.transData.transform((lon, lat))
        half_w, half_h = len(text) * 2.9 + 6, 9.0
        # Points hugging a plot edge get a sideways label so the box stays inside.
        near_left = x - box_axes.x0 < half_w + 12
        near_right = box_axes.x1 - x < half_w + 12
        if near_left:
            candidates = [(half_w + 9, 0), (half_w + 9, 17), (half_w + 9, -17)] + vertical
        elif near_right:
            candidates = [(-half_w - 9, 0), (-half_w - 9, 17), (-half_w - 9, -17)] + vertical
        else:
            candidates = vertical
        chosen = candidates[-1]
        for dx, dy in candidates:
            box = (x + dx - half_w, x + dx + half_w, y + dy - half_h, y + dy + half_h)
            if all(box[1] < o[0] or box[0] > o[1] or box[3] < o[2] or box[2] > o[3] for o in placed):
                chosen = (dx, dy)
                placed.append(box)
                break
        else:
            placed.append((x + chosen[0] - half_w, x + chosen[0] + half_w,
                           y + chosen[1] - half_h, y + chosen[1] + half_h))
        ax.annotate(
            text, (lon, lat), xytext=chosen, textcoords="offset points",
            fontsize=fontsize, fontweight="bold" if emphasise else "normal",
            color=ds.INK, ha="center", va="center", zorder=6,
            bbox=dict(boxstyle="round,pad=0.28", facecolor="white",
                      edgecolor=ds.BORDER, linewidth=0.6),
        )




# ---------------------------------------------------------------------------
# Page 1 - Executive Overview: where is the biggest acquisition opportunity?
# ---------------------------------------------------------------------------
def page_01(model: dict[str, pd.DataFrame]) -> str:
    data = joined(model)
    locality = model["locality"]
    acquire = data[data.priority_segment.eq("ACQUIRE_NOW")]

    fig = ds.page("Executive Overview", "Where is the biggest acquisition opportunity?", 0)

    ds.kpi_strip(
        fig,
        ds.rect(0, 12, 0, 3),
        [
            ("Acquire Now targets", f"{len(acquire)}", f"of {len(data)} lots scored"),
            ("Revenue at stake", ds.inr_headline(acquire.expected_monthly_platform_revenue_inr.sum()),
             "modelled monthly, Acquire Now only"),
            ("High-opportunity markets", f"{int(locality.market_class.eq('STRONG').sum())}",
             f"of {len(locality)} localities"),
            ("Candidate universe", f"{int(data.capacity_cars.sum()):,}",
             f"car spaces · avg score {data.acquisition_score.mean():.1f}/100"),
        ],
        accents=[ds.PRIMARY, ds.PRIMARY, ds.INK, ds.INK],
    )

    # --- Primary visual: geographic concentration --------------------------
    map_card = ds.card(fig, ds.rect(0, 6, 3, 21), "Where the opportunity sits",
                       note="bubble size = capacity")
    map_ax = map_card.inset_axes((0.025, 0.075, 0.95, 0.845))
    map_ax.set_facecolor("#F7F9FB")
    for code in ds.SEGMENT_ORDER:
        group = data[data.priority_segment.eq(code)]
        map_ax.scatter(
            group.longitude, group.latitude,
            s=np.sqrt(group.capacity_cars) * 8.5,
            color=ds.SEGMENT_COLOURS[code],
            alpha=0.55 if code == "AVOID" else 0.90,
            edgecolor="white", linewidth=0.6,
            zorder=4 if code == "ACQUIRE_NOW" else 2,
        )
    ds.fit_geo_extent(fig, map_ax, data.longitude, data.latitude, pad=0.09)
    labels = []
    for row in locality.nlargest(5, "high_priority_count").itertuples():
        lots = data[data.locality_id.eq(row.locality_id)]
        labels.append((
            float(lots.longitude.mean()), float(lots.latitude.mean()),
            f"{row.locality_name}  ·  {int(row.high_priority_count)}",
            bool(row.high_priority_count >= 4),
        ))
    place_labels(fig, map_ax, labels)
    ds.chip_legend(map_card, SEGMENT_LEGEND, y=0.030, step=0.145)
    map_card.text(0.982, 0.030, "number = Acquire Now targets in that market",
                  fontsize=ds.T_MICRO, color=ds.INK_FAINT, ha="right", va="center")

    # --- Secondary: the shortlist ------------------------------------------
    top_card = ds.card(fig, ds.rect(6, 6, 3, 10), "Strongest targets today",
                       note="ranked by acquisition score")
    top = data.nsmallest(6, "acquisition_rank")
    rows, colours, weights = [], [], []
    for row in top.itertuples():
        rows.append([
            str(int(row.acquisition_rank)),
            lot_label(row.parking_display_name),
            str(row.locality_name),
            f"{row.acquisition_score:.1f}",
            ds.inr_lakh(row.expected_monthly_platform_revenue_inr),
        ])
        colours.append([ds.INK_FAINT, ds.INK, ds.INK_MUTED, ds.SEGMENT_COLOURS[row.priority_segment], ds.INK])
        weights.append(["normal", "normal", "normal", "bold", "normal"])
    ds.data_table(
        top_card,
        ["#", "Parking lot", "Locality", "Score", "INR L / mo"],
        [0.030, 0.075, 0.480, 0.790, 0.968],
        ["left", "left", "left", "right", "right"],
        rows, colours, weights, top=0.72, bottom=0.11,
    )
    top_card.text(0.030, 0.045, f"All six are Acquire Now · full {len(data)}-lot ranking on the Acquisition page",
                  fontsize=ds.T_MICRO, color=ds.INK_FAINT)

    # --- Supporting: portfolio shape as one stacked strip -------------------
    mix_card = ds.card(fig, ds.rect(6, 6, 13, 4), "Portfolio shape")
    mix_ax = mix_card.inset_axes((0.030, 0.30, 0.940, 0.26))
    counts = data.priority_segment.value_counts().reindex(ds.SEGMENT_ORDER)
    left = 0.0
    for code in ds.SEGMENT_ORDER:
        value = int(counts[code])
        mix_ax.barh([0], [value], left=[left], color=ds.SEGMENT_COLOURS[code], height=1.0)
        if value >= 12:
            mix_ax.text(left + value / 2, 0, f"{value}", color="white", fontsize=7.8,
                        fontweight="bold", ha="center", va="center")
        left += value
    mix_ax.set_xlim(0, len(data))
    mix_ax.set_ylim(-0.5, 0.5)
    mix_ax.axis("off")
    ds.chip_legend(mix_card, SEGMENT_LEGEND, y=0.135, step=0.145)
    mix_card.text(0.982, 0.135, f"{len(acquire)} of {len(data)} lots justify BD capacity",
                  fontsize=ds.T_MICRO, color=ds.INK_FAINT, ha="right", va="center")

    # --- Supporting: three findings, stacked -------------------------------
    take_card = ds.card(fig, ds.rect(6, 6, 17, 7), "What the analysis says")
    top4 = locality.nlargest(4, "high_priority_count")
    attractive = data[data.attractiveness_score >= ATTRACTIVENESS_CUT]
    blocked = int((attractive.feasibility_score < FEASIBILITY_CUT).sum())
    findings = [
        (f"{int(top4.high_priority_count.sum())} of {len(acquire)}",
         f"Acquire Now targets sit in {', '.join(top4.locality_name.head(3))} and "
         f"{top4.locality_name.iloc[3]}. Concentrate BD effort, do not spread it."),
        (f"{blocked} of {len(attractive)}",
         "commercially attractive lots fail the feasibility bar: they need owner and "
         "documentation work before any commercial conversation."),
        (f"{data.nsmallest(10, 'acquisition_rank').top_10_frequency_pct.mean():.0f}%",
         "average top-10 persistence for the current top 10 across 11 demand, cost and "
         "weighting scenarios. The shortlist survives re-weighting."),
    ]
    for index, (headline, detail) in enumerate(findings):
        y = 0.66 - index * 0.245
        take_card.text(0.028, y, headline, fontsize=12.5, fontweight="bold", color=ds.PRIMARY, va="center")
        take_card.text(0.215, y, "\n".join(textwrap.wrap(detail, 74)), fontsize=7.6,
                       color=ds.INK, va="center", linespacing=1.5)
        if index:
            take_card.plot([0.028, 0.972], [y + 0.122, y + 0.122], color=ds.BORDER, linewidth=0.7)

    ds.source_strip(fig, 1, SOURCE_NOTE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return ds.save(fig, OUTPUT_DIR / "page_01_executive_overview.png")


# ---------------------------------------------------------------------------
# Page 2 - Market Opportunity: which markets should PARK It Up expand in?
# ---------------------------------------------------------------------------
def page_02(model: dict[str, pd.DataFrame]) -> str:
    locality = model["locality"].copy()
    data = joined(model)
    leader = locality.nlargest(1, "avg_acquisition_score").iloc[0]
    top4 = locality.nlargest(4, "high_priority_count")
    total_targets = int(locality.high_priority_count.sum())
    no_presence = int(locality.parkitup_coverage_pct.eq(0).sum())

    fig = ds.page("Market Opportunity", "Which markets should PARK It Up expand in?", 1)

    ds.kpi_strip(
        fig,
        ds.rect(0, 12, 0, 3),
        [
            ("Markets scored", f"{len(locality)}",
             f"{int(locality.market_class.eq('STRONG').sum())} strong · "
             f"{int(locality.market_class.eq('EMERGING').sum())} emerging · "
             f"{int(locality.market_class.eq('SATURATED').sum())} saturated · "
             f"{int(locality.market_class.eq('WEAK').sum())} weak"),
            ("Strongest market", str(leader.locality_name),
             f"opportunity score {leader.avg_acquisition_score:.1f} · "
             f"{int(leader.high_priority_count)} Acquire Now targets"),
            ("Target concentration", f"{top4.high_priority_count.sum() / total_targets * 100:.0f}%",
             f"of Acquire Now targets in {len(top4)} of {len(locality)} markets"),
            ("Untouched markets", f"{no_presence}",
             "with no modelled PARK It Up presence"),
        ],
        accents=[ds.INK, ds.PRIMARY, ds.PRIMARY, ds.INK],
    )

    strong = locality.market_class.eq("STRONG")
    point_colour = np.where(strong, ds.PRIMARY, ds.NEUTRAL)

    # --- Primary visual: demand against existing coverage -------------------
    quad_card = ds.card(fig, ds.rect(0, 7, 3, 13), "Demand against current coverage",
                        note="bubble size = parking lots in market")
    quad_ax = ds.plot_area(quad_card, left=0.068, bottom=0.155, right=0.022, top=0.175)
    x_cut = float(locality.parkitup_coverage_pct.median())
    y_cut = float(locality.avg_demand_score.median())
    x_hi = float(locality.parkitup_coverage_pct.max()) * 1.16
    y_hi = float(locality.avg_demand_score.max()) * 1.12
    quad_ax.set_xlim(-1.0, x_hi)
    quad_ax.set_ylim(5, y_hi)
    for (x0, x1, y0, y1, wash) in [
        (-1.0, x_cut, y_cut, y_hi, ds.PRIMARY_WASH),
        (x_cut, x_hi, y_cut, y_hi, ds.ACCENT_WASH),
        (-1.0, x_cut, 5, y_cut, "#F7F8F9"),
        (x_cut, x_hi, 5, y_cut, ds.WARNING_WASH),
    ]:
        quad_ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, color=wash, zorder=0))
    quad_ax.axvline(x_cut, color=ds.INK_FAINT, linestyle=(0, (4, 3)), linewidth=0.8, zorder=1)
    quad_ax.axhline(y_cut, color=ds.INK_FAINT, linestyle=(0, (4, 3)), linewidth=0.8, zorder=1)
    quad_ax.scatter(
        locality.parkitup_coverage_pct, locality.avg_demand_score,
        s=locality.parking_count * 22 + 40, color=point_colour,
        alpha=0.90, edgecolor="white", linewidth=0.7, zorder=3,
    )
    corners = [
        (0.02, 0.955, "EXPAND", ds.PRIMARY, "left"),
        (0.98, 0.955, "PRIORITISE", ds.ACCENT, "right"),
        (0.02, 0.035, "MONITOR", ds.INK_FAINT, "left"),
        (0.98, 0.035, "DEFEND", ds.WARNING, "right"),
    ]
    for x, y, text, colour, align in corners:
        quad_ax.text(x, y, text, transform=quad_ax.transAxes, color=colour, fontsize=7.2,
                     fontweight="bold", ha=align, va="center", zorder=4)
    quad_ax.text(
        0.98, 0.86,
        "\n".join(textwrap.wrap(
            "Empty: no high-demand market is already well served by the modelled network.", 30)),
        transform=quad_ax.transAxes, fontsize=6.9, color=ds.ACCENT,
        ha="right", va="top", zorder=4, linespacing=1.5,
    )
    marked = pd.concat([locality[strong], locality.nlargest(2, "parkitup_coverage_pct")]).drop_duplicates("locality_id")
    place_labels(fig, quad_ax, [
        (float(row.parkitup_coverage_pct), float(row.avg_demand_score),
         str(row.locality_name), bool(row.market_class == "STRONG"))
        for row in marked.itertuples()
    ], fontsize=6.8)
    quad_ax.set_xlabel("Modelled PARK It Up capacity coverage (%)", fontsize=7.4)
    quad_ax.set_ylabel("Average demand score", fontsize=7.4)
    ds.chip_legend(quad_card, [("Strong market", ds.PRIMARY), ("All other markets", ds.NEUTRAL)],
                   y=0.035, step=0.180)

    # --- Secondary: market ranking -----------------------------------------
    rank_card = ds.card(fig, ds.rect(7, 5, 3, 13), "Opportunity ranking",
                        note="top 10 of 17 markets")
    rank_ax = rank_card.inset_axes((0.315, 0.115, 0.640, 0.700))
    ranked = locality.nlargest(10, "avg_acquisition_score").sort_values("avg_acquisition_score")
    bar_colour = [ds.PRIMARY if value == "STRONG" else ds.NEUTRAL for value in ranked.market_class]
    rank_ax.barh(range(len(ranked)), ranked.avg_acquisition_score, color=bar_colour, height=0.66)
    rank_ax.set_yticks(range(len(ranked)), ranked.locality_name, fontsize=7.1)
    rank_ax.set_xlim(0, float(ranked.avg_acquisition_score.max()) * 1.20)
    for index, row in enumerate(ranked.itertuples()):
        rank_ax.text(row.avg_acquisition_score + 1.0, index, f"{row.avg_acquisition_score:.1f}",
                     va="center", fontsize=7.0, color=ds.INK_MUTED)
    ds.bare(rank_ax)
    rank_ax.tick_params(axis="y", length=0)
    rank_card.text(0.030, 0.045, "Average acquisition score of the lots in each market (0-100)",
                   fontsize=ds.T_MICRO, color=ds.INK_FAINT)

    # --- Supporting: market decision table ---------------------------------
    table_card = ds.card(fig, ds.rect(0, 12, 16, 8), "Market decision table",
                         note="ordered by opportunity score")
    rows, colours, weights = [], [], []
    for row in locality.nlargest(8, "avg_acquisition_score").itertuples():
        has_targets = int(row.high_priority_count) > 0
        rows.append([
            str(row.locality_name),
            str(row.market_class).title(),
            str(int(row.parking_count)),
            f"{int(row.total_capacity):,}",
            f"{row.avg_demand_score:.1f}",
            f"{row.avg_competition_score:.1f}",
            f"{row.parkitup_coverage_pct:.1f}%",
            f"{row.avg_acquisition_score:.1f}",
            str(int(row.high_priority_count)) if has_targets else "-",
        ])
        colours.append([
            ds.INK, ds.PRIMARY if row.market_class == "STRONG" else ds.INK_MUTED,
            ds.INK, ds.INK, ds.INK, ds.INK,
            ds.WARNING if row.parkitup_coverage_pct >= 15 else ds.INK,
            ds.INK, ds.PRIMARY if has_targets else ds.INK_FAINT,
        ])
        weights.append(["normal"] * 7 + ["bold", "bold" if has_targets else "normal"])
    ds.data_table(
        table_card,
        ["Locality", "Class", "Lots", "Capacity", "Demand", "Competition",
         "Coverage", "Opportunity", "Acquire Now"],
        [0.020, 0.170, 0.300, 0.400, 0.500, 0.615, 0.720, 0.840, 0.975],
        ["left", "left", "right", "right", "right", "right", "right", "right", "right"],
        rows, colours, weights, top=0.74, bottom=0.10,
    )
    table_card.text(
        0.020, 0.040,
        "Competition scores high where demand exists but competing supply is thin. "
        "Coverage above 15% is flagged: those markets are already served.",
        fontsize=ds.T_MICRO, color=ds.INK_FAINT,
    )

    ds.source_strip(fig, 2, SOURCE_NOTE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return ds.save(fig, OUTPUT_DIR / "page_02_market_opportunity.png")


# ---------------------------------------------------------------------------
# Page 3 - Acquisition Priority: which individual lots should BD pursue?
# ---------------------------------------------------------------------------
def _filter_bar(fig, model: dict[str, pd.DataFrame], data: pd.DataFrame) -> None:
    """Slicer chips plus a reset affordance, drawn as one aligned row."""
    bar = ds.card(fig, ds.rect(0, 12, 0, 2))
    slicers = [
        ("Locality", f"All {model['locality'].locality_id.nunique()}"),
        ("Priority segment", "All"),
        ("Parking type", "All"),
        ("Capacity", f"{int(data.capacity_cars.min())} - {int(data.capacity_cars.max())}"),
    ]
    width, gap = 0.205, 0.014
    for index, (label, value) in enumerate(slicers):
        x = 0.012 + index * (width + gap)
        bar.add_patch(Rectangle((x, 0.20), width, 0.60, facecolor="#FAFBFC",
                                edgecolor=ds.BORDER, linewidth=0.8))
        bar.text(x + 0.014, 0.62, label.upper(), fontsize=6.2, color=ds.INK_FAINT, va="center")
        bar.text(x + 0.014, 0.36, value, fontsize=8.2, color=ds.INK, va="center")
        bar.text(x + width - 0.014, 0.36, "v", fontsize=7.0, color=ds.INK_FAINT,
                 ha="right", va="center")
    bar.text(0.988, 0.50, "Reset filters", fontsize=7.6, color=ds.ACCENT,
             ha="right", va="center", fontweight="bold")


def page_03(model: dict[str, pd.DataFrame]) -> str:
    data = joined(model)
    fig = ds.page("Acquisition Priority", "Which parking lots should the BD team pursue?", 2)
    _filter_bar(fig, model, data)

    # --- Primary visual: the segmentation matrix itself ---------------------
    matrix_card = ds.card(
        fig, ds.rect(0, 7, 2, 22), "Commercial attractiveness against acquisition feasibility",
        note="bubble size = capacity  ·  colour = priority segment",
    )
    matrix_ax = ds.plot_area(matrix_card, left=0.062, bottom=0.095, right=0.020, top=0.105)
    x_lo, x_hi = 8, 100
    y_lo, y_hi = 8, 88
    matrix_ax.set_xlim(x_lo, x_hi)
    matrix_ax.set_ylim(y_lo, y_hi)
    # Five regions, not four: Develop also carries a lower attractiveness floor,
    # so a plain 2x2 wash would colour Avoid lots as Develop.
    regions = [
        (x_lo, x_hi, y_lo, y_hi, "AVOID", None, None, None),
        (x_lo, FEASIBILITY_CUT, ATTRACTIVENESS_CUT, y_hi, "PURSUE", "PURSUE", "left", "top"),
        (FEASIBILITY_CUT, x_hi, ATTRACTIVENESS_CUT, y_hi, "ACQUIRE_NOW", "ACQUIRE NOW", "right", "top"),
        (FEASIBILITY_CUT, x_hi, DEVELOP_FLOOR, ATTRACTIVENESS_CUT, "DEVELOP", "DEVELOP", "right", "top"),
    ]
    for x0, x1, y0, y1, code, label, ha, va in regions:
        matrix_ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0,
                                      color=ds.SEGMENT_WASHES[code], zorder=0))
        if label is None:
            continue
        tx = x1 - 1.4 if ha == "right" else x0 + 1.4
        ty = y1 - 2.2 if va == "top" else y0 + 2.2
        matrix_ax.text(tx, ty, label, color=ds.SEGMENT_COLOURS[code], fontsize=7.6,
                       fontweight="bold", ha=ha, va="center", zorder=2)
    matrix_ax.text(x_lo + 1.4, y_lo + 2.2, "AVOID", color=ds.NEUTRAL, fontsize=7.6,
                   fontweight="bold", ha="left", va="center", zorder=2)
    matrix_ax.axvline(FEASIBILITY_CUT, color=ds.INK_FAINT, linestyle=(0, (4, 3)), linewidth=0.9, zorder=1)
    matrix_ax.axhline(ATTRACTIVENESS_CUT, color=ds.INK_FAINT, linestyle=(0, (4, 3)), linewidth=0.9, zorder=1)
    matrix_ax.plot([FEASIBILITY_CUT, x_hi], [DEVELOP_FLOOR, DEVELOP_FLOOR],
                   color=ds.INK_FAINT, linestyle=(0, (4, 3)), linewidth=0.9, zorder=1)
    matrix_ax.text(FEASIBILITY_CUT + 0.8, y_lo + 1.0, f"feasibility {FEASIBILITY_CUT}",
                   fontsize=6.3, color=ds.INK_FAINT, va="bottom", zorder=2)
    matrix_ax.text(x_hi - 1.2, ATTRACTIVENESS_CUT + 1.0, f"attractiveness {ATTRACTIVENESS_CUT}",
                   fontsize=6.3, color=ds.INK_FAINT, ha="right", va="bottom", zorder=2)
    matrix_ax.text(x_hi - 1.2, DEVELOP_FLOOR + 1.0, f"attractiveness {DEVELOP_FLOOR}",
                   fontsize=6.3, color=ds.INK_FAINT, ha="right", va="bottom", zorder=2)
    for code in ds.SEGMENT_ORDER:
        group = data[data.priority_segment.eq(code)]
        matrix_ax.scatter(
            group.feasibility_score, group.attractiveness_score,
            s=np.sqrt(group.capacity_cars) * 9.0, color=ds.SEGMENT_COLOURS[code],
            alpha=0.55 if code == "AVOID" else 0.85,
            edgecolor="white", linewidth=0.6, zorder=4 if code == "ACQUIRE_NOW" else 3,
        )
    place_labels(fig, matrix_ax, [
        (float(row.feasibility_score), float(row.attractiveness_score),
         f"{int(row.acquisition_rank)}. {lot_label(row.parking_display_name)}", True)
        for row in data.nsmallest(5, "acquisition_rank").itertuples()
    ], fontsize=6.6)
    matrix_ax.set_xlabel("Acquisition feasibility score (0-100)", fontsize=7.6)
    matrix_ax.set_ylabel("Commercial attractiveness score (0-100)", fontsize=7.6)
    matrix_card.text(
        0.012, 0.028,
        "Feasibility is held on its own axis: a lot that is attractive and unobtainable needs a "
        "different BD response from one that is ordinary and easy to sign.",
        fontsize=ds.T_MICRO, color=ds.INK_FAINT,
    )

    # --- Segment mix with the action each segment implies -------------------
    mix_card = ds.card(fig, ds.rect(7, 5, 2, 7), "What each segment means")
    counts = data.priority_segment.value_counts()
    actions = model["segment"].set_index("segment_code")
    for index, code in enumerate(ds.SEGMENT_ORDER):
        y = 0.755 - index * 0.215
        mix_card.add_patch(Rectangle((0.022, y - 0.055), 0.020, 0.11,
                                     color=ds.SEGMENT_COLOURS[code]))
        mix_card.text(0.058, y + 0.035, SEGMENT_LABELS[code], fontsize=8.2,
                      fontweight="bold", color=ds.INK, va="center")
        mix_card.text(0.058, y - 0.052,
                      "\n".join(textwrap.wrap(str(actions.loc[code, "bd_action"]), 68)[:2]),
                      fontsize=6.6, color=ds.INK_MUTED, va="center", linespacing=1.5)
        mix_card.text(0.978, y, f"{int(counts[code])}", fontsize=12.5, fontweight="bold",
                      color=ds.SEGMENT_COLOURS[code], ha="right", va="center")

    # --- Ranking table ------------------------------------------------------
    rank_card = ds.card(fig, ds.rect(7, 5, 9, 15), "Priority ranking",
                        note=f"top 10 of {len(data)} lots")
    rows, colours, weights = [], [], []
    for row in data.nsmallest(10, "acquisition_rank").itertuples():
        persistence = float(row.top_10_frequency_pct)
        persistence_colour = (
            ds.PRIMARY if persistence >= 90 else ds.INK if persistence >= 70 else ds.WARNING
        )
        rows.append([
            str(int(row.acquisition_rank)),
            lot_label(row.parking_display_name),
            f"{row.acquisition_score:.1f}",
            ds.inr_lakh(row.expected_monthly_platform_revenue_inr),
            f"{row.feasibility_score:.0f}",
            f"{persistence:.0f}%",
        ])
        colours.append([ds.INK_FAINT, ds.INK, ds.SEGMENT_COLOURS[row.priority_segment],
                        ds.INK, ds.INK_MUTED, persistence_colour])
        weights.append(["normal", "normal", "bold", "normal", "normal", "bold"])
    ds.data_table(
        rank_card,
        ["#", "Parking lot", "Score", "INR L / mo", "Feas.", "Top-10 persist."],
        [0.022, 0.062, 0.585, 0.720, 0.800, 0.978],
        ["left", "left", "right", "right", "right", "right"],
        rows, colours, weights, top=0.815, bottom=0.085, fontsize=7.2,
    )
    rank_card.text(
        0.022, 0.040,
        "Persistence: share of 11 scenarios where the lot stays in the top 10. "
        "Ranks 1-8 hold; 9 and 10 move under re-weighting.",
        fontsize=ds.T_MICRO, color=ds.INK_FAINT,
    )

    ds.source_strip(fig, 3, SOURCE_NOTE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return ds.save(fig, OUTPUT_DIR / "page_03_acquisition_matrix.png")


# ---------------------------------------------------------------------------
# Page 4 - Deep Dive: why should PARK It Up acquire this specific lot?
# ---------------------------------------------------------------------------
def page_04(model: dict[str, pd.DataFrame]) -> str:
    data = joined(model)
    lot = data.nsmallest(1, "acquisition_rank").iloc[0]
    lot_id = int(lot.parking_id)
    peers = data[data.locality_id.eq(lot.locality_id) & data.parking_id.ne(lot_id)]
    segment_code = str(lot.priority_segment)
    segment_colour = ds.SEGMENT_COLOURS[segment_code]

    components = (
        model["component"]
        .merge(model["dimension"], on="dimension_code")
        .merge(model["parking"][["parking_id", "locality_id"]], on="parking_id")
    )
    lot_components = components[components.parking_id.eq(lot_id)].sort_values("display_order")
    peer_means = (
        components[components.locality_id.eq(lot.locality_id) & components.parking_id.ne(lot_id)]
        .groupby("dimension_code").subscore.mean()
    )

    fig = ds.page("Parking Lot Deep Dive", "Why should PARK It Up acquire this lot?", 3)

    # --- Identity and the recommendation -----------------------------------
    head = ds.card(fig, ds.rect(0, 12, 0, 3))
    head.text(0.014, 0.66, str(lot.parking_display_name), fontsize=16.5, fontweight="bold", color=ds.INK, va="center")
    head.text(0.014, 0.26,
              f"{lot.lot_code}  ·  {lot.locality_name}  ·  {lot.parking_type}  ·  "
              f"{int(lot.capacity_cars)} spaces  ·  INR {lot.hourly_rate_inr:.0f}/hr  ·  "
              f"{lot.operating_hours_label}",
              fontsize=8.4, color=ds.INK_MUTED, va="center")
    head.text(0.615, 0.66, f"RANK {int(lot.acquisition_rank)} of {len(data)}", fontsize=7.2,
              color=ds.INK_FAINT, ha="right", va="center")
    head.text(0.615, 0.28, f"score {lot.acquisition_score:.1f}", fontsize=11.5,
              fontweight="bold", color=ds.INK, ha="right", va="center")
    head.add_patch(Rectangle((0.645, 0.16), 0.340, 0.68, facecolor=ds.SEGMENT_WASHES[segment_code],
                             edgecolor=segment_colour, linewidth=0.9))
    head.text(0.664, 0.63, "RECOMMENDATION", fontsize=6.4, color=segment_colour,
              fontweight="bold", va="center")
    head.text(0.664, 0.36, SEGMENT_LABELS[segment_code].upper(), fontsize=13.5,
              fontweight="bold", color=segment_colour, va="center")
    head.text(0.978, 0.36, "\n".join(textwrap.wrap(str(lot.recommendation), 42)), fontsize=6.8,
              color=ds.INK_MUTED, ha="right", va="center", linespacing=1.45)

    # --- Score breakdown against the locality ------------------------------
    score_card = ds.card(fig, ds.rect(0, 6, 3, 11), "Where the score comes from",
                         note="bar = this lot  ·  marker = locality average")
    score_ax = score_card.inset_axes((0.290, 0.135, 0.640, 0.680))
    rows = list(lot_components.itertuples())[::-1]
    labels, values, peer_values = [], [], []
    for row in rows:
        labels.append(f"{row.dimension_name}  {row.weight_applied * 100:.0f}%")
        values.append(float(row.subscore))
        peer_values.append(float(peer_means.get(row.dimension_code, np.nan)))
    positions = np.arange(len(labels))
    is_feasibility = [row.pillar_group == "Feasibility" for row in rows]
    score_ax.barh(positions, values, height=0.60,
                  color=[ds.PRIMARY if not flag else ds.PRIMARY for flag in is_feasibility])
    for index, (value, peer) in enumerate(zip(values, peer_values)):
        score_ax.plot([peer, peer], [index - 0.34, index + 0.34], color=ds.INK, linewidth=1.6, zorder=4)
        delta = value - peer
        score_ax.text(max(value, peer) + 2.0, index,
                      f"{value:.1f}   {'+' if delta >= 0 else ''}{delta:.1f} vs local",
                      va="center", fontsize=6.9,
                      color=ds.PRIMARY if delta >= 0 else ds.WARNING)
    score_ax.set_yticks(positions, labels, fontsize=7.1)
    score_ax.set_xlim(0, 118)
    ds.bare(score_ax)
    score_ax.tick_params(axis="y", length=0)
    boundary = sum(is_feasibility) - 0.5
    score_ax.axhline(boundary, color=ds.BORDER, linewidth=0.9)
    score_card.text(0.030, 0.048,
                    "The four attractiveness pillars sit above the line; feasibility is scored on its "
                    "own axis and is not averaged into them.",
                    fontsize=ds.T_MICRO, color=ds.INK_FAINT)

    # --- Hard numbers against the locality ---------------------------------
    bench_card = ds.card(fig, ds.rect(6, 6, 3, 11), f"Against {lot.locality_name}",
                         note=f"{len(peers)} other lots in this market")
    comparisons = [
        ("Peak occupancy (p90)", lot.p90_peak_occupancy_rate * 100, peers.p90_peak_occupancy_rate.mean() * 100, "pct"),
        ("Average occupancy", lot.avg_occupancy_rate * 100, peers.avg_occupancy_rate.mean() * 100, "pct"),
        ("Revenue per space", lot.revenue_per_space_inr, peers.revenue_per_space_inr.mean(), "inr"),
        ("Modelled monthly revenue", lot.expected_monthly_platform_revenue_inr,
         peers.expected_monthly_platform_revenue_inr.mean(), "lakh"),
        ("Capacity", lot.capacity_cars, peers.capacity_cars.mean(), "int"),
        ("Competitors within 1 km", lot.competitor_count_1km, peers.competitor_count_1km.mean(), "one"),
    ]
    formatters = {
        "pct": (lambda v: f"{v:.1f}%", lambda d: f"{d:+.1f} pts"),
        "inr": (lambda v: f"INR {v:,.0f}", lambda d: f"INR {d:+,.0f}"),
        "lakh": (lambda v: f"INR {v / 100_000:.2f}L", lambda d: f"INR {d / 100_000:+.2f}L"),
        "one": (lambda v: f"{v:.1f}", lambda d: f"{d:+.1f}"),
        "int": (lambda v: f"{v:,.0f}", lambda d: f"{d:+,.0f}"),
    }
    rows, colours, weights = [], [], []
    for label, mine, theirs, kind in comparisons:
        fmt, fmt_delta = formatters[kind]
        delta = mine - theirs
        better = delta <= 0 if label.startswith("Competitors") else delta >= 0
        rows.append([label, fmt(mine), fmt(theirs), fmt_delta(delta)])
        colours.append([ds.INK, ds.INK, ds.INK_MUTED, ds.PRIMARY if better else ds.WARNING])
        weights.append(["normal", "bold", "normal", "normal"])
    ds.data_table(
        bench_card,
        ["Metric", "This lot", "Market average", "Gap"],
        [0.028, 0.560, 0.800, 0.972],
        ["left", "right", "right", "right"],
        rows, colours, weights, top=0.775, bottom=0.115, fontsize=7.3,
    )
    bench_card.text(0.028, 0.055,
                    "Fewer competitors is favourable; every other gap is favourable when positive.",
                    fontsize=ds.T_MICRO, color=ds.INK_FAINT)

    # --- Demand profile, closed hours excluded -----------------------------
    perf_card = ds.card(fig, ds.rect(0, 6, 14, 10), "Typical day",
                        note=f"open {lot.operating_hours_label}")
    perf_ax = ds.plot_area(perf_card, left=0.085, bottom=0.150, right=0.030, top=0.185)
    hourly = model["hourly"][model["hourly"].parking_id.eq(lot_id)]
    open_hour = int(str(lot.opens_at)[:2])
    close_hour = int(str(lot.closes_at)[:2])
    styles = {"Weekday": (ds.PRIMARY, "-"), "Weekend": (ds.NEUTRAL, "--")}
    for day_type, (colour, style) in styles.items():
        group = hourly[hourly.day_type.eq(day_type)].sort_values("hour_of_day")
        group = group[group.hour_of_day.between(open_hour, close_hour - 1)]
        perf_ax.plot(group.hour_of_day, group.avg_occupancy_rate * 100, style, color=colour,
                     linewidth=2.0, label=day_type, zorder=3)
    weekday = hourly[hourly.day_type.eq("Weekday")]
    weekday = weekday[weekday.hour_of_day.between(open_hour, close_hour - 1)]
    peak = weekday.loc[weekday.avg_occupancy_rate.idxmax()]
    perf_ax.scatter([peak.hour_of_day], [peak.avg_occupancy_rate * 100], s=42, color=ds.PRIMARY,
                    edgecolor="white", linewidth=1.0, zorder=5)
    perf_ax.annotate(f"busiest hour {peak.avg_occupancy_rate * 100:.0f}% at {int(peak.hour_of_day)}:00",
                     (peak.hour_of_day, peak.avg_occupancy_rate * 100),
                     xytext=(-8, 10), textcoords="offset points", fontsize=7.0,
                     fontweight="bold", color=ds.PRIMARY, ha="right")
    perf_ax.set_xlim(open_hour - 0.6, close_hour - 0.4)
    perf_ax.set_ylim(0, 108)
    perf_ax.set_xticks(range(open_hour, close_hour, 2))
    perf_ax.set_xticklabels([f"{hour}:00" for hour in range(open_hour, close_hour, 2)])
    perf_ax.set_ylabel("Occupancy (%)", fontsize=7.4)
    perf_ax.grid(axis="y", color=ds.BORDER, linewidth=0.5, alpha=0.7)
    perf_ax.set_axisbelow(True)
    ds.chip_legend(perf_card, [("Weekday", ds.PRIMARY), ("Weekend", ds.NEUTRAL)], y=0.055, step=0.140)
    perf_card.text(0.972, 0.055, "closed hours excluded", fontsize=ds.T_MICRO,
                   color=ds.INK_FAINT, ha="right", va="center")

    # --- Reasons for and against -------------------------------------------
    notes_card = ds.card(fig, ds.rect(6, 6, 14, 10), "Reasons on record")
    def _flags(value: object) -> list[str]:
        return [] if pd.isna(value) else [flag for flag in str(value).split("|") if flag][:4]

    strengths = _flags(lot.positive_reason_flags)
    constraints = _flags(lot.constraint_reason_flags)
    notes_card.text(0.028, 0.815, "SUPPORTS ACQUISITION", fontsize=6.8, color=ds.PRIMARY, fontweight="bold")
    notes_card.text(0.520, 0.815, "NEEDS RESOLVING", fontsize=6.8, color=ds.WARNING, fontweight="bold")
    for index, flag in enumerate(strengths):
        notes_card.text(0.028, 0.700 - index * 0.115, f"+   {flag.replace('_', ' ').title()}",
                        fontsize=7.6, color=ds.INK)
    for index, flag in enumerate(constraints):
        notes_card.text(0.520, 0.700 - index * 0.115, f"-   {flag.replace('_', ' ').title()}",
                        fontsize=7.6, color=ds.INK)
    if not constraints:
        notes_card.text(0.520, 0.700, "None recorded", fontsize=7.6, color=ds.INK_FAINT)
    notes_card.add_patch(Rectangle((0.022, 0.075), 0.956, 0.180, facecolor="#FAFBFC",
                                   edgecolor=ds.BORDER, linewidth=0.7))
    notes_card.text(0.040, 0.185,
                    f"Onboarding cost {ds.inr_headline(lot.estimated_onboarding_cost_inr)}  ·  "
                    f"setup {int(lot.estimated_setup_days)} days  ·  "
                    f"documentation readiness {int(lot.documentation_readiness)}/5  ·  "
                    f"operational complexity {int(lot.operational_complexity)}/5",
                    fontsize=7.0, color=ds.INK)
    notes_card.text(0.040, 0.115,
                    f"Nearest competitor {lot.competitor_distance_proxy_m:.0f} m  ·  "
                    f"competitor average rate INR {lot.competitor_avg_hourly_rate_inr:.0f}/hr  ·  "
                    f"exclusivity {'possible' if lot.exclusivity_possible else 'not available'}",
                    fontsize=7.0, color=ds.INK_MUTED)

    ds.source_strip(fig, 4, SOURCE_NOTE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return ds.save(fig, OUTPUT_DIR / "page_04_parking_deep_dive.png")


# ---------------------------------------------------------------------------
# Page 5 - BD Action Center: what should the BD team do next?
# ---------------------------------------------------------------------------
ACTION_LABELS = {
    "ACQUIRE_NOW": "Contact now",
    "PURSUE": "Resolve constraint",
    "DEVELOP": "Batch outreach",
    "AVOID": "No outreach",
}


def page_05(model: dict[str, pd.DataFrame]) -> str:
    data = joined(model)
    outreach = model["outreach"]
    funnel = model["funnel"].sort_values("stage_order")
    won = outreach.pipeline_status.eq("Won")

    fig = ds.page("BD Action Center", "What should the BD team do next?", 4)

    ds.kpi_strip(
        fig,
        ds.rect(0, 12, 0, 3),
        [
            ("Leads worked", f"{outreach.lead_id.nunique()}", "one per candidate lot"),
            ("Onboarded", f"{int(won.sum())}", "reached a live listing"),
            ("Lead to live", f"{won.mean() * 100:.1f}%", "end-to-end conversion"),
            ("Cycle time", f"{outreach.loc[won, 'days_to_conversion'].mean():.0f} days",
             "first contact to live, won leads"),
        ],
        accents=[ds.INK, ds.PRIMARY, ds.INK, ds.INK],
    )

    # --- Primary visual: where the pipeline leaks ---------------------------
    worst = funnel.loc[funnel.drop_off_pct.idxmax()]
    funnel_card = ds.card(fig, ds.rect(0, 6, 3, 11), "Where the pipeline leaks",
                          note=f"{int(funnel.leads_reached.iloc[0])} leads entering")
    funnel_ax = funnel_card.inset_axes((0.235, 0.115, 0.615, 0.700))
    stages = list(funnel.itertuples())
    positions = np.arange(len(stages))
    total = float(funnel.leads_reached.iloc[0])
    for index, row in enumerate(stages):
        funnel_ax.barh(index, total, color="#F1F3F5", height=0.66, zorder=1)
        is_worst = row.stage_code == worst.stage_code
        # Bars stay one colour: red on the Onboarded bar would read as "onboarding
        # is bad". Only the loss annotation is coloured as a loss.
        funnel_ax.barh(index, row.leads_reached, color=ds.PRIMARY, height=0.66, zorder=2)
        funnel_ax.text(row.leads_reached - 1.5, index, f"{int(row.leads_reached)}", color="white",
                       fontsize=7.4, fontweight="bold", ha="right", va="center", zorder=3)
        if index:
            drop = float(row.drop_off_pct)
            funnel_ax.text(total + 3.0, index, f"-{int(row.drop_off_from_prior)}   {drop:.0f}%",
                           fontsize=7.0, va="center",
                           color=ds.NEGATIVE if is_worst else ds.INK_MUTED,
                           fontweight="bold" if is_worst else "normal")
    funnel_ax.set_yticks(positions, [row.stage_name for row in stages], fontsize=7.2)
    funnel_ax.set_xlim(0, total * 1.30)
    funnel_ax.invert_yaxis()
    ds.bare(funnel_ax)
    funnel_ax.tick_params(axis="y", length=0)
    funnel_card.text(0.030, 0.048,
                     f"Worst single step: {worst.stage_name.lower()} loses "
                     f"{worst.drop_off_pct:.0f}% of the leads that reach the previous stage.",
                     fontsize=ds.T_MICRO, color=ds.INK_FAINT)

    # --- Secondary visual: why deals are lost -------------------------------
    lost = outreach[outreach.pipeline_status.eq("Lost")]
    reasons = lost.lost_reason.value_counts().sort_values()
    lost_card = ds.card(fig, ds.rect(6, 6, 3, 11), "Why deals are lost",
                        note=f"{len(lost)} closed-lost leads")
    lost_ax = lost_card.inset_axes((0.300, 0.115, 0.560, 0.700))
    top_two = reasons.nlargest(2).index.tolist()
    colours = [ds.NEGATIVE if name in top_two else ds.NEUTRAL for name in reasons.index]
    lost_ax.barh(range(len(reasons)), reasons.values, color=colours, height=0.64)
    for index, (name, value) in enumerate(reasons.items()):
        lost_ax.text(value + 0.4, index, f"{value}   {value / len(lost) * 100:.0f}%",
                     va="center", fontsize=7.0, color=ds.INK_MUTED)
    lost_ax.set_yticks(range(len(reasons)), reasons.index, fontsize=7.1)
    lost_ax.set_xlim(0, float(reasons.max()) * 1.34)
    ds.bare(lost_ax)
    lost_ax.tick_params(axis="y", length=0)
    share = reasons[top_two].sum() / len(lost) * 100
    lost_card.text(0.030, 0.048,
                   f"{share:.0f}% of losses are owner authority or commission terms - both testable "
                   "before a lot enters the pipeline.",
                   fontsize=ds.T_MICRO, color=ds.INK_FAINT)

    # --- The queue itself ---------------------------------------------------
    queue_card = ds.card(fig, ds.rect(0, 12, 14, 10), "Next actions",
                         note="highest-scoring lot in each priority segment, ordered by segment")
    picks = pd.concat([
        data[data.priority_segment.eq("ACQUIRE_NOW")].nsmallest(5, "acquisition_rank"),
        data[data.priority_segment.eq("PURSUE")].nsmallest(2, "acquisition_rank"),
        data[data.priority_segment.eq("DEVELOP")].nsmallest(1, "acquisition_rank"),
    ])
    rows, colours, weights = [], [], []
    for row in picks.itertuples():
        code = str(row.priority_segment)
        raw = row.constraint_reason_flags
        blockers = [] if pd.isna(raw) else [flag for flag in str(raw).split("|") if flag]
        rows.append([
            SEGMENT_LABELS[code],
            lot_label(row.parking_display_name),
            str(row.locality_name),
            f"{row.acquisition_score:.1f}",
            f"{row.feasibility_score:.0f}",
            ds.inr_lakh(row.expected_monthly_platform_revenue_inr),
            f"{row.top_10_frequency_pct:.0f}%",
            ACTION_LABELS[code],
            blockers[0].replace("_", " ").title() if blockers else "None recorded",
        ])
        colours.append([
            ds.SEGMENT_COLOURS[code], ds.INK, ds.INK_MUTED, ds.SEGMENT_COLOURS[code],
            ds.INK, ds.INK, ds.INK_MUTED, ds.SEGMENT_COLOURS[code],
            ds.WARNING if blockers else ds.INK_FAINT,
        ])
        weights.append(["bold", "normal", "normal", "bold", "normal", "normal", "normal", "bold", "normal"])
    ds.data_table(
        queue_card,
        ["Segment", "Parking lot", "Locality", "Score", "Feas.", "INR L / mo",
         "Top-10 persist.", "Next action", "Blocker on record"],
        [0.014, 0.115, 0.290, 0.430, 0.487, 0.567, 0.660, 0.700, 0.986],
        ["left", "left", "left", "right", "right", "right", "right", "left", "right"],
        rows, colours, weights, top=0.760, bottom=0.115, fontsize=7.3,
    )
    queue_card.text(
        0.014, 0.052,
        "Acquire Now lots go straight to commercial discussion. Pursue lots are commercially "
        "attractive but blocked, so the blocker is worked first. Develop lots absorb low-cost outreach only.",
        fontsize=ds.T_MICRO, color=ds.INK_FAINT,
    )

    ds.source_strip(fig, 5, SOURCE_NOTE)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return ds.save(fig, OUTPUT_DIR / "page_05_bd_strategy.png")


def generate_all_mockups() -> dict[str, str]:
    model = read_model()
    return {
        "executive_overview": page_01(model),
        "market_opportunity": page_02(model),
        "acquisition_matrix": page_03(model),
        "parking_deep_dive": page_04(model),
        "bd_strategy": page_05(model),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the Power BI page previews.")
    parser.add_argument("--page", type=int, choices=[1, 2, 3, 4, 5], help="render one page only")
    args = parser.parse_args()
    model = read_model()
    pages = {1: page_01, 2: page_02, 3: page_03, 4: page_04, 5: page_05}
    if args.page:
        print(pages[args.page](model))
        return
    for name, path in generate_all_mockups().items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()


