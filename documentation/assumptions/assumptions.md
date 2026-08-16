# Assumptions Register

**Project:** PARK It Up Acquisition Intelligence
**Status:** source — data-generation assumptions executed; scoring assumptions remain provisional
**Last updated:** source

---

## Purpose

Every analytical model rests on assumptions. The difference between a model that survives scrutiny and one that collapses under it is usually not the sophistication of the method but whether the analyst knew which assumptions were load-bearing and said so before being asked.

This register exists to be read adversarially. It records every judgement made in the absence of hard evidence, states the value chosen, classifies where that value came from, and commits to how it will be tested. An interviewer who wants to break this project will attack the assumptions, and the correct response is to hand them this document rather than improvise.

Two rules govern everything here. First, no assumption in this register is presented as fact anywhere in the project. Where a number is invented, the documentation says so. Second, the assumptions that most affect the final recommendation are flagged for explicit sensitivity testing in the scoring engine — because an assumption that changes the answer matters far more than one that merely changes a decimal place.

## How to read the source classification

**Public** means the value is verifiable from an external source such as OpenStreetMap, published metro network data, or municipal records. **Derived** means it is computed from other values in the model rather than asserted. **Synthetic** means it was invented to make the model runnable, and carries no evidential weight whatsoever. A synthetic assumption is not a lie as long as it is labelled; it becomes a lie the moment a result derived from it is presented as a finding about the real world.

## Sensitivity priority

**High** means the recommendation ranking is expected to move materially if this assumption is wrong — the scoring engine must test it. **Medium** means it affects magnitudes but probably not the ordering. **Low** means it is a modelling convenience with little downstream consequence.

---

## Summary

| ID | Assumption | Source | Sensitivity |
|----|-----------|--------|-------------|
| A-01 | Study area is Delhi NCR, bounded by lat 28.30–28.95, lon 76.80–77.60 | Public | Low |
| A-02 | Observation window is 2025-08-01 to 2026-07-31 (365 days) | Synthetic | Medium |
| A-03 | Modelled universe is 120 parking lots across 17 final markets | Config / Derived | Low |
| A-04 | Four-wheelers only; two-wheeler demand is out of scope | Synthetic | Medium |
| A-05 | Average parking duration is 2–3 hours, varying by land use | Synthetic | **High** |
| A-06 | Occupancy varies systematically by micro-market type | Synthetic | **High** |
| A-07 | Platform-originated bookings are approximately 4–34% of total entries | Synthetic | **High** |
| A-08 | Platform commission is approximately 7.5–25% of platform-booked revenue | Synthetic | **High** |
| A-09 | Revenue potential uses sustainable rather than peak utilisation | Derived | **High** |
| A-10 | Competition is measured at 500 m and 1 km radii | Synthetic | Medium |
| A-11 | Footfall is proxied from POI density, not observed | Derived | **High** |
| A-12 | Straight-line distance proxies walking distance | Synthetic | Medium |
| A-13 | The existing PARK It Up network is hypothetical | Synthetic | Medium |
| A-14 | Segment thresholds calibrated from the observed distribution | Derived | Resolved |
| A-15 | Baseline pillar weights are business judgement, not evidence | Synthetic | **High** |
| A-16 | Sub-scores are min-max normalised within the study area | Derived | Medium |
| A-17 | Owner willingness and flexibility are 1–5 ordinals | Synthetic | Medium |
| A-18 | Onboarding cost is ₹33,000–₹270,000 in the generated population | Synthetic | Medium |
| A-19 | The holiday calendar is incomplete by design | Public | Low |
| A-20 | Recorded revenue is the operator's gross, not platform income | Synthetic | Medium |
| A-21 | Tariffs are static across the observation window | Synthetic | Low |
| A-22 | BD funnel conversion decays at each stage | Synthetic | Medium |
| A-23 | Each parking lot has at most one BD lead record | Synthetic | Low |
| A-24 | No driver- or customer-level data exists | Structural | Low |
| A-25 | Nominatim fallback POI counts are minimum observed coverage, not exhaustive census counts | Public / Derived | **High** |

---

## A-01 — Study area

**Assumption.** The analysis covers Delhi NCR only: New Delhi, Gurugram, Noida, Ghaziabad and Faridabad, bounded by latitude 28.30–28.95 and longitude 76.80–77.60.

**Why it is needed.** Strategic Fit and Competition are both relative measures. "Distance from the existing network" and "competitor density" only mean something inside a defined market boundary. Without a fixed study area, min-max normalisation would shift every time a lot was added.

**Value.** The bounding box above, enforced as a `CHECK` constraint on `parking_lots.latitude` and `parking_lots.longitude` and asserted against `python/config.py` by `tests/test_config_schema_agreement.py`.

**Source.** Public. The box is a deliberately generous rectangle around the NCR core; it includes some territory outside the five cities, which is acceptable for a guard rail whose job is to catch transposed or truncated coordinates rather than to define policy.

**Validation.** No sensitivity testing needed. The test suite already prevents the bounding box from drifting apart from the schema.

---

## A-02 — Observation window

**Assumption.** Simulated performance covers 2025-08-01 to 2026-07-31, a full 365 days.

**Why it is needed.** Occupancy and revenue feed the Demand and Revenue pillars, so the period observed determines what those pillars see. A window that excluded the festive season would systematically understate retail-adjacent lots.

**Value.** 365 days, seeded into `dim_date` by `database/seeds/02_seed_calendar.sql`. A full year was chosen over six months specifically to capture three NCR effects that would otherwise be invisible: the monsoon from July to September, the October–November festive retail peak, and the winter smog and GRAP restriction period, which affects vehicle movement in Delhi in a way it does not elsewhere in India.

**Source.** Synthetic. The window is a modelling choice; the seasonality within it is generated, not measured.

**Validation.** the scoring engine should confirm that pillar scores computed on the first six months and the second six months produce a similar ranking. If they do not, the window is doing more work than it should and the model is picking up seasonal noise rather than structural demand.

---

## A-03 — Size of the modelled universe

**Assumption.** 120 parking lots across 17 final micro-markets.

**Why it is needed.** The number has to be large enough that locality-level aggregation is meaningful — a locality with two lots supports no conclusion — and small enough that the entire dataset can be hand-inspected when a result looks wrong.

**Value.** 120, set by `TARGET_LOT_COUNT` in `.env.example`, across the 17 markets that yielded at least three public candidates. At this size `fact_lot_daily` holds 43,800 rows.

**Source.** Config for the target size; derived from public-source coverage for the final market count.

**Validation.** None required. the data pipeline should report the achieved counts and the split by `record_source`, since the ratio of public to synthetic lots is itself a credibility statement.

---

## A-04 — Vehicle class

**Assumption.** Only four-wheeler parking is modelled. Two-wheeler capacity, pricing and demand are excluded.

**Why it is needed.** Indian parking facilities routinely serve both, at different tariffs, different dwell times and different bay footprints. Modelling both would require two capacity columns, two rate columns, two occupancy series and a bay-equivalence factor.

**Value.** Single vehicle class, enforced by naming the column `capacity_cars` rather than `capacity`, so the scope limit is visible at the point of use.

**Source.** Synthetic scoping decision.

**Validation.** This assumption understates total demand at lots where two-wheelers dominate, which in NCR skews toward retail high streets and hospitals. the scoring engine must state this limitation when reporting Revenue Potential rather than leaving it in this register. It is not sensitivity-testable within the current model — correcting it requires a schema change, and that is the honest answer to give if asked.

---

## A-05 — Average parking duration

**Assumption.** Mean dwell time is 2–3 hours, varying by surrounding land use: office parks longer, retail and restaurants shorter, hospitals longer and more variable.

**Why it is needed.** Revenue is a function of duration. Two lots with identical entries and identical tariffs produce very different revenue if one turns over every 45 minutes and the other holds vehicles all day.

**Value.** Generated per lot within 0.5–8.0 hours, centred on the land-use-appropriate mean. Constrained in the schema to `> 0 AND <= 24`.

**Source.** Synthetic.

**Validation.** **High priority.** Duration multiplies directly into revenue, so it multiplies directly into the Revenue pillar and therefore into 25% of the baseline score. the scoring engine must re-run the scoring with duration scaled to 0.75× and 1.25× and report whether the top 20 ranking changes. If the ranking is stable, say so; if it is not, the Revenue pillar's weight is not defensible at 25%.

---

## A-06 — Occupancy by micro-market type

**Assumption.** Peak occupancy varies systematically with `dim_locality.micro_market_type` — CBD and transit hubs run high on weekdays, retail high streets peak at weekends, hospitals stay high throughout, residential areas invert.

**Why it is needed.** Occupancy that was random across lots would make the Demand pillar meaningless: the model would be scoring noise. Occupancy must correlate with observable location characteristics for the scoring framework to have any construct validity.

**Value.** Peak occupancy generated in the 0.35–0.98 band, with the mean set by micro-market type and day type.

**Source.** Synthetic, but structured to be *plausible* rather than arbitrary. This is the single most important synthetic-data design decision in the project: the whole analytical premise is that location characteristics predict demand, so if the generator does not encode that relationship, the scoring engine will discover a relationship that was planted rather than found.

**Validation.** **High priority, and requires unusual care.** There is a circularity risk here that must be stated openly. If the data pipeline generates occupancy *from* POI counts and the scoring engine then reports that POI counts predict occupancy, that is not a finding — it is the generator being read back. the scoring engine must therefore either add substantial independent noise so the relationship is recoverable but not deterministic, or present the demand analysis explicitly as a demonstration of method rather than a discovery. The second is more honest and should be preferred.

---

## A-07 — Platform booking share

**Assumption.** Approximately 4% to 34% of vehicle entries at a digitised lot come through the platform, higher where the owner is digitally mature and the location attracts planned rather than incidental parking.

**Why it is needed.** Platform contribution is earned on platform-originated bookings only, not on the operator's total revenue. Without this share, every lot's value to the platform would be overstated by roughly a factor of four.

**Value.** 4–34%, correlated with digital payment, willingness to digitize, location demand and an adoption trend through the observation window.

**Source.** Synthetic.

**Validation.** **High priority.** Along with commission (A-08), this determines the entire economics of the Revenue pillar. the scoring engine must test 0.5× and 1.5× multipliers. Note that A-07 and A-08 are multiplicative, so their errors compound — a joint sensitivity grid is more informative than testing each alone.

---

## A-08 — Platform commission rate

**Assumption.** Commission is approximately 7.5–25% of the value of platform-originated bookings, varying by owner negotiating posture.

**Why it is needed.** It converts gross parking revenue into platform contribution, which is the quantity the business actually cares about.

**Value.** Stored per lot in `lot_acquisition_terms.expected_commission_pct`, constrained to 0–40 to leave room for outliers without permitting nonsense.

**Source.** Synthetic. This is emphatically **not** a PARK It Up commercial term. Real commission structures are confidential and are not used, referenced or inferred anywhere in this project.

**Validation.** **High priority**, and directly answerable as business question 10. Because commission is stored per lot rather than as a global constant, sensitivity testing can be done two ways: scale every lot's rate, or flatten all lots to a single rate. The second is more revealing, because it isolates how much of the ranking is driven by commission variation rather than by demand.

---

## A-09 — Utilisation basis for revenue potential

**Assumption.** Revenue Potential is computed from sustainable achievable utilisation, not from observed peak occupancy.

**Why it is needed.** Scoring on peak would reward lots that are already saturated, which is backwards. A lot running at 95% peak has little headroom for the platform to add incremental bookings; a lot at 55% with strong surrounding demand has a great deal.

**Value.** To be defined precisely in the scoring engine. The intended treatment is that Revenue Potential uses average rather than peak occupancy, and that headroom — the gap between current and achievable utilisation — enters the Demand pillar as an opportunity signal rather than the Revenue pillar as a volume signal.

**Source.** Derived.

**Validation.** **High priority.** This is a genuine modelling fork and the scoring engine must implement it deliberately and document which of the two it chose. Getting it backwards would invert the recommendation for exactly the lots the BD team most wants to hear about.

---

## A-10 — Competitor detection radii

**Assumption.** Competing supply is counted within 500 m and within 1 km of each lot.

**Why it is needed.** Competition has no meaning without a radius. The choice encodes an implicit claim about how far a driver will divert for cheaper or more convenient parking.

**Value.** 500 m as the primary competitive radius, roughly a five to seven minute walk, which is about the limit of what a driver will accept between parking and destination in Delhi conditions. 1 km as the secondary radius for market saturation. The schema enforces that the 1 km count is never below the 500 m count.

**Source.** Synthetic judgement, informed by the general urban-planning convention that 400–500 m is the standard pedestrian catchment.

**Validation.** Medium priority. The scoring engine can recompute the Competition pillar at 300 m and 800 m and check whether locality rankings hold. Radius choice tends to matter most in dense commercial cores where supply is thick, and least in outlying areas.

---

## A-11 — Footfall proxy

**Assumption.** Pedestrian and vehicle footfall around a lot is proxied by counts of nearby offices, retail units, restaurants, hospitals and educational institutions, together with metro proximity and locality land-use type.

**Why it is needed.** Actual footfall data for Delhi NCR is not publicly available at lot-level granularity. Something must stand in for it, because demand is the largest single pillar at 30%.

**Value.** A composite index computed in the scoring feature layer. Deliberately **not stored** in `location_demand`, which holds only measured POI counts — storing an estimate beside a measurement is how derived values quietly acquire the authority of observations.

**Source.** Derived from public POI data.

**Validation.** **High priority.** The weighting inside the composite is itself an assumption stack. the scoring engine must show the correlation between the proxy and observed occupancy, and must be candid that a high correlation partly reflects A-06's generator design rather than an external truth. The proxy's real defence is face validity: it should rank Connaught Place above a residential pocket, and if it does not, it is wrong regardless of what the correlation says.

---

## A-12 — Distance metric

**Assumption.** Straight-line (haversine) distance stands in for walking distance to metro stations, malls and competitors.

**Why it is needed.** Routed walking distance at scale requires a routing engine or a paid API. Straight-line distance is free, deterministic and reproducible.

**Value.** Haversine, computed in Python and SQL without PostGIS.

**Source.** Synthetic simplification over public coordinates.

**Validation.** Medium priority. Straight-line distance systematically *understates* real walking distance, and understates it worst where there are barriers — railway lines, the Yamuna, arterial roads without crossings, major flyovers. Two lots 400 m from a metro station are not equivalent if one has a footbridge and the other faces a six-lane road. the scoring engine should apply a uniform detour factor of roughly 1.2–1.3 and state that barrier effects remain unmodelled.

---

## A-13 — Hypothetical existing network

**Assumption.** PARK It Up's current footprint is represented by a synthetic set of sites in `existing_network_sites`.

**Why it is needed.** Strategic Fit measures coverage gaps and cannibalisation risk, both of which require a baseline network. Real inventory is confidential and is not used.

**Value.** A generated set of sites with locations and go-live dates, clearly labelled in the table comment as hypothetical.

**Source.** Synthetic. This assumption exists specifically to *avoid* using confidential information, and that reasoning should be stated rather than hidden — it is a point in the project's favour, not a weakness.

**Validation.** Medium priority. Because the baseline network is invented, Strategic Fit scores are conditional on it. the scoring engine must test at least one alternative network configuration to show how much the pillar depends on where the hypothetical sites were placed. If Strategic Fit rankings swing wildly, its 15% weight should be reconsidered.

---

## A-14 — Segment thresholds

**Assumption.** ACQUIRE NOW requires high attractiveness and at-or-above-median feasibility; PURSUE is high attractiveness with below-median feasibility; DEVELOP is mid-or-better attractiveness with at-or-above-median feasibility; AVOID is everything else.

**Why it is needed.** The four segments are the project's actual output — the thing a BD lead acts on. Cut points have to exist.

**Value.** **RESOLVED — calibrated from the observed base-case distribution.** The originally seeded placeholders (attractiveness 65 / 45, feasibility 60) were chosen before any score existed and were arbitrary in exactly the way the project brief warned against. They were replaced with distribution-derived cuts: high attractiveness **46.66** (67th percentile), DEVELOP attractiveness floor **33.42** (33rd percentile), feasibility floor **57.55** (median). These are recomputed on every scoring run and written back to `segment_rule`, so they track the distribution rather than being frozen.

**Source.** Derived from the score distribution. The *choice* of percentile — top tercile and median — remains an analyst judgement.

**Validation.** **Complete.** The resulting segment sizes are ACQUIRE NOW 25, PURSUE 15, DEVELOP 21, AVOID 59 out of 120, which satisfies the original test: a threshold putting 90% of lots in ACQUIRE NOW would tell the BD team nothing, and one putting three lots there would waste the analysis. Two regression tests now guard this — one asserts the persisted thresholds equal the corresponding percentiles of the current distribution, and one asserts that lots below the DEVELOP attractiveness floor but above the feasibility median are classified AVOID, which is what stops the segmentation degenerating into a 2×2 quadrant wash. The residual judgement is the percentile choice, not the numbers.

---

## A-15 — Baseline pillar weights

**Assumption.** Demand 30%, Revenue 25%, Competition 15%, Strategic Fit 15%, Feasibility 15%.

**Why it is needed.** A composite score requires weights. There is no way to avoid this judgement.

**Value.** Seeded as `BASELINE_V1` in `scoring_weight`. The reasoning: demand leads because a parking lot with no surrounding demand cannot be rescued by good commercial terms; revenue follows closely because the platform must eventually earn; and the remaining three are balanced because none obviously dominates the others.

**Source.** Synthetic business judgement. It is not derived from data, and no data available to this project could derive it — that would require observed outcomes from past acquisitions.

**Validation.** **High priority.** Three alternative weight sets are already seeded. The `EQUAL_WEIGHT` set is the important one: it is a control, not a proposal. If the ranking under equal weights is nearly identical to the baseline, then the carefully argued weighting is not earning its keep, and the honest report says so. the scoring engine must compute rank correlation between weight sets and report it, including the uncomfortable result if that is what appears.

---

## A-16 — Normalisation method

**Assumption.** Each pillar's inputs are min-max normalised to 0–100 across the study area.

**Why it is needed.** The pillars combine quantities in incompatible units — metres, rupees, counts, ordinals. They must be put on a common scale before weighting.

**Value.** Min-max within the study area, so scores are explicitly *relative*: 100 means best in this dataset, not best possible.

**Source.** Derived.

**Validation.** Medium priority. Min-max is chosen over z-scores because it guarantees the 0–100 bound the brief requires, and over percentile ranking because percentiles destroy information about the size of gaps — the difference between the best and second-best lot should be visible. Its weakness is sensitivity to outliers: one enormous lot compresses everything else. the scoring engine should check for this and consider winsorising at the 5th and 95th percentiles, documenting the choice either way.

---

## A-17 — Owner attitude ordinals

**Assumption.** Willingness to digitise, contract flexibility and documentation readiness are 1–5 ordinal scales.

**Why it is needed.** Feasibility depends on soft factors that resist precise measurement even in a real BD context.

**Value.** 1–5 with anchored endpoints documented in the schema comments — for willingness, 1 is actively resistant and 5 is already seeking a digital partner.

**Source.** Synthetic.

**Validation.** Medium priority. Treating ordinals as interval data when averaging them is a real methodological compromise: the distance from 1 to 2 is not necessarily the distance from 4 to 5. the scoring engine should acknowledge this and check whether the Feasibility ranking survives if the ordinals are collapsed to three levels instead of five.

---

## A-18 — Onboarding cost

**Assumption.** One-off onboarding cost ranges from ₹33,000 to ₹270,000 in the generated population, depending on size, operational complexity and whether capex is required.

**Why it is needed.** Feasibility must account for cost to acquire, not only willingness to be acquired. A cheap enthusiastic owner and an expensive enthusiastic owner are different propositions.

**Value.** The range above, correlated with `operational_complexity` and `requires_capex`.

**Source.** Synthetic.

**Validation.** Medium priority. the scoring engine should verify that onboarding cost is not double-counted — it should influence Feasibility, and it should *not* also be subtracted inside Revenue Potential, or lots with high setup costs would be penalised twice for the same fact.

---

## A-19 — Holiday calendar completeness

**Assumption.** `dim_date.is_public_holiday` marks only fixed-date national holidays and is therefore incomplete.

**Why it is needed.** Holidays shift parking demand substantially, particularly around retail.

**Value.** Independence Day, Gandhi Jayanti, Christmas and Republic Day are flagged. India's major festivals — Holi, Diwali, Eid, Dussehra — follow lunar and regional calendars, and asserting specific 2025–26 dates from memory would be precisely the kind of quiet fabrication this project exists to avoid.

**Source.** Public but deliberately partial.

**Validation.** Low priority, but a hard gate on claims. The pipeline did not expand the fixed-date list, so **no holiday-effect claim may be made anywhere in this project**. The flag understates reality and any analysis using it must say so.

---

## A-20 — Revenue definition

**Assumption.** `fact_lot_daily.gross_parking_revenue_inr` is the revenue collected by the **operator**, across all channels — not platform income.

**Why it is needed.** Confusing the two would overstate platform value by roughly an order of magnitude, and it is an easy mistake to make silently.

**Value.** Operator gross. Platform contribution is derived in the scoring engine as approximately gross revenue × platform booking share (A-07) × commission rate (A-08).

**Source.** Synthetic, but the *definition* is a structural choice recorded in the column comment.

**Validation.** Medium priority. the scoring engine must reconcile the two figures explicitly and label every chart axis with which one it shows. This is a labelling discipline issue more than a modelling one, and labelling failures of this kind are what make analysts lose an audience's trust mid-presentation.

---

## A-21 — Static tariffs

**Assumption.** Hourly rates do not change during the observation window.

**Why it is needed.** Time-varying pricing would require a rate-history table and would complicate every revenue calculation.

**Value.** One `hourly_rate_inr` per lot, fixed.

**Source.** Synthetic simplification.

**Validation.** Low priority. Real operators do adjust rates, particularly around events and festive peaks, but modelling that would add complexity without changing the relative ranking that the project actually produces.

---

## A-22 — Funnel conversion behaviour

**Assumption.** BD funnel conversion decays at each stage, with the sharpest drop between initial contact and a completed meeting.

**Why it is needed.** Business question 12 asks where the funnel loses most prospects, and the synthetic pipeline has to contain a realistic answer rather than uniform attrition.

**Value.** Declining stage-to-stage conversion, with loss reasons correlated to owner attributes — inaccessible decision makers producing "No Response", rigid contract posture producing "Wants Fixed Rent".

**Source.** Synthetic.

**Validation.** Medium priority, with the same circularity caveat as A-06. If the data pipeline generates loss reasons from owner attributes and the SQL analytics layer then reports that owner attributes predict loss reasons, that is the generator being read back rather than a finding. Business question 13 must be framed as a demonstration of the analytical approach, not as a discovered insight.

---

## A-23 — One lead per lot

**Assumption.** Each parking lot has at most one BD lead record.

**Why it is needed.** It keeps funnel analysis unambiguous — the conversion denominator is simply the number of lots approached.

**Value.** Enforced by a `UNIQUE` constraint on `outreach.parking_id`.

**Source.** Synthetic simplification. Reality is messier: leads get re-opened after a loss, and ownership changes hands.

**Validation.** Low priority. Re-approach cycles would be a natural dashboard extension and would require a lead-attempt table rather than a lead record.

---

## A-24 — No customer-level data

**Assumption.** The project contains no driver, customer or booking-level personal data.

**Why it is needed.** It bounds what the project can claim and removes an entire category of privacy risk.

**Value.** The finest grain in the model is a lot-day. There is no user table and there will not be one.

**Source.** Structural decision.

**Validation.** None. This is a deliberate constraint, not an estimate. It means questions about customer behaviour, repeat usage and price elasticity are permanently out of scope, which is stated in the business questions document rather than left to be discovered.

---

## A-25 — Public POI fallback completeness

**Assumption.** Counts derived from the bounded Nominatim fallback represent minimum observed OSM coverage, not an exhaustive count of every feature in the radius.

**Why it is needed.** Both public Overpass endpoints timed out during the source build. The fallback preserves real, traceable OSM identities and coordinates but search results are capped and favour named features.

**Value.** Cached, category-filtered Nominatim results inside each market box, combined with the two successful Overpass batches. No synthetic rows are added to the public POI counts.

**Source.** Public OSM data with a derived count and documented retrieval limitation.

**Validation.** **High priority.** the scoring engine must not interpret a zero office or retail count as proof that none exists. Demand scoring should combine multiple signals, handle sparse fields robustly, and sensitivity-test the result with office/retail inputs removed. A future source refresh against a complete local OSM extract is the correct fix.

---

## Standing rule for the analysis

Any new assumption introduced in the data pipeline, 3, 4 or 5 must be added here before the analysis depending on it is published, with the same five fields. An assumption that appears for the first time in a conclusion is an assumption nobody had the chance to challenge.
