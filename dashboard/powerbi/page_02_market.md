# Page 2 - Market Opportunity

**Business question:** Which markets should PARK It Up expand in?

**Default state:** all 17 localities, base-case weights.

**Decision supported:** which micro-markets receive BD attention next, and which
are already served well enough to deprioritise.

## Layout

| Region | Grid | Contents |
| --- | --- | --- |
| KPI strip | cols 0-12, rows 0-3 | four market-level KPI cells |
| Primary | cols 0-7, rows 3-16 | demand against current coverage |
| Secondary | cols 7-12, rows 3-16 | opportunity ranking |
| Supporting | cols 0-12, rows 16-24 | market decision table |

The page carries no lot-level detail; that is Page 3's job.

## Visuals

1. **KPI strip** - `Markets Analyzed` with the four-way class split as its
   subtitle; the leading market by `avg_acquisition_score`; target concentration,
   the share of `ACQUIRE_NOW` lots held by the top four markets; and the count of
   markets at 0% modelled coverage.
2. **Demand against current coverage** (primary) - scatter of
   `parkitup_coverage_pct` against `avg_demand_score`, bubble size by
   `parking_count`. Portfolio medians split the plot into four regions washed in
   segment tints and labelled EXPAND, PRIORITISE, MONITOR and DEFEND. Points are
   green where `market_class = STRONG` and neutral otherwise, so this page does
   not introduce a second four-colour scheme competing with the segment palette.
   The empty PRIORITISE region is annotated, because its emptiness is the finding:
   no high-demand market is already well served.
3. **Opportunity ranking** (secondary) - top 10 localities by
   `avg_acquisition_score` as horizontal bars, value at the bar end, no axis.
   Bar colour repeats the strong / not-strong split from the scatter.
4. **Market decision table** - top 8 markets. Columns: locality, class, lots,
   capacity, demand, competition, coverage, opportunity, Acquire Now count.
   Coverage at or above 15% is flagged amber. A dash, not a zero, is shown where
   a market holds no targets.

## Interactions

- Selecting a scatter point or a ranking bar filters the decision table and the
  KPI strip.
- Selecting a locality enables drill-through to Page 3 pre-filtered to that
  market.
- The `Whitespace` column was removed: `whitespace_indicator` is
  `HIGH_WHITESPACE` for every market in the top eight, so the column displayed no
  variance. The underlying field is retained in the model and in tooltips.

## Acceptance checks

17 markets, split 6 strong / 3 emerging / 3 saturated / 5 weak. Nehru Place leads
at 66.1 with 9 targets. 92% of targets sit in four markets. 5 markets show 0%
coverage. Table values must match `DimLocality`.
