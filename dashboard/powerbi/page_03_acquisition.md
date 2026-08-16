# Page 3 - Acquisition Priority

**Business question:** Which parking lots should the BD team pursue?

**Default state:** all 120 lots, no slicer applied.

**Decision supported:** which named lots enter the pipeline, and which of the four
plays each one gets.

## Layout

| Region | Grid | Contents |
| --- | --- | --- |
| Filter bar | cols 0-12, rows 0-2 | four slicers and a reset |
| Primary | cols 0-7, rows 2-24 | attractiveness against feasibility |
| Secondary | cols 7-12, rows 2-9 | what each segment means |
| Supporting | cols 7-12, rows 9-24 | priority ranking |

This page owns the acquisition matrix. It is not repeated anywhere else.

## Visuals

1. **Filter bar** - `Locality`, `Priority segment`, `Parking type`, `Capacity`,
   plus a `Reset filters` action driven by a default-state bookmark. Owner type
   and a score-range slicer were dropped: neither changed the decision this page
   supports and five chips crowded the row.
2. **Commercial attractiveness against acquisition feasibility** (primary) -
   `attractiveness_score` on Y, `feasibility_score` on X, bubble size by
   `capacity_cars`, colour by `priority_segment`.

   The plot is washed in **five** regions, not four, because the scoring
   segmentation uses three thresholds:

   | Region | Rule | Segment |
   | --- | --- | --- |
   | Top right | attractiveness >= 46.66 and feasibility >= 57.55 | `ACQUIRE_NOW` |
   | Top left | attractiveness >= 46.66 and feasibility < 57.55 | `PURSUE` |
   | Right band | 33.42 <= attractiveness < 46.66 and feasibility >= 57.55 | `DEVELOP` |
   | Remainder | everything else | `AVOID` |

   A plain 2x2 wash coloured `AVOID` lots as `DEVELOP` in the low-attractiveness,
   high-feasibility corner. All three thresholds are drawn as dashed lines and
   labelled with their values. Because each point sits on the wash of its own
   segment, the segmentation rule is legible without a legend, so the legend was
   removed. The top five ranks are labelled with rank and lot name.
3. **What each segment means** (secondary) - the four segments with their count
   and the `bd_action` text from `DimPrioritySegment`, so the page states the play
   rather than only the label.
4. **Priority ranking** - top 10 of 120. Columns: rank, lot, score, modelled
   monthly revenue, feasibility, top-10 persistence. Persistence is green at or
   above 90%, ink at or above 70%, amber below, which surfaces that ranks 9 and 10
   move under re-weighting while 1-8 hold.

## Interactions

- Slicers filter the matrix, the segment counts and the ranking table together.
- Selecting a matrix point or a ranking row enables drill-through to Page 4.
- Selecting a segment row in *What each segment means* cross-filters the matrix
  and the table to that segment.
- Tooltip on a matrix point: lot, locality, capacity, score, segment, modelled
  monthly revenue, feasibility, top-10 persistence. No table is placed in a
  tooltip.

## Acceptance checks

Segment counts 25 / 15 / 21 / 59. Thresholds must equal the
`DimPrioritySegment` values 46.66, 57.55 and 33.42. Every `DEVELOP` lot must fall
inside the right band; the current extract holds attractiveness 33.46 to 45.53 and
feasibility from 57.91 upwards. Top 10 `parking_id` order must be
52, 18, 1, 51, 6, 17, 41, 3, 8, 13.
