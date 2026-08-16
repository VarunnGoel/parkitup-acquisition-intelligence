# Page 1 - Executive Overview

**Business question:** Where is the biggest acquisition opportunity?

**Default state:** all 120 lots, all 17 localities, all parking types, base-case weights.

**Decision supported:** whether the acquisition programme has enough concentrated
upside to fund BD capacity, and which markets that capacity should go to.

## Layout

16:9 canvas. A title band carries the brand, page title and business question; a
horizontal page navigator sits directly beneath it. The content band is a
12x24 grid:

| Region | Grid | Contents |
| --- | --- | --- |
| KPI strip | cols 0-12, rows 0-3 | four KPI cells in one card |
| Primary | cols 0-6, rows 3-24 | opportunity map, full column height |
| Secondary | cols 6-12, rows 3-13 | six strongest targets |
| Supporting | cols 6-12, rows 13-17 | portfolio shape strip |
| Supporting | cols 6-12, rows 17-24 | three findings |

See `screenshots/page_01_executive_overview.png`. It is a static implementation
preview, not a PBIX screenshot.

## Visuals

1. **KPI strip** - one card, four cells, hairline dividers, no per-card accent
   colour. Cells: `High Priority Count` labelled *Acquire Now targets*;
   `Expected Monthly Platform Revenue` filtered to `ACQUIRE_NOW` and labelled
   *Revenue at stake*; `High Opportunity Markets`; `Total Capacity` with
   `Average Acquisition Score` as its subtitle.
2. **Where the opportunity sits** (primary) - map from `DimParking` latitude and
   longitude, bubble size by `capacity_cars`, colour by `priority_segment`,
   `AVOID` held at 55% opacity so the actionable segments dominate. The five
   markets with the most `ACQUIRE_NOW` lots are labelled with their target count
   using collision-avoiding placement. Card note states `bubble size = capacity`.
3. **Strongest targets today** (secondary) - top 6 by `acquisition_rank`. Columns:
   rank, lot, locality, score, modelled monthly revenue in lakh. Score is
   coloured by segment; every rupee value on the page uses lakh to one or two
   decimals so the column is comparable.
4. **Portfolio shape** - a single stacked horizontal strip of the four segment
   counts with an inline swatch legend. Replaces four separate bars.
5. **What the analysis says** - three findings, each a bold figure plus one
   sentence, generated from the extracts:
   - 23 of 25 `ACQUIRE_NOW` targets sit in four localities;
   - 15 of the 40 lots above the attractiveness threshold fall below the
     feasibility threshold;
   - 94% average top-10 persistence for the current top 10 across 11 scenarios.

## Interactions

- Locality, parking type and priority slicers are page-level here and update the
  KPI strip, map and target table.
- Selecting a map bubble or a table row cross-filters the other and enables
  drill-through to Page 4 carrying only `parking_id`.
- The findings card has interactions disabled: the sentences are written against
  the default state and must not silently re-scope.
- `Reset filters` on Page 3 restores the report default via a bookmark.

## Acceptance checks

At the default state: 120 lots, 23,685 spaces, 25 Acquire Now targets,
INR 38.3 L Acquire Now monthly revenue potential, 6 strong markets, 45.2 average
score, and MCD Parking at rank 1 with score 78.5. Filtered to Connaught Place the
measures must match the `CONNAUGHT_PLACE` rows of
`validation/powerbi_reconciliation.csv`.
