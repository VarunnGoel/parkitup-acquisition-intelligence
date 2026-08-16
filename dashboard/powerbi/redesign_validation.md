# dashboard-redesign Redesign Validation

Repository-side checks for the dashboard redesign. This does not substitute for
Power BI Desktop interaction testing, which cannot be run on this host.

## What `make dashboard` does

1. regenerates the five previews from the current `data/powerbi/` extracts;
2. runs `python/visualization/layout_audit.py`;
3. runs `tests/test_dashboard.py`.

## Layout audit

`layout_audit.py` rebuilds each page in memory and, for every chart, compares its
`get_tightbbox` - which includes tick labels, axis titles and in-chart text -
against the bounds of the card hosting it. It also checks that no text leaves the
canvas and that no two cards overlap.

Executed result:

```
page_01_executive_overview: OK
page_02_market_opportunity: OK
page_03_acquisition_matrix: OK
page_04_parking_deep_dive: OK
page_05_bd_strategy: OK

0 layout violation(s) total
```

The audit is also proved capable of failing.
`test_layout_audit_fails_when_padding_is_removed` rebuilds Page 3 with the
card padding set to zero, which reproduces the dashboard geometry exactly, and
asserts that violations are reported. With zero padding the audit reports
`chart decorations overflow their card by 38 px`.

This test exists because the first version of the audit passed a deliberately
broken page: it iterated `fig.axes`, and inset charts are children of their parent
axes rather than members of `fig.axes`, so it had inspected nothing at all.

## Displayed-figure reconciliation

`test_displayed_figures_reconcile_with_the_portable_model` asserts that
every headline number printed on a page comes from the extracts, including the
three segmentation thresholds, the `DEVELOP` band bounds, and that all hours
outside the selected lot's operating window hold zero occupancy.

Executed: 33 of 33 figure checks passed, covering totals, revenue at stake, market
counts and split, target concentration, segment counts, the deep-dive lot's
occupancy and revenue against its market, and the full funnel and loss-reason
distribution.

## Visual review, executed against the rendered images

Each item below was checked by rendering the page and inspecting the PNG, not by
reading the code.

- [x] Horizontal navigator with an active-page indicator on all five pages.
- [x] Header carries page title, business question, scope and base-case weights.
- [x] No axis label, tick label or legend crosses into a neighbouring card.
- [x] No category label is clipped at a card or canvas edge.
- [x] Map labels for all five leading markets are visible and do not overlap;
      collision-avoiding placement was added after Nehru Place, the largest
      market, was found hidden behind its neighbour's label.
- [x] Page 2 labels for points near the plot edge are placed sideways so the box
      stays inside the plot.
- [x] Page 3 matrix carries no legend and every point sits on the wash of its own
      segment.
- [x] Page 4 score bars and locality reference markers are readable together, and
      the feasibility rule sits between Strategic Fit and Acquisition Feasibility.
- [x] Page 4 uses one name per statistic: the p90 figure is labelled
      `Peak occupancy (p90)` and the hourly maximum is labelled `busiest hour`.
- [x] Page 5 funnel and loss-reason labels sit inside their chart areas.
- [x] Every rupee value on a page uses the same unit.
- [x] Footer provenance is on one baseline and names no internal build stages.

## Known validation boundary

The previews validate layout, labels, field mapping, units and current values.
They cannot validate Power BI filter propagation, drill-through, bookmark
behaviour, accessibility metadata or DAX evaluation in a running report. Those
remain in [build_checklist.md](build_checklist.md) for the Power BI Desktop
assembly.

## Latest executed results

Run on this host:

- Layout audit: 5 pages, 0 violations.
- Layout audit negative control: fails as required.
- Dashboard tests: 6 of 6 passed.
- Displayed-figure reconciliation: 33 of 33 passed.
- Source reconciliation `validation/powerbi_reconciliation.csv`: 60 of 60 PASS,
  produced by the most recent `make powerbi-data`.

Not re-run on this host: `pytest` is not installed in the sandbox that executed
these checks, so the dashboard-redesign tests were executed directly through a runner
rather than under pytest, and the wider regression suite
(`make test`) was not re-executed. Both should be run on the macOS host with
`make dashboard` and `make test` before this work is considered closed.
