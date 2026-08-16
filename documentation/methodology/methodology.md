# Methodology

**Project:** PARK It Up Acquisition Intelligence
**Status:** framework definition. Results are produced by the layers documented alongside this file.

---

## 1. The business problem

PARK It Up is a parking technology platform operating in Delhi NCR. It does not own parking capacity. It partners with existing operators — mall managements, resident welfare associations, hospitals, private companies, municipal bodies — to digitise their lots with bookings, digital payment and occupancy visibility, and earns a commission on bookings originated through the platform.

The constraint that makes this an analytical problem is bandwidth. A business development team can hold perhaps a dozen live negotiations at once. Delhi NCR contains thousands of parking facilities. The question is not whether a given lot is worth having; almost any lot is worth having on generous enough terms. The question is which lots deserve the next dozen conversations.

Most BD prioritisation in practice is done by proximity, familiarity and whoever answers the phone. That produces a network shaped by accident rather than intent. The purpose of this project is to replace that with something defensible: a ranked, explainable priority score that a BD lead can act on and a founder can interrogate.

Two design commitments follow from the audience. First, the output has to be a *decision*, not a number — a segment with an attached instruction, not a leaderboard. Second, every score has to decompose into reasons. A model that says "lot 47 scores 78" is useless in a negotiation; a model that says "lot 47 scores 78, driven mainly by demand and weak nearby supply, held back by an inflexible owner" tells a BD rep what to prepare for.

### Why not machine learning

The deliberate absence of ML here is a decision, not an omission, and it rests on a specific fact: there is no ground truth. Supervised learning needs labelled outcomes — lots that were approached and either converted or did not, with enough history to learn from. This project has none, because it uses no confidential PARK It Up data. A model trained on synthetic labels would learn the data generator, not the market.

Even with real outcome data, a transparent weighted model would likely remain the right answer at this scale. A BD lead who cannot explain to an operator why their lot is a priority cannot use the tool. Gradient boosting on 120 rows would also overfit comprehensively. The scoring framework below is defensible line by line, which is worth considerably more than sophistication that cannot be defended.

---

## 2. Data architecture

### 2.1 Provenance separation

The project mixes publicly sourced and simulated data, and keeps the two rigorously distinguishable. This is a hard requirement rather than a stylistic preference: the author previously interned at PARK It Up, and the project must demonstrably contain no confidential information.

Public data covers what can be verified externally — parking facility locations, names and types from OpenStreetMap; localities and their administrative context; metro station positions; counts of nearby offices, retail units, restaurants, hospitals and schools; and the locations of competing parking supply.

Synthetic data covers everything that would be commercially sensitive or is simply unavailable at this granularity — occupancy, entries, bookings, revenue, dwell time, owner attitudes, commission rates, onboarding costs, and the entire business development pipeline.

Provenance is recorded in three places. Every table carries a `COMMENT ON TABLE` declaring its provenance class, so the classification travels with the database rather than living only in documentation. Tables where provenance genuinely varies row by row carry a `record_source` column, and a `CHECK` constraint prevents a synthetic record from carrying an `osm_id` and thereby masquerading as extracted data. The column-level register is `data_dictionary.md`.

The rule that matters most: no figure derived from synthetic data is ever presented as a finding about the real world. Relative rankings produced by the framework are defensible as a demonstration of method. Absolute rupee forecasts are not, and the project does not make them.

### 2.2 Layering

Data moves through four layers, and the boundaries between them are load-bearing.

**Reference** holds dimensions: cities, localities, the calendar, funnel stages and scoring pillars. Small, slowly changing, mostly public or configuration.

**Raw entity** holds what a lot *is*: `parking_lots` and its one-to-one companions `location_demand`, `competition` and `lot_acquisition_terms`, plus `owners`. These tables hold measured or asserted attributes only.

**Fact** holds what a lot *did*: `fact_lot_daily` for the dated series and `fact_lot_hourly_profile` for the typical-week shape, plus the BD pipeline in `outreach` and `outreach_events`.

**Derived** holds what the model *concludes*: features, then `lot_dimension_score` and `lot_score`.

The critical rule is that **derived quantities never live in raw tables**. Four fields from the original specification were removed on these grounds. `current_occupancy` was a point-in-time reading of a time series and belongs in the facts. `estimated_daily_footfall`, `commercial_density`, `weekday_activity` and `weekend_activity` are all computed quantities, and storing an estimate beside a measurement in `location_demand` would let it quietly acquire the authority of an observation. The question "how did you observe footfall?" has no good answer, so the schema is arranged so nobody can ask it. `acquisition_difficulty` was removed for a sharper reason: it is the *output* of the Feasibility pillar, and storing it as an input would have made the scoring circular.

### 2.3 Grain discipline

Two grain decisions shape the model.

The performance series is split. A single table keyed by date and hour would have required roughly 1.05 million synthetic rows to serve questions asked almost entirely at daily or typical-hour grain. Instead `fact_lot_daily` carries about 43,800 rows of dated series and `fact_lot_hourly_profile` carries 48 rows per lot describing a typical week. Peak-hour analysis is preserved; the dataset stays small enough to inspect by hand when a figure looks wrong, which is a property worth more than completeness on a project whose credibility depends on being checkable.

Scoring results are keyed by weight set. `weight_set_id` is part of the primary key of both `lot_score` and `lot_dimension_score`, so alternative weightings coexist instead of overwriting each other. This is what makes sensitivity analysis a query rather than a re-run, and rank stability measurable after the fact.

---

## 3. Feature engineering strategy

Features are computed in a scoring layer that reads the raw and fact tables and writes nothing back to them. Four families are needed.

**Proximity features** convert distances into decaying influence. Raw metres are the wrong scale for scoring: the difference between 100 m and 300 m from a metro station matters far more than the difference between 3 km and 3.2 km. Metro and mall distances will therefore be transformed with a decay function rather than used linearly, and a detour factor of roughly 1.2–1.3 applied to reflect that straight-line distance systematically understates walking distance (assumption A-12).

**Density features** aggregate the POI counts in `location_demand` into a composite footfall proxy, weighted by how strongly each category generates parking demand — offices and malls more than schools, which mostly generate two-wheeler and pedestrian traffic that this model excludes. Because no observed footfall exists anywhere in the project, this proxy is the single largest source of construct risk and is recorded as assumption A-11.

**Utilisation features** summarise the fact tables per lot: mean and peak occupancy, weekday-weekend differential, the shape and height of the daily peak from the hourly profile, and — most importantly — *headroom*, the gap between current utilisation and what the location could sustain. Headroom is where the platform's incremental value lives, and it is why the framework does not simply reward high occupancy.

**Economic features** build the platform contribution estimate: capacity, achievable utilisation, tariff, dwell time, platform booking share and commission rate, combined into an expected monthly contribution. Every input here is synthetic, so the resulting figure is used for *ordering* lots and never quoted as a forecast.

**Network features** compute haversine distance from each lot to the nearest site in `existing_network_sites`, plus locality-level coverage counts. No PostGIS: the geometry needed is point-to-point distance, which is about fifteen lines of numpy, and the dependency would complicate installation for no analytical gain.

---

## 4. Scoring methodology

### 4.1 Structure

Five pillars, each normalised to 0–100, combined by weights that sum to 1. Weights live in the `scoring_weight` table rather than in code, so a scenario is a row set and not an edit.

| Pillar | Group | Baseline weight | Measures |
|--------|-------|-----------------|----------|
| Demand Potential | Attractiveness | 30% | Latent parking demand around the lot |
| Revenue Potential | Attractiveness | 25% | Expected economic value to the platform |
| Competition Opportunity | Attractiveness | 15% | Favourability of the local supply picture |
| Strategic Fit | Attractiveness | 15% | Contribution to network strategy |
| Acquisition Feasibility | Feasibility | 15% | Realistic probability of closing |

### 4.2 Demand Potential — 30%

The largest weight, on the reasoning that a lot with no surrounding demand cannot be rescued by good commercial terms, while a lot in a strong location can survive mediocre ones.

Inputs are the composite footfall proxy from surrounding POI density; metro proximity after decay transformation; the micro-market character of the locality, which sets the expected demand pattern; observed average occupancy as evidence that latent demand is real; and peak intensity from the hourly profile, since a lot that is full for two hours a day is a different proposition from one steadily busy for ten.

The subtlety worth stating: occupancy enters as *corroboration*, not as the primary signal. A lot at 90% occupancy in a weak location is probably small or cheap rather than well placed. Location characteristics lead; occupancy confirms.

### 4.3 Revenue Potential — 25%

Expected monthly platform contribution, driven by capacity, achievable utilisation, tariff, dwell time, platform booking share and commission rate.

Two decisions here carry real weight. First, the pillar uses *sustainable* rather than peak utilisation (assumption A-09). Scoring on peak would reward saturated lots, which is backwards — a lot at 95% peak has little room for the platform to add incremental bookings. Second, contribution is computed on the platform-booked share of revenue, not on the operator's gross. Conflating the two would overstate platform value by roughly a factor of four, and the schema comment on `gross_parking_revenue_inr` says so explicitly to stop it happening by accident.

Because both the booking share and the commission rate are synthetic and multiplicative, their errors compound. scoring tests them jointly rather than separately.

### 4.4 Competition Opportunity — 15%

Scores high where demand exists but competing supply is thin. It is a *relative* measure — competitor capacity per unit of estimated demand, not a raw competitor count — because five competitors around Connaught Place means something entirely different from five around a suburban office park.

Inputs are competitor capacity within 1 km relative to estimated demand; distance to the nearest competitor; the lot's tariff position against the local competitor average; and aggregator penetration, the count of nearby lots already listed on a rival platform. That last input carries strategic weight beyond its size: a market a competitor has already digitised is harder to win and less valuable once won.

A deliberate asymmetry: high competitor *density* is penalised, but a high competitor *price* is rewarded, since it indicates a market that supports premium tariffs.

### 4.5 Strategic Fit — 15%

The only pillar with a non-monotonic input, which makes it the most interesting to specify and the easiest to get wrong.

Distance from the existing network is scored as a band rather than a slope. Very close to a current site is penalised for cannibalisation — a new lot 200 m from one already live largely moves bookings rather than adding them. Very far is penalised too, because an isolated site gets no operational or brand density benefit and costs more to service. The favourable range sits between, and the scoring engine must implement it as a band, not a linear term. A linear "further is better" treatment would actively recommend cannibalisation, and a linear "closer is better" treatment would recommend clustering into saturation.

Other inputs are locality coverage gap, the priority of the micro-market type, and the lot's capacity contribution relative to what the network already holds in that locality.

Because the baseline network is hypothetical (assumption A-13), this pillar is conditional on where those synthetic sites were placed. the scoring engine must test at least one alternative configuration, and if rankings swing badly, the 15% weight needs revisiting.

### 4.6 Acquisition Feasibility — 15%

Kept structurally separate from the other four, and this separation is the most important structural decision in the framework.

Inputs are owner willingness to digitise and contract flexibility, both 1–5 ordinals with anchored endpoints; digital readiness from payment capability and current management system; documentation readiness; whether the decision maker is reachable at all, which is a frequent hard blocker for RWA and municipal owners; operational complexity, inverted; onboarding cost and setup time, inverted; and an owner-type adjustment, since municipal lots involve procurement processes that private operators do not.

The reason feasibility is not simply averaged into the other four: a lot that is wonderful and unobtainable requires a completely different BD response from one that is mediocre and easy. Averaging the two would produce identical scores for both and hide precisely the distinction the BD team needs. Instead, attractiveness and feasibility form the two axes of the Acquisition Matrix, and the segmentation reads them separately.

### 4.7 Normalisation

Each pillar's inputs are min-max normalised to 0–100 across the study area, with cost-like inputs inverted first so that higher always means better.

Min-max was chosen over two alternatives. Z-scores do not respect the 0–100 bound the project requires. Percentile ranking destroys information about gap size — the difference between the best lot and the second-best should be visible, and under percentile ranking it never is. Min-max keeps the bound and preserves relative distances.

Its weakness is outlier sensitivity: a single 2,000-bay facility compresses every other lot's capacity score toward zero. the scoring engine must check for this and consider winsorising at the 5th and 95th percentiles, documenting the choice either way.

The consequence to state plainly in every presentation: scores are **relative to this dataset**. A score of 100 means best among the 120 lots modelled, not best possible. Adding lots changes existing scores, which is a property of the method and not a defect, but it does mean scores are not comparable across dataset versions.

### 4.8 Composite score

```
subscore_p          ∈ [0, 100]   for each pillar p
weight_p            ≥ 0,  Σ weight_p = 1

acquisition_score   = Σ (subscore_p × weight_p)

attractiveness      = Σ (subscore_p × weight_p) / Σ weight_p
                      over p ∈ {DEMAND, REVENUE, COMPETITION, STRATEGIC_FIT}

feasibility         = subscore_FEASIBILITY
```

The 0–100 guarantee is structural rather than clamped. Because every subscore lies in [0, 100] and the weights are non-negative and sum to 1, the composite is a convex combination of values in [0, 100] and therefore necessarily lies in [0, 100]. No clipping is applied anywhere, which matters: a clamp would silently mask a bug in the normalisation step, whereas a `CHECK` constraint that the score is between 0 and 100 will fail loudly. That constraint is in the schema.

Attractiveness is renormalised by dividing by the sum of the four attractiveness weights — 0.85 under the baseline — so it also remains on a 0–100 scale and stays comparable across weight sets that distribute those four weights differently.

### 4.9 Explainability

Explainability is implemented, not asserted. `lot_dimension_score` stores, for every lot under every weight set, each pillar's subscore, the weight applied and the resulting contribution. Any published score can therefore be decomposed into its five parts long after the code has moved on, and rule DQ-021 reconciles the stored total against the sum of its components within a tolerance of 0.05.

This table is what the deep-dive dashboard page reads from, and it is what turns "lot 47 scores 78" into a sentence a BD rep can use in a meeting.

---

## 5. Acquisition segmentation

Scores are translated into four actions through the `segment_rule` table. Rules are evaluated in priority order and the first match wins, with the lowest-priority rule carrying no bounds, so the rule set is total by construction and every lot receives exactly one segment.

| Segment | Condition | BD action |
|---------|-----------|-----------|
| **ACQUIRE NOW** | Attractive and closeable | Assign a named owner this week; open commercial discussions |
| **PURSUE** | Attractive but constrained | Work the blocker before the commercials — find the decision maker, test a pilot, revisit exclusivity |
| **DEVELOP** | Moderately attractive, easy to close | Batch into low-cost outreach; suitable for junior reps |
| **AVOID** | Everything else | No outreach; revisit only if the surrounding market changes |

The logic behind the split is that attractiveness and feasibility fail in different ways and demand different responses. A high-attractiveness, low-feasibility lot is not a bad lot — it is a lot with an identified obstacle, and the correct action is to attack the obstacle rather than the price. That is senior BD work. A moderately attractive but easy lot is genuinely useful for building network density and coverage credibility, and it is where a junior rep should be spending time. Collapsing both into a single ranked list would send the wrong person at each.

**The thresholds were provisional at design time and have since been calibrated.** The originally seeded values — attractiveness 65 and feasibility 60 for ACQUIRE NOW, attractiveness 45 for DEVELOP — were chosen to be structurally sensible before any score existed, which made them arbitrary in exactly the way the project brief warned against. They were subsequently re-derived from the observed base-case distribution: high attractiveness at **46.66** (67th percentile), the DEVELOP attractiveness floor at **33.42** (33rd percentile), and the feasibility floor at **57.55** (median). The resulting segment sizes are ACQUIRE NOW 25, PURSUE 15, DEVELOP 21, AVOID 59 — which passes the test this paragraph originally set, since a threshold placing 90% of lots in ACQUIRE NOW tells the BD team nothing and one placing three lots there wastes the analysis. The calibration is recomputed on every run and a regression test asserts the persisted thresholds still equal the corresponding percentiles of the current distribution. Recorded as assumption A-14.

---

## 6. Sensitivity analysis

The framework rests on judgement, so the honest question is not whether the weights are right but how much the recommendation depends on them. Four tests are planned.

**Weight sensitivity.** Four weight sets are already seeded: `BASELINE_V1`, `DEMAND_LED`, `FEASIBILITY_LED` and `EQUAL_WEIGHT`. The last is a control rather than a proposal, and it is the most informative of the four. If the ranking under equal weights closely matches the baseline, then the carefully argued weighting is not doing real work, and the correct report says exactly that. the scoring engine must compute rank correlation between weight sets and the overlap in the top 20, and publish the result including the uncomfortable version.

**Assumption sensitivity.** The four high-priority assumptions — dwell time (A-05), platform booking share (A-07), commission rate (A-08) and the utilisation basis (A-09) — are re-run at multipliers around their baseline values. Booking share and commission are tested jointly because they multiply, and a joint grid shows compounding that separate tests miss. This is what answers business questions 9 and 10.

**Threshold sensitivity.** Segment boundaries are moved to see how many lots change classification. A boundary where a five-point shift reclassifies half the portfolio is not a boundary, and if that is what the distribution shows, the segmentation needs a different basis.

**Structural sensitivity.** The competitor radius (A-10) and the hypothetical network configuration (A-13) are varied, since both are arbitrary choices that could plausibly have been made differently.

The output is a statement of the form "the top ten lots are stable across all four weightings; ranks eleven to thirty are not" — which is far more useful to a BD lead than a single ranking presented with false confidence.

---

## 7. Data quality framework

Validation is split by what each mechanism can actually enforce, and the split is deliberate.

Row-scoped invariants are enforced at write time by `CHECK` constraints, so bad data cannot enter the database at all. This covers negative prices, occupancy above 100%, coordinates outside Delhi NCR, impossible capacities, contradictory operating hours, bookings exceeding entries, cancellations exceeding bookings, mean occupancy above peak, competitor radius nesting, and pipeline states that contradict themselves. The schema carries 95 such expressions.

Everything a `CHECK` fundamentally cannot express lives in `sql/data_quality/dq_checks.sql`: cross-row invariants such as weights summing to 1.0, cross-table completeness such as every lot needing a `location_demand` row, reconciliation between a stored total and the sum of its parts, funnel stage contiguity, and distributional smells such as an all-zero series or revenue implausible against entries and tariff. Thirty-two rules, each reporting PASS or FAIL with a violation count.

Two details of that design are intentional. Rules always report even when they pass, because "the check ran and found nothing" and "the check never ran" are different states that a failures-only report cannot distinguish. And rules touching source tables pass trivially while those tables are empty, so the framework is installed before the data rather than retrofitted after it.

---

## 8. Limitations

Stated here rather than buried, because a reader who finds these themselves will discount everything else.

**No ground truth exists.** Nothing in this project can be validated against actual acquisition outcomes, because no outcome data is used. The framework's defence is therefore face validity, internal consistency and sensitivity testing — not predictive accuracy. It has never been shown to predict anything, and it cannot be until it is applied against real results. This is the single most important limitation and the honest answer to "how do you know it works" is: I don't, and here is what I would need to find out.

**Circularity risk in the synthetic data.** Occupancy is generated to correlate with location characteristics (A-06), and funnel loss reasons are generated to correlate with owner attributes (A-22). If the scoring engine then reports that location predicts occupancy, that is the generator being read back rather than a discovery. Wherever this risk applies, the analysis must be framed as a demonstration of method rather than a finding. The correct framing is "here is how I would test this relationship", not "here is the relationship I found".

**Scores are relative and dataset-bound.** Min-max normalisation means scores shift when the population changes, and are not comparable across dataset versions.

**Two-wheelers are excluded** (A-04), which understates demand most at retail high streets and hospitals — precisely where two-wheeler share is highest in NCR. Correcting this needs a schema change, not a parameter change.

**Distance ignores barriers** (A-12). Two lots 400 m from a metro station are not equivalent if one has a footbridge and the other faces six lanes of traffic. Railway lines, the Yamuna and major flyovers are all invisible to a haversine calculation.

**The holiday calendar is deliberately incomplete** (A-19). Movable festival dates were not asserted from memory, so no holiday-effect claim may be made until the data pipeline populates them from an authoritative source.

**Ordinals are treated as interval data** when averaged. The distance from 1 to 2 on a willingness scale is not necessarily the distance from 4 to 5.

**Commission and terms are invented** (A-08, A-18). They are not PARK It Up figures, are not derived from any, and no conclusion about actual platform economics can be drawn from them.

---

## 9. What would make this stronger

If the project were extended with real data rather than more technique, the highest-value additions would be, in order: actual acquisition outcomes to test the score against; observed footfall or mobile-location data to replace the POI proxy; competitor tariffs collected by field survey; and two-wheeler demand. None of these require a more sophisticated model. All of them would do more for the quality of the recommendation than any amount of additional machinery — which is itself a useful thing to be able to say in an interview.
