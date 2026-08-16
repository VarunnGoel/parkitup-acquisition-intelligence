# dashboard Validation

## Tooling status

The implementation host is macOS 26.2 on ARM64. The following were checked and unavailable:

- Power BI Desktop;
- PBIP tooling / `pbi-tools`;
- Tabular Editor;
- DAX Studio;
- Windows compatibility runtime.

Therefore:

- PBIX created: **No**.
- PBIP created: **No**.
- Implementation package created: **Yes**.
- Portable star-schema extracts created: **Yes**.
- DAX executed in a DAX engine: **No**.

## Model validation

`python/analysis/prepare_powerbi.py` runs source-grain, key, and foreign-key checks before writing the portable model. The executed result is in `validation/powerbi_model_checks.csv`:

- 44 checks passed;
- 0 failed;
- 120 parking lots, 72 owners, 17 localities, 365 dates, 11 scenarios;
- 43,800 daily facts and 5,760 hourly-profile facts;
- 120 base scores, 600 base component rows;
- 1,320 scenario-score rows and 6,600 scenario-component rows;
- 120 leads and 385 outreach events;
- zero unresolved parking, owner, locality, lead, scenario, segment, or component keys.

## Reconciliation

The Python equivalents of the core DAX measures were calculated from source frames and then from the written/reloaded portable model. `validation/powerbi_reconciliation.csv` contains 60 passing comparisons and no failures.

### Base portfolio

| Metric | Verified value |
|---|---:|
| Parking lots | 120 |
| Capacity | 23,685 |
| Average occupancy | 33.8952% |
| Total synthetic gross parking revenue | INR 2,226,063,620.57 |
| Acquire Now targets | 25 |
| Modelled monthly platform revenue | INR 6,052,472.71 |
| Average acquisition score | 45.1744 |
| Markets analyzed | 17 |
| Strong markets | 6 |
| BD conversion | 10.0% |

### Filter contexts

Reconciliation also passed under:

- Connaught Place only;
- Acquire Now only;
- Connaught Place and Acquire Now simultaneously;
- parking ID 52 only;
- the exact Top-10 ordering and scores.

For example, Connaught Place resolves to 11 lots, 1,849 spaces, 45.2750% occupancy, eight Acquire Now targets, INR 1,385,431.21 modelled monthly platform revenue, and 63.8873 average score.

## Top-10 reconciliation

The portable model exactly reproduces scoring/5 ranks 1-10: parking IDs 52, 18, 1, 51, 6, 17, 41, 3, 8, and 13.

## UX review

The five static actual-data mockups were reviewed as a first-pass BD-manager journey:

1. Page 1 shows the opportunity size, geographic distribution and Top 10 without scrolling.
2. Page 2 identifies Nehru Place and Connaught Place as leading average-score markets and exposes demand/coverage trade-offs.
3. Page 3 separates attractive-closeable lots from constrained or lower-attractiveness lots and provides the action list.
4. Page 4 explains the rank-1 lot through components, locality benchmarks, hourly demand, economics, competition, strengths and constraints.
5. Page 5 identifies the funnel drop-off, lead-source performance, robust recommendations and next actions.

The mockups answer the five requested questions within one page sequence. Power BI cross-filter, drill-through, bookmark, and reset-button behavior remains an assembly-time test because Power BI Desktop is unavailable.

## Required Power BI acceptance tests

On the Windows assembly machine:

1. Validate all headline values against the table above.
2. Apply a Connaught Place filter and compare against the reconciliation CSV.
3. Apply Acquire Now and the combined filter; verify no duplicated daily facts inflate totals.
4. Select parking 52; verify Page 4 values and Top-10 stability.
5. Test locality, parking type, owner type, priority and scenario together.
6. Verify Reset Filters returns to all markets and Base Case.
7. Confirm Page 5 funnel responds to lead-source and locality filters using dynamic measures, not aggregate tables.
8. Confirm the scenario slicer does not alter official base-case KPI cards.
9. Inspect blank and zero states, particularly division-by-zero measures.

## Problems and handling

- **No Power BI runtime:** produced a complete package and did not claim a PBIX/PBIP.
- **Scenario results exist in Python rather than a SQL view:** exported validated long-form scenario facts with a separate dimension; PostgreSQL remains primary for base entities/facts.
- **Competitor capacity is unavailable:** dashboard uses count, distance, price, and aggregator proxies and labels them accordingly.
- **Pre-aggregated funnel tables do not support arbitrary filters:** retained only as hidden reconciliation tables; dynamic DAX uses the lead-level fact.
- **Deep-dive reason flags are arrays/pipe lists:** documented a Power Query split-to-rows option; no reasons are fabricated.
