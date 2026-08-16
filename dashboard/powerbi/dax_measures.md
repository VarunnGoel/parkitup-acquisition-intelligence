# DAX Measures

The formulas below assume the table names and active relationships in `relationships.md`. Create a dedicated empty `Measures` table and place all measures there. Set percentage, currency, whole-number, and decimal formats in the model rather than embedding `FORMAT()` in numeric measures.

Power BI Desktop was unavailable in the development environment, so these measures were not executed by a DAX engine. Their source-equivalent calculations and filter contexts were reconciled in Python across overall, locality, priority, combined-filter, and single-lot scopes; see `validation/powerbi_reconciliation.csv`.

## Portfolio and economics

```DAX
Total Parking Lots =
DISTINCTCOUNT(DimParking[parking_id])

Total Capacity =
SUM(DimParking[capacity_cars])

Average Occupancy % =
AVERAGE(FactDailyPerformance[avg_occupancy_rate])

Peak Occupancy % =
AVERAGE(FactDailyPerformance[peak_occupancy_rate])

Total Gross Parking Revenue =
SUM(FactDailyPerformance[gross_parking_revenue_inr])

Revenue per Space =
DIVIDE([Total Gross Parking Revenue], [Total Capacity])

Expected Monthly Platform Revenue =
SUM(FactAcquisitionScore[expected_monthly_platform_revenue_inr])

Expected Annual Platform Revenue =
[Expected Monthly Platform Revenue] * 12

Average Acquisition Score =
AVERAGE(FactAcquisitionScore[acquisition_score])

Selected Acquisition Score =
MAX(FactAcquisitionScore[acquisition_score])

Selected Attractiveness Score =
MAX(FactAcquisitionScore[attractiveness_score])

Selected Feasibility Score =
MAX(FactAcquisitionScore[feasibility_score])

Selected Acquisition Rank =
MIN(FactAcquisitionScore[acquisition_rank])
```

Format `Average Occupancy %` and `Peak Occupancy %` as Percentage with one decimal. The underlying data is 0-1.

## Priority and market

```DAX
High Priority Count =
CALCULATE(
    DISTINCTCOUNT(FactAcquisitionScore[parking_id]),
    FactAcquisitionScore[priority_segment] = "ACQUIRE_NOW"
)

Pursue Count =
CALCULATE(
    DISTINCTCOUNT(FactAcquisitionScore[parking_id]),
    FactAcquisitionScore[priority_segment] = "PURSUE"
)

Priority Segment Count =
DISTINCTCOUNT(FactAcquisitionScore[parking_id])

Priority Segment Share =
DIVIDE(
    [Priority Segment Count],
    CALCULATE([Priority Segment Count], REMOVEFILTERS(DimPrioritySegment))
)

Markets Analyzed =
DISTINCTCOUNT(DimLocality[locality_id])

High Opportunity Markets =
CALCULATE(
    DISTINCTCOUNT(DimLocality[locality_id]),
    DimLocality[market_class] = "STRONG"
)

Average Demand Score =
AVERAGE(FactAcquisitionScore[demand_score])

Average Competition Opportunity =
AVERAGE(FactAcquisitionScore[competition_score])

Market Whitespace Score =
AVERAGE(DimLocality[market_whitespace_score])

PARK It Up Coverage % =
AVERAGE(DimLocality[parkitup_coverage_pct]) / 100
```

## Dynamic funnel and BD

```DAX
BD Lead Count =
DISTINCTCOUNT(FactOutreach[lead_id])

BD Onboarded Count =
CALCULATE(
    DISTINCTCOUNT(FactOutreach[lead_id]),
    FactOutreach[pipeline_status] = "Won"
)

Overall Conversion Rate =
DIVIDE([BD Onboarded Count], [BD Lead Count])

Average Days to Conversion =
CALCULATE(
    AVERAGE(FactOutreach[days_to_conversion]),
    FactOutreach[pipeline_status] = "Won"
)

Active Lead Count =
CALCULATE(
    DISTINCTCOUNT(FactOutreach[lead_id]),
    FactOutreach[pipeline_status] = "Active"
)

Funnel Stage Leads =
VAR StageOrder = SELECTEDVALUE(DimFunnelStage[stage_order])
RETURN
    IF(
        ISBLANK(StageOrder),
        BLANK(),
        CALCULATE(
            DISTINCTCOUNT(FactOutreach[lead_id]),
            REMOVEFILTERS(DimFunnelStage),
            FILTER(
                ALL(FactOutreach[furthest_stage_order]),
                FactOutreach[furthest_stage_order] >= StageOrder
            )
        )
    )

Stage-to-Stage Conversion Rate =
VAR StageOrder = SELECTEDVALUE(DimFunnelStage[stage_order])
VAR CurrentLeads = [Funnel Stage Leads]
VAR PriorLeads =
    CALCULATE(
        [Funnel Stage Leads],
        REMOVEFILTERS(DimFunnelStage),
        FILTER(
            ALL(DimFunnelStage),
            DimFunnelStage[stage_order] = StageOrder - 1
        )
    )
RETURN
    IF(StageOrder = 1, 1, DIVIDE(CurrentLeads, PriorLeads))

Stage Drop-off Count =
VAR StageOrder = SELECTEDVALUE(DimFunnelStage[stage_order])
VAR CurrentLeads = [Funnel Stage Leads]
VAR PriorLeads =
    CALCULATE(
        [Funnel Stage Leads],
        REMOVEFILTERS(DimFunnelStage),
        FILTER(
            ALL(DimFunnelStage),
            DimFunnelStage[stage_order] = StageOrder - 1
        )
    )
RETURN
    IF(StageOrder = 1, BLANK(), PriorLeads - CurrentLeads)

Steepest Drop-off Stage =
VAR CandidateStages =
    FILTER(
        ADDCOLUMNS(
            ALL(DimFunnelStage),
            "__conversion", CALCULATE([Stage-to-Stage Conversion Rate])
        ),
        DimFunnelStage[stage_order] > 1
    )
VAR WorstStage =
    TOPN(1, CandidateStages, [__conversion], ASC, DimFunnelStage[stage_order], ASC)
RETURN
    CONCATENATEX(WorstStage, DimFunnelStage[stage_name], "")
```

## Component explanation and locality benchmark

```DAX
Pillar Score =
AVERAGE(FactScoreComponent[subscore])

Pillar Weight =
MAX(FactScoreComponent[weight_applied])

Pillar Contribution =
SUM(FactScoreComponent[weighted_contribution])

Pillar Portfolio Mean =
CALCULATE(
    AVERAGE(FactScoreComponent[subscore]),
    REMOVEFILTERS(DimParking),
    REMOVEFILTERS(DimLocality),
    REMOVEFILTERS(DimOwner)
)

Pillar vs Portfolio Mean =
[Pillar Score] - [Pillar Portfolio Mean]

Selected Lot Locality Average Score =
VAR LocalityId = SELECTEDVALUE(DimParking[locality_id])
RETURN
    CALCULATE(
        AVERAGE(FactAcquisitionScore[acquisition_score]),
        REMOVEFILTERS(DimParking),
        TREATAS({LocalityId}, DimParking[locality_id])
    )

Selected Lot Locality Average Demand =
VAR LocalityId = SELECTEDVALUE(DimParking[locality_id])
RETURN
    CALCULATE(
        AVERAGE(FactAcquisitionScore[demand_score]),
        REMOVEFILTERS(DimParking),
        TREATAS({LocalityId}, DimParking[locality_id])
    )

Competitor Count within 1 km =
MAX(FactAcquisitionScore[competitor_count_1km])

Tariff vs Competitor =
SELECTEDVALUE(DimParking[hourly_rate_inr])
    - MAX(FactAcquisitionScore[competitor_avg_hourly_rate_inr])

Recommended Action =
VAR SegmentCode = SELECTEDVALUE(FactAcquisitionScore[priority_segment])
RETURN
    LOOKUPVALUE(
        DimPrioritySegment[bd_action],
        DimPrioritySegment[segment_code], SegmentCode
    )
```

## Robustness and scenario

```DAX
Top 10 Stability % =
AVERAGE(FactAcquisitionScore[top_10_frequency_pct]) / 100

Top 20 Stability % =
AVERAGE(FactAcquisitionScore[top_20_frequency_pct]) / 100

Robust Top 10 Count =
COUNTROWS(
    FILTER(
        VALUES(FactAcquisitionScore[parking_id]),
        CALCULATE(MAX(FactAcquisitionScore[top_10_frequency_pct])) = 100
    )
)

Average Scenario Rank =
AVERAGE(FactScenarioScore[rank_overall])

Scenario Acquisition Score =
AVERAGE(FactScenarioScore[acquisition_score])

Scenario Rank Change =
AVERAGE(FactScenarioScore[rank_change_vs_base])

Scenario Score Change =
AVERAGE(FactScenarioScore[score_change_vs_base])

Scenario High Priority Count =
CALCULATE(
    DISTINCTCOUNT(FactScenarioScore[parking_id]),
    FactScenarioScore[segment_code] = "ACQUIRE_NOW"
)

Scenario Pillar Score =
AVERAGE(FactScenarioComponent[subscore])

Scenario Pillar Contribution =
SUM(FactScenarioComponent[weighted_contribution])
```

`rank_change_vs_base` is defined as base rank minus scenario rank, so a positive value means the lot moved up.

## Matrix boundaries and comparison ranks

```DAX
Acquire Now Attractiveness Threshold =
CALCULATE(
    MAX(DimPrioritySegment[min_attractiveness]),
    REMOVEFILTERS(DimPrioritySegment),
    DimPrioritySegment[segment_code] = "ACQUIRE_NOW"
)

Acquire Now Feasibility Threshold =
CALCULATE(
    MAX(DimPrioritySegment[min_feasibility]),
    REMOVEFILTERS(DimPrioritySegment),
    DimPrioritySegment[segment_code] = "ACQUIRE_NOW"
)

Naive Capacity Rank =
RANKX(
    ALLSELECTED(DimParking[parking_id]),
    CALCULATE(MAX(DimParking[capacity_cars])),
    ,
    DESC,
    Dense
)

Model vs Capacity Rank Gap =
[Naive Capacity Rank] - [Selected Acquisition Rank]

Owner Lot Count =
DISTINCTCOUNT(DimParking[parking_id])

Owner Combined Capacity =
SUM(DimParking[capacity_cars])
```

## Dynamic text

```DAX
Scenario Label =
"Current scenario: " & COALESCE(SELECTEDVALUE(DimScenario[scenario_code]), "Select one")

Selected Parking Header =
COALESCE(SELECTEDVALUE(DimParking[lot_name]), "Select one parking lot")

Model Caveat =
"Synthetic decision-support model. Scores are relative to the current candidate universe."
```

## the dashboard redesign additions

Measures introduced by the redesign. All are additive to the dashboard set; none
replace an existing definition.

```dax
-- Page 1: revenue attached only to lots worth acting on now
Revenue At Stake =
CALCULATE(
    [Expected Monthly Platform Revenue],
    KEEPFILTERS(DimPrioritySegment[segment_code] = "ACQUIRE_NOW")
)

-- Page 1 and 2: how concentrated the actionable targets are
Target Concentration Pct =
VAR Targets = [High Priority Count]
VAR TopMarkets =
    TOPN(
        4,
        SUMMARIZE(ALLSELECTED(DimLocality), DimLocality[locality_id]),
        CALCULATE([High Priority Count]),
        DESC
    )
VAR InTopMarkets = CALCULATE([High Priority Count], TopMarkets)
RETURN DIVIDE(InTopMarkets, Targets)

-- Page 1: lots that clear the attractiveness bar but fail the feasibility bar.
-- The count the BD team cannot fix with more outreach.
Attractive But Blocked =
CALCULATE(
    COUNTROWS(FactAcquisitionScore),
    FILTER(
        FactAcquisitionScore,
        FactAcquisitionScore[attractiveness_score] >= [Acquire Now Attractiveness Threshold]
            && FactAcquisitionScore[feasibility_score] < [Acquire Now Feasibility Threshold]
    )
)

-- Page 2: markets with no modelled network presence
Untouched Market Count =
CALCULATE(
    DISTINCTCOUNT(DimLocality[locality_id]),
    FILTER(ALLSELECTED(DimLocality), DimLocality[parkitup_coverage_pct] = 0)
)

-- Page 3: the third segmentation threshold, needed for the Develop band.
-- Without it the matrix washes Avoid lots as Develop.
Develop Attractiveness Floor =
CALCULATE(
    MIN(DimPrioritySegment[min_attractiveness]),
    DimPrioritySegment[segment_code] = "DEVELOP"
)

-- Page 3 and 5: robustness, stated over the scenario set in DimScenario
Top 10 Persistence =
AVERAGE(FactAcquisitionScore[top_10_frequency_pct]) / 100

-- Page 4: locality average of a component subscore, for the reference marker
Component Locality Average =
VAR Market = SELECTEDVALUE(DimParking[locality_id])
RETURN
CALCULATE(
    AVERAGE(FactScoreComponent[subscore]),
    ALLEXCEPT(FactScoreComponent, DimScoreDimension[dimension_code]),
    FILTER(ALL(DimParking), DimParking[locality_id] = Market)
)

Component Gap Vs Locality =
[Component Subscore] - [Component Locality Average]

-- Page 4: peer average excludes the selected lot, otherwise the lot dilutes
-- the benchmark it is being compared against
Locality Peer Average Occupancy =
VAR Market = SELECTEDVALUE(DimParking[locality_id])
VAR ThisLot = SELECTEDVALUE(DimParking[parking_id])
RETURN
CALCULATE(
    AVERAGE(FactAcquisitionScore[avg_occupancy_rate]),
    FILTER(
        ALL(DimParking),
        DimParking[locality_id] = Market && DimParking[parking_id] <> ThisLot
    )
)

-- Page 4: restrict the hourly trend to the site's operating hours so a closing
-- time does not render as demand collapsing to zero
Hourly Occupancy In Operating Hours =
VAR OpenHour = HOUR(SELECTEDVALUE(DimParking[opens_at]))
VAR CloseHour = HOUR(SELECTEDVALUE(DimParking[closes_at]))
VAR Is24x7 = SELECTEDVALUE(DimParking[is_24x7])
RETURN
CALCULATE(
    AVERAGE(FactHourlyProfile[avg_occupancy_rate]),
    KEEPFILTERS(
        Is24x7
            || (FactHourlyProfile[hour_of_day] >= OpenHour
                && FactHourlyProfile[hour_of_day] < CloseHour)
    )
)

Busiest Hour Label =
VAR Best =
    TOPN(1, VALUES(FactHourlyProfile[hour_of_day]), [Hourly Occupancy In Operating Hours], DESC)
RETURN
FORMAT(MAXX(Best, FactHourlyProfile[hour_of_day]), "00") & ":00"

-- Page 5: loss diagnosis over the whole closed-lost population
Closed Lost Leads =
CALCULATE(DISTINCTCOUNT(FactOutreach[lead_id]), FactOutreach[pipeline_status] = "Lost")

Loss Reason Share =
DIVIDE(
    [Closed Lost Leads],
    CALCULATE([Closed Lost Leads], ALLSELECTED(FactOutreach[lost_reason]))
)

-- Page 5: worst single step, used for the funnel annotation
Worst Stage Drop Off Pct =
MAXX(ALLSELECTED(DimFunnelStage), CALCULATE([Stage Drop Off Pct]))

-- Page 5: the action text comes from the model, never written per row
Next Action = SELECTEDVALUE(DimPrioritySegment[bd_action])
```

## Required formats

| Measure group | Format |
|---|---|
| Occupancy, conversion, coverage, stability | `0.0%` |
| Score | `0.0` plus `/ 100` in title/subtitle |
| Capacity/count/rank | `#,0` |
| INR values below crore | `INR #,0` |
| Executive INR cards | Display units `Lakhs` or `Millions`, one or two decimals |
| Rank change | `+0;-0;0` |

Validate every ratio at zero denominator and every selected-lot measure under no selection, one selection, and multiple selections.
