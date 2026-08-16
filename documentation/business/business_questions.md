# Business Questions

**Project:** PARK It Up Acquisition Intelligence

> **How to read this document.** This is the original specification, written
> before any analysis existed, and it is kept in that form deliberately — fixing
> the question set first is the point being demonstrated. The **`Artefact.`,
> `Tables.` and `Logic.` lines in each question below are the original plan, not
> a description of the code.** The work was consolidated into fewer, differently
> named files than one-per-question, and the schema evolved. The
> [implementation map](#implementation-map) immediately below is the accurate
> record of where each question is actually answered. Where the map says
> NOT IMPLEMENTED, it means exactly that.

---

## Implementation map

Verified by reading each artefact, not by matching filenames. Paths are relative
to the repository root.

| Q | Question | Answered by | Status |
|---|---|---|---|
| Q1 | Strongest locality opportunity | `vw_locality_summary` in `database/views/01_analytics_views.sql`, surfaced by `sql/market_analysis/locality_and_network.sql` | Implemented; uses a plain mean, not the capacity-weighted mean specified, and does not report spread |
| Q2 | Demand high, supply weak | `vw_locality_summary` — inputs only | **Not answerable.** Competitor capacity is null for every candidate in OSM, so no supply-versus-demand ratio can be computed. Nothing is imputed. See `future_improvements.md` |
| Q3 | Underpenetrated markets | `vw_locality_summary` (`parkitup_coverage_pct`, `market_whitespace_score`, `whitespace_rank`) | Implemented for platform coverage; the aggregator-penetration half stays at lot grain |
| Q4 | Which lots to prioritise | `sql/acquisition/acquisition_ranking.sql` over `vw_bd_acquisition_targets` | Implemented; the SELECT shows expected revenue in place of `revenue_score`, so the pillar breakdown is 4 of 5 |
| Q5 | Highest revenue potential | `sql/revenue/revenue_analysis.sql` | Partial. Ranks by observed `avg_daily_revenue_inr`, not by the `revenue_score` pillar; commission is not reported alongside |
| Q6 | High demand, weak competition | `sql/competition/competition_analysis.sql`; `competition_quadrants()` in `python/analysis/eda.py` | Implemented; uses `competitor_count_1km` rather than the 500 m count specified |
| Q7 | Does capacity correlate with opportunity | `write_methodology()` in `python/analysis/scoring_engine.py`, rendered into `documentation/methodology/scoring_methodology.md` | Implemented. Capacity vs Revenue 0.666, Capacity vs Acquisition 0.436 — the answer is "moderately, and not enough to dominate" |
| Q8 | Highest expected platform contribution | Computed in `sql/analysis/component_scores.sql`, ranked at locality grain in `sql/revenue/revenue_analysis.sql` | Implemented at locality grain; exposed but not ranked at lot grain |
| Q9 | Sensitivity to occupancy assumptions | `python/model_validation/sensitivity.py`; `sql/sensitivity/rank_robustness.sql` | Implemented as one module rather than the two specified. Multipliers are ±15%, not the ±25% specified |
| Q10 | Sensitivity to commission assumptions | `python/model_validation/sensitivity.py` | Implemented, including both the proportional shock and the uniform-rate flattening test |
| Q11 | Which operators are easiest to acquire | — | **NOT IMPLEMENTED.** No artefact aggregates feasibility and capacity to owner grain. `DimOwner` exists so the grain is reachable in Power BI. Recorded in `future_improvements.md` |
| Q12 | Where the funnel loses prospects | `vw_bd_funnel`, surfaced by `sql/bd_funnel/bd_funnel_analysis.sql` | Stage drop-off implemented. The specified loss-reason × stage cross-tab is **not** built; loss reasons appear only as an ungrouped total |
| Q13 | Lead characteristics vs success | `sql/bd_funnel/bd_funnel_analysis.sql`; `bd_conversion_breakdowns()` in `python/analysis/eda.py` | Implemented across five dimensions; uses `digital_payment_enabled` rather than the willingness band specified |
| Q14 | Which markets to enter next | `sql/market_analysis/locality_and_network.sql`; `classify_markets()` in `python/analysis/eda.py` | Implemented |
| Q15 | Which lots to acquire immediately | `vw_bd_acquisition_targets`; `bd_acquisition_targets` in `database/schema/06_analysis.sql` | Implemented. Sorts Acquire Now first rather than filtering to it, and the BD action is a hard-coded `CASE` rather than a join to `segment_rule.bd_action` |
| Q16 | Attractive lots that should be avoided | — | **NOT IMPLEMENTED.** No naive-proxy ranking is computed anywhere, so the model-versus-heuristic divergence cannot be shown. This is the more valuable of the two gaps — see `future_improvements.md` |

### Analysis that exists but is not in this list

Substantial working analysis has no numbered question here: price-band and
dominant-type market structure, peak-hour identification, utilisation-efficiency
segmentation, peer benchmarking and rank explanation (`vw_parking_benchmarks`,
`vw_parking_rank_explanation`), network strategy classification, per-locality
top-three alternatives, multivariate outlier review, and the entire
model-validation layer — 7 monotonicity tests, 6 adversarial stress cases and 16
scenarios. The scenario breadth in particular goes well beyond Q9 and Q10: weight
sensitivity, arguably the most important robustness test for a weighted model, has
no numbered question at all.

That is a gap in this document rather than in the work. `documentation/sql/business_question_catalog.md`
is the accurate catalogue of what the SQL layer actually delivers.

---

## Why the question set is fixed first

The failure mode of an analytics project is not producing wrong answers. It is producing correct answers to questions nobody asked. A dataset of this shape supports hundreds of queries, and without a fixed brief the analysis drifts toward whatever is easiest to compute — occupancy by month, revenue by parking type, counts by locality — none of which changes a decision.

This document is therefore a constraint on the analysis that follows, not a wish list. Every SQL file written in the SQL analytics layer must map to a numbered question here, and every dashboard visual built in the validation layer must answer one. If a query does not trace back to this list, it either belongs in exploratory work that never reaches the deliverable, or it reveals a question that should be added here explicitly and argued for.

The sixteen questions are grouped by the decision they inform and by who makes it. Market questions belong to a founder or city head deciding where to expand. Parking-lot and economics questions belong to whoever builds the target list. BD questions belong to the team lead allocating rep time. Strategy questions are the synthesis, and they are the ones that get asked in an interview.

A note on what "answering" means here. Several of these questions have honest answers that are unflattering to the model — question 7 may return no relationship, and questions 9 and 10 may show the recommendations are fragile. Those outcomes are findings and must be reported as such. An analysis that only ever confirms its own framework is not an analysis.

---

## Market

These four are answered at locality grain and drive expansion sequencing rather than individual deals.

### Q1 — Which localities have the strongest parking opportunity?

**Restated.** Ranking each locality by the mean attractiveness of the parking lots within it, weighted by capacity so a locality with one excellent large lot is not outranked by one with three small mediocre lots. Localities with fewer than three modelled lots are reported separately as insufficient evidence rather than ranked alongside the rest.

**Why it matters.** A city head allocating the next quarter's BD attention needs a ranked shortlist of neighbourhoods, not a list of 120 individual sites.

**Grain.** Locality.

**Tables.** `dim_locality`, `dim_city`, `parking_lots`, `lot_score`.

**Logic.** Capacity-weighted mean of `lot_score.attractiveness_score` grouped by `locality_id`, with a lot count and the spread reported beside the mean. The spread matters: a locality where every lot scores 60 is a different proposition from one averaging 60 across a 90 and a 30.

**Artefact.** `sql/business_questions/q01_locality_opportunity_ranking.sql` → Page 2, Market Opportunity.


### Q2 — Where is demand high but parking supply relatively weak?

**Restated.** Identifying localities where the aggregate demand signal is in the upper range while competing parking capacity per unit of demand is in the lower range. This is a supply-demand imbalance measure, not a comparison of raw counts.

**Why it matters.** These are the localities where a new listing captures genuinely incremental bookings rather than displacing existing ones. It is the strongest argument a BD rep can take to an operator.

**Grain.** Locality.

**Tables.** `dim_locality`, `parking_lots`, `location_demand`, `competition`, `lot_dimension_score`.

**Logic.** Compare the locality mean of the `DEMAND` subscore against `competition.competitor_total_capacity_1km` normalised by that demand. Flag localities in the high-demand, low-supply-ratio corner. Because the same lots contribute to both sides, the calculation must avoid double-counting a lot as its own competitor.

**Artefact.** `sql/business_questions/q02_demand_supply_gap.sql` → Page 2, Market Opportunity.


### Q3 — Which markets are currently underpenetrated?

**Restated.** Which localities have meaningful parking demand but little or no presence from either the hypothetical PARK It Up network or rival aggregators. Underpenetration means low *platform* coverage, which is distinct from Q2's low *physical* supply.

**Why it matters.** Distinguishes a market nobody has digitised from one a competitor already owns. The first is an opportunity; the second is a fight.

**Grain.** Locality.

**Tables.** `dim_locality`, `parking_lots`, `existing_network_sites`, `competition`, `lot_dimension_score`.

**Logic.** Count `existing_network_sites` with `site_status = 'Live'` per locality, alongside the locality sum of `competition.aggregator_listed_count_1km`, against mean demand. Both counts near zero with high demand indicates a white space.

**Artefact.** `sql/business_questions/q03_market_penetration.sql` → Page 2, Market Opportunity.


---

## Parking lot

The core target-list questions, answered per lot.

### Q4 — Which parking lots should PARK It Up prioritise?

**Restated.** The ranked list of lots by `acquisition_score` under the default weight set, with each lot's segment and the pillar breakdown that produced its score.

**Why it matters.** This is the project's primary output. Everything else supports or qualifies it.

**Grain.** Lot.

**Tables.** `lot_score`, `lot_dimension_score`, `parking_lots`, `dim_locality`, `owners`, `segment_rule`.

**Logic.** Order by `acquisition_score` descending, filtered to the weight set flagged `is_default`, joined to `lot_dimension_score` so the five contributions are visible beside the total.

**Artefact.** `sql/business_questions/q04_acquisition_priority_ranking.sql` → Page 1, Executive Overview.


### Q5 — Which parking lots have the highest revenue potential?

**Restated.** Ranking by the `REVENUE` subscore alone, ignoring the other four pillars, so revenue-attractive lots that the composite ranks lower become visible.

**Why it matters.** Revenue potential alone is not a reason to acquire — but a lot that ranks high here and low overall is worth understanding, because the reason it fell is usually a single fixable obstacle.

**Grain.** Lot.

**Tables.** `lot_dimension_score`, `parking_lots`, `fact_lot_daily`, `lot_acquisition_terms`.

**Logic.** Filter `lot_dimension_score` to `dimension_code = 'REVENUE'` and order by `subscore`, reporting the underlying capacity, tariff, utilisation and commission rate so the score is interpretable.

**Artefact.** `sql/business_questions/q05_revenue_potential_ranking.sql` → Page 1, Executive Overview.


### Q6 — Which lots have high demand but weak competition?

**Restated.** The lot-level version of Q2: lots whose `DEMAND` subscore is high and whose `COMPETITION` subscore is also high, since the competition pillar is constructed so that a high score means favourable conditions rather than heavy rivalry.

**Why it matters.** These lots have the cleanest commercial story and the least risk of a price war shortly after launch.

**Grain.** Lot.

**Tables.** `lot_dimension_score`, `competition`, `location_demand`, `parking_lots`.

**Logic.** Pivot `lot_dimension_score` to compare the two subscores per lot, selecting lots in the upper range on both, with `competitor_count_500m` and `nearest_competitor_distance_m` shown as corroboration.

**Artefact.** `sql/business_questions/q06_high_demand_low_competition.sql` → Page 3, Acquisition Matrix.


### Q7 — Does capacity actually correlate with opportunity?

**Restated.** Testing whether `parking_lots.capacity_cars` has any consistent relationship with `lot_score.acquisition_score`, and separately with the `REVENUE` subscore, across the modelled population.

**Why it matters.** BD intuition says bigger lots are better prospects. If the model disagrees, that is a genuinely useful correction — a rep chasing the largest facility in a locality may be spending effort on the least incremental opportunity.

**Grain.** Lot, reported as a single relationship.

**Tables.** `parking_lots`, `lot_score`, `lot_dimension_score`.

**Logic.** Correlation between capacity and score, plus a comparison of mean scores across capacity bands. A scatter plot with the fitted relationship is more informative than a single coefficient.

**Artefact.** `sql/business_questions/q07_capacity_opportunity_correlation.sql` → Page 3, Acquisition Matrix.


**Handle with care.** This is a real hypothesis test, and it can fail. Capacity feeds the Revenue pillar directly, so some positive relationship there is close to guaranteed and is not evidence of anything — it is arithmetic. The interesting test is against the *composite* score, where capacity competes with demand, competition and feasibility. **A weak or absent correlation is a legitimate finding and must be reported plainly, not buried or explained away.** The correct write-up if that happens is that capacity is a poor standalone screening criterion, which is a more valuable conclusion than confirming the intuition would have been.

---

## Economics

### Q8 — Which parking lots have the highest expected platform contribution?

**Restated.** Ranking by modelled monthly platform contribution in rupees, distinct from the normalised Revenue subscore — this is the unnormalised economic estimate.

**Why it matters.** Score ranking answers "which first"; contribution answers "how much is this worth". A founder needs the second to judge whether the whole expansion is worth the BD headcount.

**Grain.** Lot.

**Tables.** `fact_lot_daily`, `lot_acquisition_terms`, `parking_lots`.

**Logic.** Approximately `gross_parking_revenue_inr` × platform booking share × `expected_commission_pct`, aggregated to a monthly figure. Every input is synthetic, so the output is valid for *ordering* lots and invalid as a forecast.

**Artefact.** `sql/business_questions/q08_expected_platform_contribution.sql` → Page 1, Executive Overview.


**Caveat that must travel with the answer.** Because assumptions A-07 and A-08 are both synthetic and multiplicative, the absolute rupee figure carries no evidential weight. Charts must be labelled as modelled contribution, and the number must never appear in a sentence that implies it is a projection.

### Q9 — How sensitive are recommendations to occupancy assumptions?

**Restated.** How much the ranking and segment assignment change when the occupancy and dwell-time assumptions (A-05, A-06, A-09) are varied around their baseline values.

**Why it matters.** Occupancy drives both Demand and Revenue, so it influences 55% of the baseline score. If the recommendation is unstable to it, that must be disclosed before anyone acts on the ranking.

**Grain.** Lot, compared across scenarios.

**Tables.** `lot_score`, `lot_dimension_score`, `scoring_weight_set`, `fact_lot_daily`.

**Logic.** Re-run the scoring with occupancy and duration scaled to roughly 0.75× and 1.25×, writing results under separate weight set identifiers, then measure rank correlation and top-20 overlap against the baseline.

**Artefact.** `sql/business_questions/q09_occupancy_sensitivity.sql` plus `python/analysis/sensitivity_occupancy.py` → Page 1, Executive Overview.


**Not a single query.** This requires re-running the scoring engine with modified inputs and storing multiple result sets. The SQL file compares outcomes; it does not produce them.

### Q10 — How sensitive are recommendations to commission assumptions?

**Restated.** How much the ranking changes when commission (A-08) and platform booking share (A-07) are varied — both scaled proportionally, and flattened to a single uniform rate across all lots.

**Why it matters.** Commission is the most negotiable term in a real deal. Knowing that the top ten holds even if commission lands three points lower makes a BD lead far more confident conceding it.

**Grain.** Lot, compared across scenarios.

**Tables.** `lot_acquisition_terms`, `lot_score`, `lot_dimension_score`.

**Logic.** Two distinct tests. Scaling every lot's rate shows sensitivity to the overall level. Flattening all lots to one rate is more revealing, because it isolates how much of the ranking is driven by commission *variation* rather than by demand. Because A-07 and A-08 multiply, a joint grid exposes compounding that separate tests miss.

**Artefact.** `sql/business_questions/q10_commission_sensitivity.sql` plus `python/analysis/sensitivity_commission.py` → Page 1, Executive Overview.


---

## Business development

### Q11 — Which parking operators appear easiest to acquire?

**Restated.** Ranking by `feasibility_score` at operator grain rather than lot grain, so an operator controlling several lots is assessed once, with the combined capacity a single negotiation would unlock.

**Why it matters.** Operator-level thinking changes sequencing. One conversation that unlocks four lots outranks four conversations that unlock one each, even when the individual lots score lower.

**Grain.** Owner.

**Tables.** `owners`, `parking_lots`, `lot_score`, `lot_acquisition_terms`.

**Logic.** Aggregate `feasibility_score` and total `capacity_cars` by `owner_id`, with `willingness_to_digitize`, `contract_flexibility` and `decision_maker_accessible` shown as the drivers. Report the count of lots per owner prominently.

**Artefact.** `sql/business_questions/q11_owner_acquisition_ease.sql` → Page 5, BD Strategy.


### Q12 — Where does the BD funnel lose the most prospects?

**Restated.** The stage-to-stage conversion rate across the seven funnel stages, and the distribution of loss reasons at each stage.

**Why it matters.** It tells the BD lead whether the problem is reach, pitch or close. Each implies a completely different intervention, and the cost of guessing wrong is a quarter of misdirected effort.

**Grain.** Funnel stage.

**Tables.** `outreach`, `outreach_events`, `dim_funnel_stage`.

**Logic.** Count distinct leads reaching each `stage_id` in `outreach_events`, ordered by `stage_order`, with each stage's count as a proportion of the previous. Cross-tabulate `lost_reason` against `furthest_stage_id` to see where each failure mode concentrates.

**Artefact.** `sql/business_questions/q12_funnel_dropoff.sql` → Page 5, BD Strategy.


### Q13 — Which lead characteristics are associated with successful acquisition?

**Restated.** Which attributes of a lead — source, channel, owner type, willingness, documentation readiness, contact intensity — differ between leads that converted and leads that were lost.

**Why it matters.** It sharpens qualification. If referrals convert at several times the rate of cold calls, the sourcing mix should change.

**Grain.** Lead, reported as attribute comparisons.

**Tables.** `outreach`, `outreach_events`, `owners`, `lot_acquisition_terms`.

**Logic.** Conversion rate by `lead_source`, by `owners.owner_type`, by `willingness_to_digitize` band, and by whether `decision_maker_accessible` is true. Also mean `days_to_conversion` by source. Association only — no causal claim is available from this data.

**Artefact.** `sql/business_questions/q13_conversion_drivers.sql` → Page 5, BD Strategy.


**Circularity warning.** the data pipeline generates loss reasons correlated with owner attributes (assumption A-22). If the SQL analytics layer then reports that owner attributes predict conversion, that is the data generator being read back, not a discovery. **This question must be framed as a demonstration of the analytical approach — "here is how I would test this on real pipeline data" — not as a finding about operator behaviour.**

---

## Strategy

The synthesis questions. Each depends on several of the above.

### Q14 — Which markets should PARK It Up enter next?

**Restated.** A recommended sequence of localities for expansion, combining opportunity from Q1, the supply gap from Q2, penetration from Q3, and the presence of at least a few feasible targets — a locality with no acquirable lots is not a market, however attractive.

**Why it matters.** Converts locality analysis into a plan with an order and a rationale.

**Grain.** Locality, ranked.

**Tables.** `dim_locality`, `dim_city`, `parking_lots`, `lot_score`, `existing_network_sites`.

**Logic.** Combine the locality-level outputs of Q1 to Q3 with a count of lots in `ACQUIRE_NOW` or `PURSUE`, then sequence. The feasibility filter is what makes this a plan rather than a wish list.

**Artefact.** `sql/business_questions/q14_market_entry_sequence.sql` → Page 2, Market Opportunity.


### Q15 — Which parking lots should be acquired immediately?

**Restated.** The `ACQUIRE_NOW` segment, ordered by `acquisition_score`, with the specific BD action from `segment_rule` and the pillar breakdown attached to each lot.

**Why it matters.** This is the call list. It is what a BD rep opens on Monday morning, and its usefulness depends entirely on being short and specific.

**Grain.** Lot.

**Tables.** `lot_score`, `segment_rule`, `lot_dimension_score`, `parking_lots`, `owners`, `lot_acquisition_terms`.

**Logic.** Filter to `segment_code = 'ACQUIRE_NOW'` under the default weight set, joined to owner contact posture and deal terms so the rep has context before dialling.

**Artefact.** `sql/business_questions/q15_acquire_now_list.sql` → Page 1, Executive Overview, drilling through to Page 4.


**Depends on calibration.** The segment boundaries are provisional (assumption A-14). Until the scoring engine re-derives them from the observed score distribution, the membership of this list is not stable, and the honest presentation says so.

### Q16 — Which apparently attractive parking lots should actually be avoided?

**Restated.** Lots that a naive screen would rank highly — large capacity, high revenue, prime location — but which the model places in `AVOID` or low in the ranking, together with the specific pillar that pulled them down.

**Why it matters.** This is where the model earns its existence. Anyone can rank by size. A framework that only confirms the obvious adds nothing; one that identifies expensive mistakes before they are made pays for itself.

**Grain.** Lot.

**Tables.** `lot_score`, `lot_dimension_score`, `parking_lots`, `competition`, `owners`, `lot_acquisition_terms`.

**Logic.** Rank lots by a naive proxy — capacity, or capacity × tariff — then compare against the model rank. Surface the largest negative divergences and attribute each to its weakest pillar: saturated competition, an immovable owner, cannibalisation of an existing site, or thin genuine demand behind a good address.

**Artefact.** `sql/business_questions/q16_attractive_but_avoid.sql` → Page 3, Acquisition Matrix, drilling through to Page 4.


**The most interview-valuable question in the set.** It requires the model to disagree with intuition and then justify the disagreement, which is exactly the conversation worth having. Each identified lot needs a one-sentence explanation traceable to `lot_dimension_score`, because "the model said so" is not an answer. Note also that this question can expose a defective model rather than a defective intuition — if the divergent lots look wrong on inspection, the finding is that the framework needs fixing, and reporting that is more valuable than hiding it.

---

## Questions we are deliberately not answering

Three categories are out of scope, and saying so protects the project from being judged against a brief it never accepted.

**Individual customer and driver behaviour.** There is no customer, user or booking-level data anywhere in the model, and there will not be (assumption A-24). The finest grain is a lot-day. Questions about repeat usage, driver segments, session-level behaviour or booking funnels cannot be answered and must not be attempted with aggregate data dressed up as individual behaviour.

**Price elasticity and optimal pricing.** Establishing how demand responds to tariff changes requires either observed price variation with controls, or a genuine experiment. The model holds tariffs static across the observation window (assumption A-21), so any elasticity computed from it would be an artefact of the generator. Recommending a price would be actively irresponsible.

**Precise revenue forecasting in rupees.** The revenue chain rests on synthetic dwell time, synthetic booking share and synthetic commission, all multiplicative. Relative ranking survives this, because errors that apply similarly across lots largely cancel when comparing them. Point forecasts do not survive it at all. The project therefore reports *modelled contribution* for ordering purposes and refuses to state an expected revenue figure — which is a limitation to state proudly rather than apologise for, since the alternative is a number that looks authoritative and means nothing.
