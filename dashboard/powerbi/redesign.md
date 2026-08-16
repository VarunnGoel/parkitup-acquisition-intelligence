# dashboard-redesign Dashboard Redesign

## Purpose

the dashboard redesign is a design, UX and information-architecture pass over the dashboard
Power BI package. It does not change the data model, the scoring methodology, the
DAX definitions or the business questions. It changes what each page leads with,
how much of it there is, and whether it can be read in about a minute.

## The defect that caused most of the visual problems

The first dashboard pass built every panel as a matplotlib axes and then drew the chart into that
same axes. Matplotlib renders tick labels, axis titles and legends *outside* the
plot box, so they landed on top of whichever panel came next. That is why section
titles were struck through by axis labels, why category names were cut off at the
canvas edge, and why legends sat over quadrant labels.

The fix is structural rather than cosmetic. `python/visualization/design_system.py`
now separates a **card** (a background surface with its axis switched off) from a
**plot area** (an inset axes with explicit padding). Anything matplotlib draws
outside the plot box now lands on the card's own padding.

Because the defect is invisible in code review and obvious only in the rendered
image, `python/visualization/layout_audit.py` rebuilds all five pages and measures
each chart's full extent, tick labels included, against its host card. It is
wired into `make dashboard`. A companion test removes the padding on purpose and
asserts that the audit reports violations, so the check cannot quietly become
vacuous - which it briefly was, when a first version inspected `fig.axes` and
never saw the inset charts at all.

## Design changes

**Information architecture**

- Each page now has one dominant visual sized to say so, rather than a grid of
  similarly weighted charts. The primary visual is identified in each page spec.
- Page 1 leads with geographic concentration instead of a KPI wall; the KPI row
  fell from six cards to four cells in one strip.
- Page 3 owns the acquisition matrix outright. No other page repeats it.
- Page 5 replaces a lead-source rate chart with loss reasons, which use the full
  closed-lost population instead of seven subsamples of 9 to 29 leads.
- 34 visual elements became 22. The full keep/remove record with reasons is in
  [visual_inventory.md](visual_inventory.md).

**Navigation and chrome**

- The left navigation rail was replaced with a horizontal navigator under the
  header, returning roughly an eighth of the canvas width to the analytics.
- The header carries brand, page title, business question, scope and the base-case
  weights, so a screenshot is self-describing.
- Provenance sits on one footer baseline and no longer names internal build stages.

**Colour**

- One meaning per hue, enforced across all five pages. The four priority-segment
  colours come from `DimPrioritySegment.segment_colour_hex`, so the theme, the
  model and the previews cannot drift apart.
- Decorative teal, purple and light blue were removed from the theme.
- Negative red is reserved for losing something, which is why the `Onboarded`
  funnel bar stays green and only its loss annotation is red.
- Full system in [theme.md](theme.md).

**Correctness fixes found while redesigning**

These were display defects, not model defects. The scoring engine was not touched.

1. The Page 3 matrix was washed as a 2x2 grid, but the scoring segmentation uses
   **three** thresholds: `DEVELOP` also requires attractiveness >= 33.42. The old
   wash therefore coloured `AVOID` lots as `DEVELOP` in the low-attractiveness,
   high-feasibility corner. The matrix now draws five regions and all three
   threshold lines.
2. The Page 4 day trend plotted all 24 hours, so a 06:00-23:00 closing time
   appeared as occupancy collapsing to zero at 23:00. Closed hours are now
   excluded and the card says so.
3. Page 4 rendered `documentation_readiness` and `operational_complexity` as bare
   integers. They are 1-5 scales and now read `3/5`.
4. Page 4's benchmark gap column mixed units and decimals, showing
   `+154,688.4` for a rupee figure displayed elsewhere in lakh. Gaps now use the
   metric's own unit.
5. Rupee values used three different units in one table (`1.82 L`, `25K`, `87K`).
   Everything is now lakh to two decimals.
6. A `NaN` constraint flag rendered as the literal string `Nan` in the Page 5
   blocker column.
7. Page 1's robustness finding conflated two different statistics. It compared
   top-10 persistence for the top 10 against persistence for lots ranked below 10
   - but lots outside the top 10 rarely entering the top 10 is a tautology, not a
   contrast. The finding now states only the defensible figure: 94% average
   persistence for the current top 10 across 11 scenarios.

## What did not change

- PostgreSQL remains the relational source of truth.
- scoring, weights and segmentation remain authoritative and untouched.
- validation sensitivity, scenario, stress-test and rank-stability outputs remain
  authoritative.
- `data/powerbi/` remains a generated portable extract, not a second model.
- Power BI remains the only business-facing surface. The retired Streamlit
  simulator is not reintroduced.

## Implementation status

Power BI Desktop and PBIP tooling are unavailable on the development host, so the
repository contains an assembly-ready package and actual-data static previews. No
`.pbix` or `.pbip` file is claimed. Regenerate with:

```bash
make dashboard
```

The generator is [powerbi_mockups.py](../../python/visualization/powerbi_mockups.py),
composed only of page layout; primitives live in
[design_system.py](../../python/visualization/design_system.py).

## Review standard

Accepted only when all five previews are 16:9 and nonblank, carry no clipped or
overlapping labels under the layout audit, are built from the current reconciled
extracts, and label modelled or synthetic values as such. Executed results are in
[redesign_validation.md](redesign_validation.md).
