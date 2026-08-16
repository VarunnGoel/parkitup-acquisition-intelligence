# Architecture Decision Records

Decisions where the project deliberately departed from the original specification, or where a reader would reasonably ask "why not the other way?" Each records what was decided, what was rejected, and the cost of being wrong.

These exist because baseline's most valuable output is not the schema — it is the reasoning behind it. A schema can be re-derived; the reasoning cannot.

---

## ADR-001 — Owner promoted to a first-class entity

**Decision.** Owner attributes live in `owners`, referenced by `parking_lots.owner_id`, rather than in a per-lot `owner_profiles` table.

**Rejected.** The specification's one-row-per-lot owner table.

**Reasoning.** The proposed design duplicated `owner_type` between `parking_lots` and `owner_profiles`, which is two places to be wrong. More importantly, it made a common BD situation inexpressible: one operator controlling four lots in the same locality, where a single negotiation unlocks all four. That is a genuine prioritisation lever — four mediocre lots under one willing owner may outrank one excellent lot under a difficult one — and the proposed model could not represent it. Operator-level analysis is now a `GROUP BY` rather than a fragile string match on owner name.

**Cost if wrong.** Minimal. If operator-level analysis proves uninteresting, the extra join is cheap.

---

## ADR-002 — Locality modelled as a dimension

**Decision.** `dim_locality` and `dim_city` as reference tables, with `parking_lots.locality_id` as a foreign key.

**Rejected.** Free-text `locality` and `city` columns on `parking_lots`.

**Reasoning.** Four of the sixteen business questions are asked at locality grain. With locality as text, every one of them depends on exact string matching — "Connaught Place" versus "Connaught place" versus "CP" — and there is nowhere to record locality attributes such as metro presence, land-use character or density band, all of which the Demand and Strategic Fit pillars need. Normalising also makes an inconsistency impossible: a lot cannot claim to be in Noida while its locality sits in Gurugram.

**Cost if wrong.** None identified. This is standard dimensional modelling.

---

## ADR-003 — Performance split across two grains

**Decision.** `fact_lot_daily` at one row per lot-day, plus `fact_lot_hourly_profile` at one row per lot per day-type per hour.

**Rejected.** A single `parking_performance` table keyed by lot, date and hour.

**Reasoning.** The rejected design implies roughly 120 lots × 365 days × 24 hours ≈ 1.05 million rows of synthetic data. Almost every business question is asked at daily grain or at typical-hour grain; virtually none needs a specific hour on a specific date. The split gives about 43,800 dated rows plus 48 profile rows per lot — around 4% of the row count — while preserving peak-hour analysis entirely.

The decisive argument is not performance but **checkability**. This project's credibility rests on a reader being able to verify figures by hand. A million-row synthetic table cannot be sanity-checked by inspection; 48 rows describing a lot's typical week can. A dataset small enough to argue with is worth more than one large enough to impress.

**Cost if wrong.** Genuine loss of capability: date-specific hourly analysis is impossible, so questions like "what happened at this lot on Diwali evening?" cannot be answered. Accepted, because the holiday calendar is deliberately incomplete anyway (A-19) and no business question requires it. Reversible by adding a third fact table later without touching existing tables.

---

## ADR-004 — Derived quantities excluded from raw tables

**Decision.** `location_demand` holds only measured POI counts and distances. Footfall estimates, density indices and activity scores are computed in the scoring feature layer and never stored alongside measurements.

**Rejected.** Storing `estimated_daily_footfall`, `commercial_density`, `weekday_activity` and `weekend_activity` as columns on `location_demand`.

**Reasoning.** Two reasons, one practical and one about defensibility. Practically, a stored derived value and its inputs can disagree, giving two sources of truth. On defensibility: `location_demand` is documented as containing public measured facts, and a column called `estimated_daily_footfall` sitting in it invites the question "how did you observe footfall?" — to which there is no good answer, because it was never observed. Keeping estimates in a clearly labelled derived layer means the provenance claim on each table stays true.

`acquisition_difficulty` was removed for a sharper reason: it is the *output* of the Feasibility pillar, computed from willingness, documentation readiness, complexity and owner type. Storing it as an input would have made the scoring circular — the model would predict difficulty from difficulty.

**Cost if wrong.** Slightly more work in the scoring engine, which must compute features rather than read them. Worth it.

---

## ADR-005 — Weights and thresholds stored as data

**Decision.** Pillar weights live in `scoring_weight`, segment thresholds in `segment_rule`, and `weight_set_id` forms part of the primary key of both scoring result tables.

**Rejected.** Weights as Python constants; thresholds as a SQL `CASE` expression.

**Reasoning.** Three consequences, in ascending order of importance.

Sensitivity analysis becomes non-destructive. Scoring under `DEMAND_LED` does not overwrite `BASELINE_V1`; both sit in `lot_score` simultaneously and can be compared with a self-join. Under the rejected design, testing an alternative weighting means recomputing and discarding, which makes rank-stability analysis impossible after the fact.

Every published score is traceable to the exact weighting that produced it, because the weight set is part of the key rather than an implicit property of when the code was run.

And the thresholds become **arguable**. A stakeholder who disagrees that 65 is the right attractiveness cut-off can see the number, in a table, with its rationale beside it. Buried in a `CASE` statement, that disagreement never surfaces — which is how arbitrary thresholds survive unchallenged into production.

**Cost if wrong.** A little more schema and a join in every scoring query. Trivial against the benefit.

---

## ADR-006 — Feasibility separated from attractiveness

**Decision.** `lot_score` stores `attractiveness_score` and `feasibility_score` as distinct columns, and the segmentation reads them independently. `dim_score_dimension.pillar_group` encodes the split.

**Rejected.** Averaging all five pillars into a single ranked score.

**Reasoning.** A lot scoring 85 on attractiveness and 30 on feasibility, and a lot scoring 55 on both, produce a similar weighted total and require completely different responses. The first has an identified obstacle and needs senior BD effort aimed at the obstacle rather than the price. The second is ordinary work for a junior rep. A single score sends the same person to both.

This also gives the Acquisition Matrix its two axes, which is what makes the output a two-dimensional decision rather than a leaderboard. The composite `acquisition_score` is retained for ranking, but the segmentation — the part that produces an action — reads the axes separately.

**Cost if wrong.** None. The composite is still computed and available.

---

## ADR-007 — No PostGIS

**Decision.** Haversine distance computed in numpy and plain SQL.

**Rejected.** PostGIS with `geography` columns and `ST_Distance`.

**Reasoning.** The only geometry the project needs is point-to-point distance between coordinate pairs — about fifteen lines of numpy. PostGIS brings GEOS and PROJ, complicates installation on any machine that has to run this, and would make the project harder for a reviewer to reproduce. If the analysis later needed polygon operations, isochrones or spatial joins against boundary files, the calculation would change entirely.

**Cost if wrong.** If locality boundary polygons become necessary for the Power BI map, PostGIS or a GeoJSON file would be needed. Deferred until there is a concrete requirement.

---

## ADR-008 — Constraints in the schema rather than in application code

**Decision.** 95 `CHECK` expressions enforce business rules at write time — geographic bounds, occupancy ranges, subset relationships, operating-hour coherence, pipeline state consistency, provenance integrity.

**Rejected.** Validating in the Python ETL and leaving the schema permissive.

**Reasoning.** A constraint in the database holds regardless of which path wrote the data — the ETL, a manual `psql` session, a fix applied at 11pm. A constraint in application code holds only for data that went through that code. Since a large fraction of the data-quality rules in the brief are row-scoped, moving them into the schema converts them from *detection after the fact* into *prevention*, and shrinks the data-quality suite to the cross-row and cross-table invariants a `CHECK` genuinely cannot express.

There is a secondary benefit worth naming: the constraints double as executable documentation. `CHECK (latitude BETWEEN 28.30 AND 28.95)` states the study area more precisely and more durably than a sentence in a README, and it cannot drift out of date.

**Cost if wrong.** Over-strict constraints reject legitimate edge cases and require a migration to relax. Mitigated by testing valid inserts alongside invalid ones in `scripts/validate_schema.sh` — a schema that accepts nothing is as broken as one that accepts anything, and only probing both directions catches that.

---

## ADR-009 — Two validators rather than one

**Decision.** `python/etl/validate_ddl.py` performs dependency-free structural checks; `scripts/validate_schema.sh` executes the schema against a live server and writes a report to `validation/`.

**Rejected.** A single test suite requiring a database connection.

**Reasoning.** Forced by circumstance and kept on merit. the schema layer was developed in an environment with no PostgreSQL and no network access to one, so the DDL could not be executed where it was written. Rather than assume correctness, the structural validator parses the DDL and checks the invariants that account for most schema defects — every table has a primary key, every foreign key resolves to a primary key or unique constraint, creation order permits applying files in filename order, the teardown drops everything created.

That validator turns out to be worth keeping regardless. It runs anywhere with no setup, so it can gate a commit in seconds, and it catches the errors that are cheapest to fix early. The shell harness handles what only a real server can prove: that PostgreSQL accepts the syntax, and that the constraints actually reject bad input.

The division of labour is stated explicitly in each file so neither is mistaken for the other. Passing the structural validator does **not** mean the schema is valid SQL, and the file says so.

**Cost if wrong.** Two things to maintain. Accepted, because the structural checks would otherwise have been skipped entirely.

---

## ADR-010 — Validation output written to the repository

**Decision.** `scripts/validate_schema.sh` writes a full report to `validation/report.txt`, including the catalogue PostgreSQL actually built.

**Rejected.** Printing pass/fail to the terminal.

**Reasoning.** A report file can be read after the fact, diffed between runs, and — the original motivation — read by someone who could not run the script themselves. It also captures the catalogue dump: every table, column type, constraint definition and index as the server created them, which is strictly better evidence than "the script exited zero". It shows what PostgreSQL *interpreted*, not merely that the SQL parsed.

The directory is git-ignored, so reports do not accumulate in version control.

**Cost if wrong.** Negligible.

---

## ADR-011 — Holiday calendar left deliberately incomplete

**Decision.** `dim_date.is_public_holiday` flags only fixed-date national holidays. Movable festivals — Holi, Diwali, Eid, Dussehra — are not flagged, and no holiday-effect claim may be made until the data pipeline populates them from an authoritative published source.

**Rejected.** Asserting festival dates for 2025–26 from memory.

**Reasoning.** These follow lunar and regional calendars. Stating specific dates without a source would be precisely the quiet fabrication this project exists to avoid, and it would be *invisibly* wrong — a reader has no way to spot an incorrect Diwali date, which makes it more corrosive than an obvious error. An explicitly incomplete flag with a documented gap is more honest than a complete-looking one that is silently wrong.

**Cost if wrong.** Holiday analysis is unavailable until the gap is filled, and the flag understates reality. Both are stated in assumption A-19 and in the seed file itself.

---

## ADR-012 — Delhi NCR only, and one vehicle class

**Decision.** Study area limited to five NCR cities within a fixed bounding box. Four-wheelers only; two-wheeler capacity, pricing and demand excluded.

**Rejected.** Multi-city coverage; modelling both vehicle classes.

**Reasoning.** On geography: Competition and Strategic Fit are *relative* measures, so "competitor density" and "distance from the existing network" require a defined market boundary. Spreading 120 lots across five metros would leave too few per locality for competition and clustering logic to mean anything, and min-max normalisation would compare lots in incomparable markets. Depth beats breadth here.

On vehicle class: modelling both would require two capacity columns, two tariffs, two occupancy series and a bay-equivalence factor, for a model whose output is a *relative ranking*. The naming makes the limit visible at the point of use — `capacity_cars`, not `capacity`.

**Cost if wrong.** The vehicle-class exclusion is the more consequential of the two. It understates demand at retail high streets and hospitals, precisely where two-wheeler share is highest in NCR, so those locations are systematically under-scored. This is a real bias, not a rounding error, and correcting it requires a schema change rather than a parameter change. Recorded as assumption A-04, and it should be volunteered in discussion rather than waited for.

---

## ADR-013 — Retire the standalone Streamlit simulator

**Decision.** Remove the simulator Streamlit application and keep Power BI as the project's only business-facing decision surface. Preserve all scoring and validation sensitivity, scenario, stress-test, and rank-stability logic.

**Rejected.** Maintaining both a Power BI dashboard and a standalone interactive what-if application in the final portfolio.

**Reasoning.** The simulator demonstrated scenario interactivity but added an application architecture, runtime, UI dependency set, and duplicate wrappers around analysis already owned by the earlier build stages. For a data analyst or business analyst portfolio, that extra surface dilutes the stronger story: constrained PostgreSQL data, explainable SQL/Python analysis, a validated acquisition model, and a decision-ready Power BI report. Scenario robustness remains visible through validation outputs and the Power BI scenario tables, so retiring the app removes presentation duplication without removing analytical depth.

**Migration.** Removed `app/`, Streamlit and Altair dependencies, app-only tests, the simulator audit script, and generated simulator validation artifacts. `python/analysis/scoring_engine.py`, `python/model_validation/sensitivity.py`, the validation notebooks and exports, `FactScenarioScore`, `FactScenarioComponent`, `FactLocalityScenario`, and `DimScenario` remain authoritative.

**Cost if wrong.** Stakeholders cannot create arbitrary ad hoc scenarios through a custom web UI. The accepted replacement is a curated scenario slicer and robustness reporting in Power BI, which is sufficient for the portfolio audience and avoids a second product surface.
