# Analytics Layer Contract — inputs the validation layer depends on

## Final SQL views

- `parkitup.vw_parking_performance_summary`: one row per lot with demand, revenue, efficiency, competition, network, and scores.
- `parkitup.vw_locality_summary`: one row per locality with candidate supply, coverage, whitespace, and acquisition counts.
- `parkitup.vw_parking_benchmarks`: one row per lot with locality/type comparisons and local ranks.
- `parkitup.vw_bd_funnel`: ordered funnel stages, reach, conversion, and drop-off.
- `parkitup.vw_bd_acquisition_targets`: BD-ready ordered target list and action group.
- `parkitup.vw_parking_rank_explanation`: filterable high/low ranking explanation with peer deltas and reason flags.
- Existing scoring views remain authoritative: `parking_acquisition_score`, `parking_component_scores`, `parking_acquisition_features`, and `bd_acquisition_targets`.

## Recommended Python inputs

- Use `vw_parking_performance_summary` for distributional EDA and efficiency relationships.
- Use `vw_parking_benchmarks` for peer residuals and outlier validation.
- Use `lot_scenario_score`, `sensitivity_summary`, and `lot_rank_stability` for scenario/rank analysis.
- Use `fact_lot_daily` only when daily trend/seasonality is required; do not reconstruct its existing parking-level aggregates.
- Use `fact_lot_hourly_profile` for hourly shapes and the documented data-defined peak-hour rule.

## Recommended Power BI inputs

- Executive and target pages: `vw_bd_acquisition_targets`.
- Market page: `vw_locality_summary`.
- Lot deep dive: `vw_parking_rank_explanation` joined/filter-linked by `parking_id`.
- Benchmark page: `vw_parking_benchmarks`.
- Funnel page: `vw_bd_funnel`, plus the source/owner queries in `sql/bd_funnel/bd_funnel_analysis.sql` if those cuts are required.

## Findings to retain

- Synthetic overall acquisition conversion: 10.00% (12/120).
- Largest proportional funnel drop: Documents Collected to Onboarded, 47.83%.
- Largest absolute pre-final drop: Contacted to Meeting Held, 31 leads.
- Leading independent whitespace markets: Connaught Place, Nehru Place, Karol Bagh, then uncovered Lajpat Nagar.
- Top target: parking 52, MCD Parking, Lajpat Nagar, acquisition score 78.53 and 100% top-10 stability.
- Portfolio peak-hour window from the data: 14:00-19:00 for both weekday and weekend profiles.

## Known limitations

- Operational, commercial, outreach, owner, and existing-network fields are synthetic.
- Competitor capacity is unavailable for every candidate; do not visualize null capacity as zero known supply.
- No explicit `INTERESTED` stage exists. Any `owner_interest_level >= 3` cut must be labeled as a proxy.
- Relative scores are calibrated to this 120-lot universe and are not predictive probabilities.

## Do not duplicate in the validation layer

- Do not recalculate scoring pillar or acquisition scores.
- Do not recreate parking/locality aggregates already exposed by the SQL analytics layer views.
- Do not invent a competitor-capacity estimate.
- Do not convert synthetic results into real-world claims.
- Do not build a second target-ranking definition outside `vw_bd_acquisition_targets`.
