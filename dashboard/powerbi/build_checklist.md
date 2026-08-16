# Power BI Assembly Checklist

## Model

- [ ] Import PostgreSQL sources or the generated `data/powerbi/` fallback files.
- [ ] Apply explicit data types: whole numbers for keys/ranks/capacity, decimal for scores/currency, date for dates, boolean for flags.
- [ ] Create relationships exactly as documented.
- [ ] Mark `DimDate` as the date table.
- [ ] Configure sort-by columns for stages, segments and score dimensions.
- [ ] Hide technical IDs, source metadata, and the two aggregate validation tables.
- [ ] Add display folders and measure formats.

## Measures

- [ ] Create the core portfolio, market, BD, component and scenario measures.
- [ ] Verify every ratio uses `DIVIDE`.
- [ ] Test no-filter, locality, priority, combined, and single-lot contexts.
- [ ] Confirm the dynamic funnel uses `furthest_stage_order`.
- [ ] Confirm locality benchmark measures remove only the parking filter.
- [ ] Confirm rank-change sign: positive means an improved scenario rank.

## Pages

- [ ] Build the five pages using the page specifications.
- [ ] Use the dashboard-redesign horizontal navigator and compact two-band header on every page.
- [ ] Preserve the visible Base Case / active-filter context in the header.
- [ ] Add parking and market report-page tooltips.
- [ ] Add drill-through to Page 4 on `parking_id`.
- [ ] Add Home, Back and Reset buttons.
- [ ] Sync only the documented global slicers.
- [ ] Keep scenario filtering restricted to robustness visuals.
- [ ] Add visible synthetic/modelled caveats.
- [ ] Keep source notes on the footer baseline and outside visual containers.

## Validation

- [ ] Reconcile the base KPI values.
- [ ] Reconcile Connaught Place, Acquire Now, combined, and parking 52 contexts.
- [ ] Confirm the Top 10 exact ordering.
- [ ] Test multiple simultaneous filters.
- [ ] Test blank selections and zero denominators.
- [ ] Check interaction edit mode for misleading cross-highlighting.
- [ ] Review 1366x768 and 1920x1080 display sizes.
- [ ] Review tab order, alt text and colour-independent labels.
- [ ] Confirm all labels remain inside their visual bounds at both target display sizes.
