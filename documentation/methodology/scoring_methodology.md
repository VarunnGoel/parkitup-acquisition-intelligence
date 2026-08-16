# Scoring Methodology

## Business objective

Rank the controlled Delhi NCR candidate universe for BD prioritisation while keeping demand, economics, competitive whitespace, network value and closeability distinct. The result is a transparent relative decision aid, not a prediction model and not a claim about real PARK It Up operations.

## Inputs and provenance

`parking_acquisition_features` combines source public OSM location/POI fields, derived distances/counts, and explicitly synthetic operational performance, owner terms and hypothetical network sites. Competitor capacity is absent for all candidates, so the Competition pillar uses a **count-based supply-pressure proxy**. It does not invent competitor capacity.

## Normalisation

Continuous inputs use 5th/95th-percentile winsorisation followed by min-max scaling to 0-100. This prevents the largest synthetic facilities or revenue values from compressing all other lots. Scenario calculations retain baseline anchors so a uniform commission or cost shock changes absolute scores instead of disappearing through re-normalisation. Scores are relative to this 120-lot universe.

## Pillars

### Demand Potential (30%)

`0.50 * observed demand + 0.40 * location demand + 0.10 * demand headroom`

- Observed demand = `0.70 * average occupancy + 0.30 * 90th-percentile daily peak occupancy`.
- Location demand = metro accessibility (30%), bounded POI activity (35%), transit stops (15%), and micro-market prior (20%). Sparse OSM POI counts are treated as incomplete coverage, not proof of no activity.
- Headroom is the positive gap between location potential and utilisation evidence. It is deliberately small so a weakly utilised lot cannot rank on proxy data alone.

### Revenue Potential (25%)

`0.75 * expected monthly platform contribution + 0.25 * contribution per parking space`

Expected monthly contribution uses adjusted net platform bookings, average dwell duration, hourly tariff, the synthetic mean realisation factor of 0.76, synthetic per-lot commission, and 30 days. Sustainable utilisation is capped at 85% and only receives a small uplift from location headroom. Revenue per space prevents sheer capacity from deciding the pillar.

### Competition Opportunity (15%)

`0.55 * inverse count-based supply pressure + 0.20 * inverse aggregator penetration + 0.15 * competitor distance + 0.10 * tariff headroom`

Supply pressure is `ln(1 + competitor count within 1 km) / market demand prior`. It is a derived proxy because public competitor capacities are unavailable. Higher nearby competitor tariffs indicate possible headroom; missing tariffs are neutral rather than treated as favourable.

### Strategic Fit (15%)

`0.50 * network distance band + 0.35 * market whitespace + 0.15 * anchor capacity`

The network band penalises lots within 400 m of a live hypothetical site, rewards roughly 1.5-6 km spacing, and tapers after 6 km. Market whitespace equals locality location-demand strength times one minus local live-network-capacity coverage. It is conditional on the explicitly synthetic network baseline.

### Acquisition Feasibility (15%)

Willingness (20%), contract flexibility (14%), digital readiness (12%), documentation (15%), decision-maker access (12%), operational simplicity (8%), onboarding cost (7%), setup speed (4%), exclusivity (3%), capex need (2%), and owner-type friction (3%). It is kept separate in the attractiveness matrix and still contributes 15% to the final portfolio rank.

## Formula

`Acquisition Score = 0.30*Demand + 0.25*Revenue + 0.15*Competition + 0.15*Strategic Fit + 0.15*Feasibility`

The baseline weights remain the baseline business judgement. They were not tuned to synthetic outcomes. Demand-heavy, revenue-heavy, feasibility-heavy and balanced alternatives are tested rather than presented as proven truth.

## Correlation and double-counting audit

| Pair | Spearman correlation |
|---|---|
| Demand vs Revenue | 0.648 |
| Demand vs Strategic Fit | 0.483 |
| Demand vs Competition Opportunity | -0.243 |
| Capacity vs Revenue | 0.666 |
| Occupancy vs Revenue | 0.586 |
| Feasibility vs Willingness | 0.748 |
| Capacity vs Acquisition | 0.448 |

Demand and Revenue are moderately correlated because utilisation and bookings legitimately drive both, but they are not interchangeable: Demand blends location evidence and occupancy, while Revenue includes tariff, capacity, dwell, booking share and commission. Capacity has only a moderate relationship with the final Acquisition Score, so large facilities do not dominate automatically. Feasibility remains a separate owner/deal construct; its relationship with willingness is expected, while the feasibility-heavy scenario tests whether that pillar can materially change the ordering.

## Segmentation

Thresholds are calibrated from the base-case distribution rather than inherited from the schema layer placeholders:

- High attractiveness: 46.60 (67th percentile)
- Develop attractiveness floor: 32.87 (33rd percentile)
- Feasibility floor: 57.55 (median)

`ACQUIRE NOW` = high attractiveness and at-or-above-median feasibility. `PURSUE` = high attractiveness but lower feasibility. `DEVELOP` = mid-or-better attractiveness plus feasibility. Others are `AVOID`.

| segment_code | Lots |
|---|---|
| ACQUIRE_NOW | 25 |
| AVOID | 59 |
| DEVELOP | 21 |
| PURSUE | 15 |

## Explainability

`lot_dimension_score` stores each pillar, its actual weight and weighted contribution. `parking_score_explanation` stores positive and constraint flags; `parking_acquisition_score` joins them with the source feature layer. No score contains an encoded recommendation flag from the data pipeline.

## Sensitivity and rank stability

Ten primary scenarios feed rank stability: base, conservative/optimistic demand, lower/higher commission, higher cost, and the four alternative weight sets. A lot's rank stability is the share of these scenarios in which it stays in the top 10: 90-100% Very Stable, 70-89% Stable, 40-69% Sensitive, below 40% Highly Sensitive. Six supplementary checks cover dwell time, joint platform economics, and two hypothetical-network variants.

| scenario_code | top_10_overlap_pct | spearman_rank_correlation | mean_abs_rank_change | segment_change_count |
|---|---|---|---|---|
| BASE_CASE | 100.0 | 1.0 | 0.0 | 0 |
| CONSERVATIVE_DEMAND | 100.0 | 0.998 | 1.3 | 10 |
| OPTIMISTIC_DEMAND | 90.0 | 0.999 | 1.2 | 14 |
| LOWER_COMMISSION | 90.0 | 0.999 | 0.833 | 6 |
| HIGHER_COMMISSION | 90.0 | 1.0 | 0.5 | 7 |
| HIGH_ACQUISITION_COST | 100.0 | 1.0 | 0.133 | 5 |
| DEMAND_HEAVY | 100.0 | 0.991 | 3.55 | 8 |
| REVENUE_HEAVY | 90.0 | 0.982 | 4.767 | 8 |
| FEASIBILITY_HEAVY | 90.0 | 0.925 | 10.117 | 1 |
| BALANCED | 90.0 | 0.983 | 4.75 | 18 |
| LOWER_DWELL | 100.0 | 0.999 | 0.7 | 5 |
| HIGHER_DWELL | 90.0 | 1.0 | 0.367 | 6 |
| EXPANDED_NETWORK | 100.0 | 0.999 | 0.483 | 0 |
| MATURE_NETWORK | 90.0 | 0.994 | 2.217 | 4 |
| LOWER_PLATFORM_ECONOMICS | 90.0 | 0.992 | 2.6 | 16 |
| HIGHER_PLATFORM_ECONOMICS | 80.0 | 0.999 | 1.2 | 20 |

## Score distributions

| Score | min | 25% | 50% | mean | 75% | max |
|---|---|---|---|---|---|---|
| demand_score | 4.45 | 17.34 | 25.29 | 35.51 | 61.67 | 87.6 |
| revenue_score | 0.0 | 21.9 | 34.99 | 40.66 | 54.78 | 100.0 |
| competition_score | 17.59 | 31.82 | 49.82 | 49.83 | 60.26 | 95.5 |
| strategic_fit_score | 12.49 | 45.39 | 55.86 | 53.49 | 62.08 | 87.64 |
| feasibility_score | 14.78 | 43.42 | 57.55 | 56.05 | 66.42 | 95.53 |
| acquisition_score | 20.1 | 33.94 | 41.82 | 44.72 | 54.05 | 78.3 |

## Validation status

The engine ran 84 automated scoring checks; 0 failed.

Demand and Revenue exist twice by necessity: `parking_component_scores` defines
the baseline in SQL, and Python re-derives them because a scenario multiplier
cannot be expressed in that view. Every run therefore reconciles the base case
column by column against the SQL view, so a constant edited in only one of the
two files fails the build instead of quietly producing two different models.

Largest absolute base-case difference across 120 lots and 13 measures: `1.16e-10` (tolerance `1e-06`).

| column | compared | max_abs_diff | status |
|---|---|---|---|
| demand_score | 120 | 0.0 | PASS |
| revenue_score | 120 | 0.0 | PASS |
| competition_score | 120 | 0.0 | PASS |
| strategic_fit_score | 120 | 0.0 | PASS |
| feasibility_score | 120 | 0.0 | PASS |
| observed_demand_score | 120 | 0.0 | PASS |
| location_demand_score | 120 | 0.0 | PASS |
| achievable_utilization | 120 | 0.0 | PASS |
| expected_monthly_platform_revenue_inr | 120 | 1.16e-10 | PASS |
| expected_revenue_per_space_inr | 120 | 0.0 | PASS |
| network_distance_score | 120 | 0.0 | PASS |
| onboarding_cost_score | 120 | 0.0 | PASS |
| market_whitespace_score | 120 | 0.0 | PASS |

| test_id | test_name | records_tested | observed_metric | status |
|---|---|---|---|---|
| FT-01 | Large capacity, extremely low occupancy | 6 | 42.0 | PASS |
| FT-02 | Very high price, weak demand | 5 | 42.0 | PASS |
| FT-03 | High demand, extreme competition | 14 | 5.47 | PASS |
| FT-04 | High demand, poor acquisition feasibility | 4 | 0.0 | PASS |
| FT-05 | Small capacity, exceptionally strong demand | 3 | 6.0 | PASS |
| FT-06 | Moderate lot in a network gap | 10 | 21.82 | PASS |

## Limitations

- Performance, commercial terms, owner posture, outreach and the network baseline are synthetic.
- The OSM POI extract is bounded and sparse; zero counts do not prove zero local activity.
- Competitor capacity is unavailable, so competition uses a transparent count-density proxy.
- Haversine distances ignore walking barriers and actual road routing.
- Two-wheelers are out of scope.
- Scores are relative to this synthetic 120-lot study universe and have no predictive validation against acquisition outcomes.
- This is a weighted decision framework, not an ML model. It has no target variable or learned coefficients; its value is inspectability and sensitivity testing.
