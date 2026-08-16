# Exact Field Mappings

## Global controls

| Control | Field | Scope |
|---|---|---|
| Locality | `DimLocality[locality_name]` | Sync pages 1-3 and 5; do not sync to drill-through page 4 |
| Parking type | `DimParking[parking_type]` | Sync pages 1-3 |
| Priority segment | `DimPrioritySegment[segment_label]` | Sync pages 1 and 3; page 5 may use its own |
| Scenario | `DimScenario[scenario_code]` | Page 5 robustness only; force single select |
| Parking lot selector | `DimParking[parking_display_name]` | Page 4 only; force single select and searchable dropdown |

## Page 1 - Executive Overview

| Visual | Category / detail | Values | Encoding |
|---|---|---|---|
| KPI cards | None | `Total Parking Lots`, `Total Capacity`, `High Priority Count`, `Expected Monthly Platform Revenue`, `High Opportunity Markets`, `Average Acquisition Score` | Display units and caveat subtitles |
| Opportunity map | `DimParking[lot_name]`, latitude, longitude | `Total Capacity` or `Expected Monthly Platform Revenue` | Size = capacity; legend = `priority_segment` |
| Top-target table | `acquisition_rank`, lot, locality, capacity, segment | score, monthly revenue, feasibility | Visual-level filter Top N 10 by acquisition rank |
| Priority breakdown | `DimPrioritySegment[segment_label]` | `Priority Segment Count` | Fixed segment sort order and colors |
| Takeaway text | Static findings from the validation layer | None | Do not imply live narrative generation |

## Page 2 - Market Opportunity

| Visual | Category / detail | Values | Encoding |
|---|---|---|---|
| KPI cards | locality context | `Markets Analyzed`, selected top market, `High Priority Count`, `Total Capacity`, `Average Demand Score` | Filter-aware |
| Locality rank bar | `DimLocality[locality_name]` | `avg_acquisition_score` | Data color = `market_class`; sort descending |
| Demand/coverage matrix | locality name | X `parkitup_coverage_pct`; Y `avg_demand_score`; size `parking_count` | Legend = `market_class`; reference lines at medians |
| Market table | locality | counts, capacity, demand, competition, score, high priority, coverage, whitespace | Conditional formatting on score and whitespace |

## Page 3 - Acquisition Priority Matrix

| Visual | Category / detail | Values | Encoding |
|---|---|---|---|
| Main scatter | `DimParking[parking_id]`, lot name | X feasibility; Y attractiveness; size capacity | Legend = priority segment; quadrant reference lines from threshold measures |
| Segment cards | priority segment | `Priority Segment Count` | Four cards |
| Top-20 table | rank, lot, locality, segment | acquisition score, revenue, feasibility, Top-10 stability | Sort by rank; visual-level Top N 20 |
| Slicers | locality, parking type, owner type, priority | score/capacity numeric range | Page-specific, except documented global slicers |

## Page 4 - Parking Lot Deep Dive

| Visual | Category / detail | Values | Encoding |
|---|---|---|---|
| Header | lot name, locality, type | capacity, tariff, segment | Drill-through on `parking_id` |
| Component bar | `DimScoreDimension[dimension_name]` | `Pillar Score` | Sort by display order; show 0-100 axis |
| Locality benchmark | metric names | selected lot values and locality-average measures | Matrix or disconnected metric selector |
| Hourly occupancy | `FactHourlyProfile[hour_of_day]` | average occupancy | Legend = day type |
| Daily trend | `DimDate[activity_date]` | average occupancy or gross revenue | Optional toggle/bookmark; do not crowd default view |
| Competition cards | None | count 500m/1km, distance proxy, competitor tariff, tariff delta | Show units and proxy label |
| Strengths/constraints | reason flag columns | None | Split pipe-delimited strings in Power Query if list rows are preferred |

## Page 5 - BD Strategy and Action Center

| Visual | Category / detail | Values | Encoding |
|---|---|---|---|
| KPI cards | current filters | lead count, onboarded, conversion, cycle time, steepest drop, robust count | Synthetic caveat visible |
| Funnel | `DimFunnelStage[stage_name]` | `Funnel Stage Leads`, conversion rate | Sort by stage order |
| Conversion by source | `FactOutreach[lead_source]` | onboarded count, lead count, conversion rate | Show volume label; exclude groups below chosen minimum only with visible note |
| Conversion by owner | `DimOwner[owner_type]` | conversion rate and lead count | No causal language |
| Robust-target table | lot, locality | base rank, average/best/worst, Top-10/20 frequency | Sort Top-10 frequency desc then average rank asc |
| BD action table | rank, lot, locality, segment | score, feasibility, revenue, stability, recommended action | Visual filter to actionable segments; sortable |
| Scenario comparison | lot/scenario | base and selected rank, rank change | Single-select scenario slicer |

## Tooltips

Create a report-page tooltip `Parking Tooltip` at 320 x 240 pixels with:

- `DimParking[lot_name]`
- `DimLocality[locality_name]`
- `DimParking[capacity_cars]`
- `Selected Acquisition Score`
- demand, revenue, feasibility and competition scores
- priority segment
- `Top 10 Stability %`

Create a second `Market Tooltip` with locality, parking count, capacity, demand, coverage, whitespace, average score, and high-priority count.
