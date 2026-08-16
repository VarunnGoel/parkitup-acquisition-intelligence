# Python Analytics and Model Validation

## Purpose

the validation layer uses Python for work that is awkward or less transparent in relational SQL: distribution profiling, association diagnostics, controlled scenario recalculation, rank stability, adversarial stress tests, monotonicity checks, and analytical charts.

The layer answers a narrower question than the reporting layer:

> Do the data and scoring model support the acquisition recommendations, and which recommendations remain credible when assumptions change?

It does not treat synthetic observations as evidence about the real Delhi NCR parking market. The implementation demonstrates an auditable analytical method.

## Responsibility split

| Layer | Responsibility |
|---|---|
| PostgreSQL base tables | Typed, constrained source and fact data |
| SQL views | Joins, relational metrics, parking/locality summaries, funnel logic, dashboard source grains |
| scoring Python engine | Feature transforms, five component scores, segment rules, scenario scoring |
| validation Python | EDA, statistical diagnostics, sensitivity, rank stability, stress tests, monotonicity, exports and charts |
| Power BI | Business-facing reporting and cross-filtered decisions in the dashboard package |

Complex analytics joins are not recreated in Pandas. `python/analysis/data_access.py` reads named SQL views where a view already supplies the correct grain. Daily and hourly tables are read only when their native time grain is required.

## Architecture

```text
PostgreSQL tables and analytics views
              |
              v
python/analysis/data_access.py
              |
      +-------+--------+
      |                |
      v                v
EDA and profiling   score_scenario
      |                |
      +-------+--------+
              v
diagnostics, scenarios, rank stability
              |
      +-------+--------+
      |                |
      v                v
validation artifacts  dashboard-ready CSVs
```

The model has one source of truth. The validation layer imports `score_scenario`, `classify_segments`, `winsor_score`, and `COMPONENT_COLUMNS` from `python/analysis/scoring_engine.py`. It never defines a second base scoring formula.

## Module structure

| Module | Responsibility |
|---|---|
| `python/analysis/data_access.py` | Environment-driven PostgreSQL connection and named analytical loaders |
| `python/analysis/profiling.py` | Dataset shape, missingness, duplicates, percentiles and suspicious-distribution flags |
| `python/analysis/eda.py` | Demand, economics, competition, market and BD summaries |
| `python/analysis/statistics.py` | SciPy-free Spearman correlation using Pearson correlation of average ranks |
| `python/model_validation/diagnostics.py` | Component influence, base reconciliation, monotonicity and outlier review |
| `python/model_validation/sensitivity.py` | Weight validation, business scenarios, revenue grids, locality effects and rank stability |
| `python/model_validation/stress_tests.py` | Six deliberately difficult synthetic score cases |
| `python/visualization/charts.py` | Twelve purposeful, non-interactive matplotlib figures |
| `python/analysis/run_validation.py` | End-to-end orchestration and artifact export |

The four notebooks are narrative consumers of these modules:

1. `01_data_quality.ipynb`: source contracts and profiling.
2. `02_eda.ipynb`: parking, demand, economics, competition, market and BD exploration.
3. `03_acquisition_model_validation.ipynb`: reconciliation, influence, stress, monotonicity and outliers.
4. `04_sensitivity_analysis.ipynb`: scenarios, rank stability, locality movement and revenue sensitivity.

Each notebook begins with its objective, source and methodology, and ends with findings and limitations.

## Data extraction contract

Credentials come only from environment variables or the git-ignored `.env`; `.env.example` contains placeholders. The executed validation source checks require:

- 120 parking-level score, component and performance rows;
- 17 locality rows;
- 43,800 daily rows, exactly 365 per lot;
- 5,760 typical-hour rows, exactly 48 per lot;
- 120 outreach leads;
- unique `parking_id` at every parking-level analytical grain.

The full run failed loudly until every contract passed.

## Statistical methods

### Profiling

For important columns the profiler reports count, type, missingness, unique count, full-row duplicates, minimum, maximum, mean, median, standard deviation and the 1st, 5th, 25th, 75th, 95th and 99th percentiles. Rule-based flags identify high missingness, constants, zero inflation, skew and boundary concentration. A flag requests review; it is not an instruction to delete data.

### Relationships

Pearson and Spearman correlations are reported where useful. Spearman is implemented as Pearson correlation of average ranks, avoiding an unnecessary SciPy dependency. Scatter-plot trend lines are descriptive only. The language throughout is "associated with" rather than causal language.

### Component influence

Three diagnostics are combined:

- correlation between each component and final score;
- standard deviation of its weighted contribution;
- rank movement after replacing that component with its portfolio median while holding the others fixed.

This separates a high correlation caused by legitimate data variation from unexpected model domination. No weight is automatically changed.

## Sensitivity methodology

Weights must contain exactly Demand, Revenue, Competition, Strategic Fit and Feasibility; they must be non-negative and sum to 1.0 or 100%. The reusable public function accepts all five explicit weights.

Eleven scenarios are evaluated:

| Scenario | Change from base |
|---|---|
| Base Case | Official scoring assumptions, 30/25/15/15/15 weights |
| Conservative | Demand 0.85x, booking share 0.90x, commission 0.80x, dwell 0.95x, onboarding cost 1.25x |
| Growth | Demand 1.15x, booking share 1.10x, commission 1.05x |
| Acquisition Cost Pressure | Onboarding cost 1.50x |
| Competitive Pressure | Competition opportunity component 0.75x |
| Network Expansion | Planned hypothetical sites included in network coverage |
| Demand Heavy | 40/20/15/15/10 |
| Revenue Heavy | 20/40/15/15/10 |
| Feasibility Heavy | 25/20/15/15/25 |
| Strategic Growth | 25/20/10/30/15 |
| Equal Weight Control | 20/20/20/20/20 |

For each lot, stability reports Top-10, Top-20 and Top-50 frequency, average rank, best rank, worst rank and population rank standard deviation. Stability classes are scenario-set-relative:

- Very Stable: Top-10 frequency at least 90%.
- Stable: at least 70%.
- Sensitive: at least 40%.
- Highly Sensitive: below 40%.

The robust-target table is therefore not simply the base Top 10.

## Revenue sensitivity

The reusable grid evaluates explicit occupancy levels, price multipliers and per-lot or global commission assumptions. Outputs are calculated, not hard-coded. They represent expected gross platform revenue, not profit or contribution, because all platform operating costs are not modelled.

## Stress and sanity tests

Six adversarial cases are executed alongside the observed portfolio:

1. Huge lot with extremely low occupancy must not rank near the top.
2. Small, highly utilised, high-demand lot must have a credible high rank.
3. High price with weak demand must not appear attractive by price alone.
4. Extreme competition must reduce opportunity relative to a thin-competition twin.
5. Low owner willingness must materially constrain a high-demand lot.
6. A network gap must visibly improve an otherwise moderate twin.

Monotonicity checks independently confirm that increasing demand cannot lower Demand Score, increasing commission cannot lower Revenue Score, increasing onboarding cost cannot improve Feasibility, increasing willingness cannot reduce Feasibility, and increasing competitor count cannot improve Competition Opportunity while other inputs are controlled.

## Executed results

- All source contracts passed.
- All six stress tests passed.
- All five monotonicity tests passed with zero violations.
- The base rerun matched all 120 official the scoring engine ranks and segments.
- Maximum acquisition-score difference was 0.00499, caused by comparing full-precision recalculation with two-decimal persisted output.
- Revenue and demand are the strongest final-score associations (Spearman 0.88 and 0.83), but neutralisation tests show that both materially affect rank and neither fully determines it.
- The data-defined portfolio peak window is 14:00-19:00 on weekdays and weekends.
- Seven lots remain Top 10 in all 11 scenarios; parking 52 is the most stable with average rank 1.27 and worst rank 2.

## Outlier policy

No outlier is removed automatically. Extreme values are reviewed for schema plausibility, provenance, data-quality evidence and model distortion. The identified extremes are plausible within the synthetic generator and retained. Continuous scoring transforms already use 5th/95th percentile anchors where documented, limiting domination without altering source facts.

## Outputs

Primary analytical evidence is written to `validation/validation_*.csv`, `validation/validation_execution_summary.json`, `validation/validation_findings.md`, and `validation/figures/`.

Portable dashboard inputs are:

- `data/processed/parking_dashboard.csv`
- `data/processed/locality_dashboard.csv`
- `data/processed/acquisition_targets.csv`
- `data/processed/bd_funnel_dashboard.csv`
- `data/processed/bd_conversion_dashboard.csv`
- `data/processed/sensitivity_dashboard.csv`
- `data/processed/locality_sensitivity_dashboard.csv`
- `data/processed/revenue_sensitivity_dashboard.csv`

PostgreSQL views remain the preferred source of truth where Power BI can connect directly. CSVs exist for review, portability and environments without the database connection.

## Execution

```bash
make validate
make notebooks
```

`make validate` runs extraction, EDA, validation, charts and exports. `make notebooks` executes all four notebooks in place so stored outputs are reviewable.

## Limitations

- There are no real acquisition outcomes, so internal validity is tested but predictive accuracy is unknown.
- Synthetic relationships partly reflect generator assumptions and must not be presented as market discoveries.
- Public OSM coverage is bounded and sparse.
- Competitor capacity is unavailable.
- The live-network baseline is hypothetical.
- Scores, percentile anchors, thresholds and market classes are relative to the current candidate universe.
- Scenario robustness is conditional on the selected scenario set and bounds.
- Correlation and descriptive regression lines do not identify causal effects.
