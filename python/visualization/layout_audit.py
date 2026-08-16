"""Assert that no text or artist escapes the card it belongs to.

The dashboard previews collided because charts were drawn straight into the panel
rectangle, so matplotlib placed tick labels and axis labels outside it. That
class of defect is invisible in code review and obvious only in the rendered
image, so it is checked mechanically here: every page is rebuilt in memory and
each drawn text is compared against the bounds of its own axes and against the
page margins.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from python.visualization import design_system as ds
from python.visualization import powerbi_mockups as pm

TOLERANCE_PX = 2.0


def _page_builders() -> dict[str, callable]:
    return {
        "page_01_executive_overview": pm.page_01,
        "page_02_market_opportunity": pm.page_02,
        "page_03_acquisition_matrix": pm.page_03,
        "page_04_parking_deep_dive": pm.page_04,
        "page_05_bd_strategy": pm.page_05,
    }


def audit_page(name: str, builder) -> list[str]:
    """Render one page and return a list of layout violations."""
    model = pm.read_model()
    ds.apply_base_style()
    problems: list[str] = []
    original_save = ds.save
    captured: dict[str, plt.Figure] = {}

    def capture(fig, path):  # keep the figure open so it can be measured
        captured["fig"] = fig
        return str(path)

    ds.save = capture
    try:
        builder(model)
    finally:
        ds.save = original_save

    fig = captured["fig"]
    renderer = fig.canvas.get_renderer()
    fig.canvas.draw()
    page = fig.bbox

    for axes in fig.axes:
        box = axes.get_window_extent(renderer)
        for text in axes.texts:
            if not text.get_text().strip():
                continue
            bounds = text.get_window_extent(renderer)
            if (bounds.x0 < page.x0 - TOLERANCE_PX or bounds.x1 > page.x1 + TOLERANCE_PX
                    or bounds.y0 < page.y0 - TOLERANCE_PX or bounds.y1 > page.y1 + TOLERANCE_PX):
                problems.append(f"{name}: text leaves the canvas: {text.get_text()[:40]!r}")
            # Text belonging to a card must stay inside that card. Inset plot
            # axes are exempt because their own padding is the card padding.
            if axes.get_label() == "card" and (
                bounds.x0 < box.x0 - TOLERANCE_PX or bounds.x1 > box.x1 + TOLERANCE_PX
                or bounds.y0 < box.y0 - TOLERANCE_PX or bounds.y1 > box.y1 + TOLERANCE_PX
            ):
                problems.append(f"{name}: text leaves its card: {text.get_text()[:40]!r}")

    cards = [ax for ax in fig.axes if ax.get_label() == "card"]

    # The real dashboard defect: a chart whose tick labels and axis labels render
    # outside the card hosting it. Charts are inset children of their card, so
    # they are reached through card.child_axes, not fig.axes. get_tightbbox
    # includes tick labels, axis labels and titles.
    for card in cards:
        host_box = card.get_window_extent(renderer)
        for child in card.child_axes:
            tight = child.get_tightbbox(renderer)
            if tight is None:
                continue
            overflow = max(
                host_box.x0 - tight.x0, tight.x1 - host_box.x1,
                host_box.y0 - tight.y0, tight.y1 - host_box.y1,
            )
            if overflow > TOLERANCE_PX:
                problems.append(
                    f"{name}: chart decorations overflow their card by {overflow:.0f} px"
                )
            for text in child.texts:
                if not text.get_text().strip():
                    continue
                bounds = text.get_window_extent(renderer)
                if (bounds.x0 < host_box.x0 - TOLERANCE_PX
                        or bounds.x1 > host_box.x1 + TOLERANCE_PX
                        or bounds.y0 < host_box.y0 - TOLERANCE_PX
                        or bounds.y1 > host_box.y1 + TOLERANCE_PX):
                    problems.append(
                        f"{name}: in-chart label leaves its card: {text.get_text()[:34]!r}"
                    )

    for index, first in enumerate(cards):
        box_a = first.get_window_extent(renderer)
        for second in cards[index + 1:]:
            box_b = second.get_window_extent(renderer)
            overlap_w = min(box_a.x1, box_b.x1) - max(box_a.x0, box_b.x0)
            overlap_h = min(box_a.y1, box_b.y1) - max(box_a.y0, box_b.y0)
            if overlap_w > TOLERANCE_PX and overlap_h > TOLERANCE_PX:
                problems.append(f"{name}: two cards overlap by {overlap_w:.0f}x{overlap_h:.0f} px")
    plt.close(fig)
    return problems


def main() -> int:
    failures: list[str] = []
    for name, builder in _page_builders().items():
        found = audit_page(name, builder)
        print(f"{name}: {'OK' if not found else str(len(found)) + ' violation(s)'}")
        failures.extend(found)
    for problem in failures:
        print(f"  - {problem}")
    print(f"\n{len(failures)} layout violation(s) total")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
