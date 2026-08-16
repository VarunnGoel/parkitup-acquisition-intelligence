# Data Sources and Refresh Contract

## Source precedence

1. **Primary:** PostgreSQL database `parkitup`, schema `parkitup`. The analytics views remain the relational source of truth.
2. **Portable fallback:** generated CSVs under `data/powerbi/`. They are refreshed by `python/analysis/prepare_powerbi.py` and are intended for inspection, portability, and a quick assembly build.
3. **Scenario layer:** validated scenario outputs are imported as `FactScenarioScore`, `FactScenarioComponent`, and `FactLocalityScenario`. The base score still comes from the official scoring result.

Never hand-edit a CSV. Regenerate it after a data or scoring change.

## PostgreSQL source mapping

| Model table | PostgreSQL source | Grain | Notes |
|---|---|---:|---|
| `DimParking` | `parking_lots` joined to `dim_locality`/`dim_city` | 1 row per parking lot | Static identity, coordinates, supply and tariff |
| `DimOwner` | `owners` | 1 row per owner | One owner may control multiple lots |
| `DimLocality` | `dim_locality` joined to `dim_city` and `vw_locality_summary` | 1 row per locality | Market metrics are analytics locality aggregates |
| `DimDate` | `dim_date` | 1 row per date | Mark as the official date table |
| `DimFunnelStage` | `dim_funnel_stage` | 1 row per stage | Ordered 1-7 |
| `DimScoreDimension` | `dim_score_dimension` | 1 row per pillar | Display order and descriptions |
| `DimPrioritySegment` | `segment_rule` | 1 row per segment | Thresholds and BD actions |
| `DimScenario` | validation `sensitivity_dashboard.csv` distinct scenario rows | 1 row per scenario | Persisted validation scenario catalogue |
| `FactDailyPerformance` | `fact_lot_daily` | 1 row per lot-date | 43,800 rows |
| `FactHourlyProfile` | `fact_lot_hourly_profile` | 1 row per lot-day type-hour | 5,760 rows |
| `FactAcquisitionScore` | `vw_parking_performance_summary` plus score fields and validation stability | 1 row per lot | Base-case headline and robustness fields |
| `FactScoreComponent` | `lot_dimension_score` for default weight set | 1 row per lot-pillar | Deep-dive decomposition |
| `FactOutreach` | `outreach` | 1 row per BD lead | Includes furthest stage order for dynamic funnel measures |
| `FactOutreachEvent` | `outreach_events` | 1 row per lead-stage event | Event-level chronology |
| `FactScenarioScore` | validation `sensitivity_dashboard.csv` | 1 row per lot-scenario | 120 x 11 |
| `FactScenarioComponent` | Long form of validation component scores and weights | 1 row per lot-scenario-pillar | Scenario explanation |
| `FactLocalityScenario` | validation `locality_sensitivity_dashboard.csv` | 1 row per locality-scenario | Locality rank movement |

`AggBDFunnel` and `AggBDConversion` are included as portable reconciliation references. Hide them in the report and use the dynamic `FactOutreach` measures for visuals that need slicers.

## Portable files

`data/powerbi/` contains one CSV per model table. The generated row counts are recorded in `validation/powerbi_execution_summary.json`; model and foreign-key checks are in `validation/powerbi_model_checks.csv`.

## Refresh sequence

```text
PostgreSQL / analytics views
          |
          v
make validate-all
          |
          v
python/analysis/prepare_powerbi.py
          |
          v
data/powerbi/*.csv + validation/powerbi_*.csv
```

The dashboard should not regenerate the synthetic dataset during a refresh. If the PostgreSQL source changes, rerun the pipeline and validation first, then refresh Power BI.

## Data notes shown in the report

- Score values are relative to the 120-lot candidate universe.
- Expected platform revenue is modelled gross monthly revenue, not profit.
- OSM-derived location fields are public but bounded in coverage.
- Occupancy, revenue, owner terms, outreach outcomes, and network coverage are synthetic or assumed.
