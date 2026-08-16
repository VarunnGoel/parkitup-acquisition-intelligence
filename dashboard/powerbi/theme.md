# Design System

The dashboard uses a horizontal page navigator, a single card surface, and a
strictly semantic palette. Nothing on a page is coloured for decoration.

## Colour

Four of the six theme colours are the priority-segment colours, taken directly
from `DimPrioritySegment.segment_colour_hex`. The model, the theme file and the
previews therefore cannot drift apart: changing a segment colour in the database
changes it everywhere.

| Token | Hex | Meaning | Where it may appear |
| --- | --- | --- | --- |
| Primary / positive | `#0B6E4F` | `ACQUIRE_NOW`, favourable variance, brand | Segment marks, favourable gaps, headline findings |
| Warning | `#D97706` | `PURSUE`, a constraint to resolve | Segment marks, blockers, unfavourable variance |
| Accent | `#2563EB` | `DEVELOP`, an interactive affordance | Segment marks, `Reset filters` |
| Neutral | `#6B7280` | `AVOID`, "no action", any non-highlighted series | Segment marks, comparison series |
| Negative | `#B3261E` | Loss and drop-off only | Pipeline loss annotation, closed-lost reasons |
| Ink | `#1B2027` | Text and reference markers | Values, locality-average markers |

Rules that follow from the table:

- A hue carries one meaning across all five pages. Green never means "series 1".
- Negative red is reserved for losing something. It is never used on a bar that
  represents a good outcome, which is why the `Onboarded` funnel bar stays green
  and only its loss annotation is red.
- Colour is never the only encoding. Segments are always labelled in text as
  well, and quadrant regions carry both a wash and a written label.

Supporting washes `#E4F0EA`, `#FDF0DC`, `#E7EEFD` and `#F0F1F3` are 8% tints of
the four segment colours, used for quadrant backgrounds and the recommendation
badge so a region reads as its segment without competing with the marks.

## Type scale

Power BI renders in Aptos; the previews render in Lato because Aptos is not
installed in the rendering environment. The sizes are the contract, not the face.

| Role | Size | Weight |
| --- | --- | --- |
| Page title | 19 | Bold |
| Business question | 10 | Regular |
| Card title | 9.8 | Bold |
| KPI value | 17 | Bold |
| KPI label | 7.3 | Regular, upper case |
| Body and findings | 7.6 - 8.3 | Regular |
| Table cell | 7.2 - 7.4 | Regular, bold for the deciding column |
| Table header | 6.9 | Bold |
| Footnote | 6.6 | Regular |

No size exists purely to look premium. The KPI value is the largest element on a
page only where the number is the answer to the page's question.

## Layout

A 12-column by 24-row grid spans the content band, with an 8 px gutter. Cards
snap to that grid, so left and right edges align down the page and card heights
repeat rather than drifting.

Every card is a white surface with a 1 px `#DCE1E6` border, its title on the
first baseline, and an optional right-aligned note that carries the encoding
legend (`bubble size = capacity`) or the scope (`top 10 of 17 markets`).

Charts are never drawn into the card rectangle. They occupy an inset plot area
with explicit padding, so tick labels, axis titles and in-chart labels land on
the card's own padding instead of the neighbouring card. This is enforced
mechanically by `python/visualization/layout_audit.py`.

## Chart conventions

- Ranking uses horizontal bars with the value at the bar end and no vertical
  gridlines; the axis is removed because every bar is already labelled.
- Trade-offs use scatter plots with the decision thresholds drawn as dashed
  lines and the resulting regions washed in the segment colour they define.
- Composition uses one stacked strip rather than several bars.
- Comparison against a benchmark uses a reference marker on the bar, not a
  second bar, so the gap is read in one movement.
- Trends exclude hours the site is closed, so a closing time cannot look like a
  collapse in demand.
- No pie charts, gauges, radar charts, or 3D. Radar was rejected for the score
  breakdown because five pillars on a radar hide the size of each gap that the
  horizontal bars show directly.
