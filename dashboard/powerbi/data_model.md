# Power BI Data Model

## Design

The report uses a small star-shaped model with `DimParking` as the central conformed dimension. `DimLocality` and `DimOwner` filter it; `DimParking` filters performance, score, scenario, and outreach facts. All relationships are single-direction unless Power BI requires a documented exception.

## Tables

### Dimensions

| Table | Key | Purpose |
|---|---|---|
| `DimParking` | `parking_id` | Lot identity, coordinates, capacity, type, tariff, operating hours, capacity band |
| `DimOwner` | `owner_id` | Operator type, readiness, management and negotiation context |
| `DimLocality` | `locality_id` | Market identity, city, demand, coverage and whitespace context |
| `DimDate` | `activity_date` | Daily date slicing and time labels |
| `DimFunnelStage` | `stage_id` | Ordered BD funnel stages |
| `DimScoreDimension` | `dimension_code` | Five scoring pillars and display order |
| `DimPrioritySegment` | `segment_code` | Acquire/Pursue/Develop/Avoid rules and actions |
| `DimScenario` | `scenario_id` | Base, business, and weighting scenarios |

### Facts and aggregates

| Table | Grain | Primary use |
|---|---|---|
| `FactDailyPerformance` | parking-date | Revenue, occupancy, bookings, entries and daily trend |
| `FactHourlyProfile` | parking-day type-hour | Peak-window and deep-dive hourly profile |
| `FactAcquisitionScore` | parking lot | Base recommendation, score, rank, reasons and stability |
| `FactScoreComponent` | parking lot-pillar | Base score decomposition |
| `FactScenarioScore` | parking lot-scenario | Rank and score movement under validation assumptions |
| `FactScenarioComponent` | parking lot-scenario-pillar | Scenario score decomposition |
| `FactLocalityScenario` | locality-scenario | Market rank movement |
| `FactOutreach` | lead | BD pipeline and conversion |
| `FactOutreachEvent` | lead-stage event | Funnel chronology and event analysis |
| `AggBDFunnel` | stage | Static reconciliation reference; hide in report |
| `AggBDConversion` | dimension-segment | Static reconciliation reference; hide in report |

## Model rules

- Mark `DimDate` as the date table using `DimDate[activity_date]`.
- Sort `DimFunnelStage[stage_name]` by `stage_order`.
- Sort `DimPrioritySegment[segment_label]` by `segment_sort_order`.
- Sort `DimScenario[scenario_code]` by `scenario_id` or a documented display-order column.
- Treat `FactAcquisitionScore` as the base-case fact. Do not mix it with `FactScenarioScore` in a single headline KPI.
- Use `FactScenarioScore` for sensitivity visuals and explicitly label the selected scenario.
- Do not use the pre-aggregated funnel tables for filtered visuals; their values are global snapshots.
- Hide technical keys and provenance fields from the report view, but retain them in the model for validation and drill-through.

## Recommended report field folders

| Folder | Fields |
|---|---|
| `01 Identity` | lot code/name, locality, city, owner, parking type |
| `02 Supply` | capacity, hourly rate, operating hours, coordinates |
| `03 Performance` | occupancy, entries, bookings, gross revenue |
| `04 Model` | five scores, attractiveness, acquisition score, segment, rank |
| `05 Robustness` | Top-10/20 frequency, average/best/worst rank, standard deviation |
| `06 BD` | lead source, pipeline status, assigned rep, action/recommendation |
| `07 Scenario` | scenario code, multipliers, weights, rank/score change |
