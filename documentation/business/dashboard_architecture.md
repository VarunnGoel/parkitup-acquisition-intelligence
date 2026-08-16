# Dashboard Architecture

**Project:** PARK It Up Acquisition Intelligence
**Tool:** Power BI Desktop
**Status:** dashboard implementation package complete and dashboard-redesign design and information-architecture pass complete. The package includes reconciled star-schema extracts, DAX, exact visual specifications, a design system, a keep/remove inventory for every visual, and five actual-data static previews. Power BI Desktop was unavailable on the macOS development host, so no `.pbix` or `.pbip` is claimed.

dashboard-redesign gave each page a single dominant visual, cut the report from 34 visual elements to 22, restricted colour to one meaning per hue sourced from `DimPrioritySegment`, and made layout integrity a mechanical check rather than a review opinion. See `dashboard/powerbi/redesign.md` and `dashboard/powerbi/visual_inventory.md`.

The current visual design uses a compact horizontal page navigator rather than the left navigation concept in the original baseline proposal. Detailed implementation truth lives in `dashboard/powerbi/`; this document preserves the design rationale and business-question architecture.

---

## Design intent

Five pages, arranged so a business user moves from "where is the opportunity" to "what do I do on Monday" without backtracking. Each page answers exactly one question, and the question is written at the top of the page so a reader who lands there cold knows what they are looking at.

The governing principle is that **a visual which does not change a decision should not be on the page.** Occupancy by month is interesting; it is not on any page, because nobody acts on it. This rules out the usual filler — row counts, generic trend lines, pie charts of categorical splits — and it means each page carries fewer visuals than a typical portfolio dashboard. That is deliberate. A page with four visuals that each drive a decision reads as considered; a page with twelve reads as a tool demonstration.

The second principle is that the model must be **interrogable, not just consultable**. Page 4 exists so that any recommendation can be decomposed into the five pillars that produced it. If a user cannot get from a headline score to its reasons in two clicks, the model is a black box regardless of how transparent its arithmetic is.

---

## The data model as Power BI sees it

A star-ish schema with `parking_lots` as the central bridge. Dimensions are `dim_city`, `dim_locality`, `dim_date`, `dim_funnel_stage` and `dim_score_dimension`. Facts are `fact_lot_daily`, `fact_lot_hourly_profile`, `lot_score` and `lot_dimension_score`. The one-to-one attribute tables — `location_demand`, `competition`, `lot_acquisition_terms` — are best flattened into `parking_lots` at import, since a one-to-one relationship in the model adds join cost for no analytical benefit.

Relationships must be **single-direction, dimension to fact**. Bi-directional filtering is the standard way a Power BI model becomes unpredictable, and there is no requirement here that needs it. `owners` filters `parking_lots`; `dim_locality` filters `parking_lots` and `existing_network_sites`; `parking_lots` filters all four facts.

`dim_date` must be marked as the official date table so time intelligence behaves correctly. Note the join subtlety on the hourly profile: `dim_date.day_type` emits `Weekday`, `Weekend` and `Holiday`, while `fact_lot_hourly_profile.day_type` carries only the first two. the validation layer must map `Holiday` onto the weekend profile explicitly rather than letting the join drop rows silently.

**The weight-set slicer is the most important control in the report.** `scoring_weight_set` has no relationship to the dimensions; it filters `lot_score` and `lot_dimension_score` directly, and a slicer on `weight_set_code` lets the user switch between `BASELINE_V1`, `EQUAL_WEIGHT`, `DEMAND_LED` and `FEASIBILITY_LED` and watch the ranking move. That single control is what turns the sensitivity analysis from a static appendix nobody reads into something a sceptical stakeholder can push on themselves. It belongs on pages 1, 3 and 4, and its default selection must be the set flagged `is_default`.

---

## Page 1 — Executive Overview

**Question:** What are the biggest acquisition opportunities?
**Audience:** Founder, city head. Assume ninety seconds of attention.

**KPI cards.** Count of lots in `ACQUIRE_NOW` under the selected weight set — the headline number, because it is the size of the immediate opportunity. Total modelled monthly platform contribution across that segment, labelled as modelled. Mean `acquisition_score` across all scored lots, as context for judging whether a score of 70 is good. Count of localities containing at least one `ACQUIRE_NOW` lot, which signals whether the opportunity is concentrated or spread. Count of distinct owners across the segment, since that is the number of conversations required. Optionally, top-20 rank stability across weight sets, expressed as the count of lots that stay in the top 20 under all four weightings — an unusual card that immediately signals the analysis knows its own fragility.

**Visuals.** A horizontal bar chart of the top 15 lots by `acquisition_score`, with bars segmented by the five pillar contributions from `lot_dimension_score` so the composition of each score is visible without leaving the page — this is the single most valuable visual in the report. A table of the `ACQUIRE_NOW` list showing lot name, locality, owner, capacity, score, segment and the `bd_action` text from `segment_rule`, since the action is the point. A small multiple or bar chart of lot counts by segment, to show the shape of the portfolio. A locality bar chart of aggregate opportunity, as a bridge to page 2.

**Slicers.** Weight set, city, segment.

**Navigation.** Selecting a lot in either the bar chart or the table drills through to Page 4.

---

## Page 2 — Market Opportunity

**Question:** Which localities should PARK It Up target?
**Audience:** City head, expansion planning.

**KPI cards.** Count of localities assessed, with those below the three-lot evidence threshold excluded and reported separately. Count of localities flagged as underpenetrated. Mean capacity-weighted attractiveness across localities. Count of live `existing_network_sites`, as the current footprint baseline.

**Visuals.** A map — filled shapes if locality boundaries are available, otherwise bubbles at lot coordinates — sized by aggregate opportunity and coloured by penetration status. A map is genuinely justified here rather than decorative, because coverage gaps are a spatial concept and a table cannot show adjacency. A scatter plot of locality demand against competitor capacity per unit demand, which is the visual answer to question 2, with quadrants labelled. A ranked bar chart of localities by capacity-weighted attractiveness, with the lot count shown as a label so thin evidence is visible. A table giving the recommended entry sequence from question 14, with the reason for each locality's position.

**Slicers.** City, micro-market type, minimum lot count.

**Navigation.** Selecting a locality cross-filters the whole page and enables drill-through to a filtered lot list.

---

## Page 3 — Acquisition Matrix

**Question:** Which individual lots combine attractiveness with feasibility?
**Audience:** BD lead building a target list.

This is the analytical centrepiece. A scatter plot of `attractiveness_score` on the X axis against `feasibility_score` on the Y axis, one point per lot, sized by capacity and coloured by segment.

**The quadrant boundaries must be read from `segment_rule`, not typed into the report.** the validation layer should create measures that return `min_attractiveness` and `min_feasibility` from that table and drive the reference lines from those measures. Hard-coding 65 and 60 into a Power BI constant line would mean that when scoring recalibrates the thresholds — which assumption A-14 requires it to — the visual would silently disagree with the underlying segment assignment. That divergence would be invisible until someone noticed a point sitting in the wrong quadrant, and by then the report has lost its credibility.

Each quadrant carries a text label naming the segment and its action: high-high is Acquire Now, high attractiveness with low feasibility is Pursue, low-high is Develop, and the remainder is Avoid.

**KPI cards.** Lot count and mean score per quadrant, four cards, so the quadrant populations are legible without counting dots.

**Other visuals.** A scatter of capacity against `acquisition_score` answering question 7, with a trend line — and if the relationship is weak, the visual should be kept and annotated with that finding rather than removed. A table for question 16: lots ranked highly by a naive capacity proxy but placed low by the model, with the weakest pillar named for each. A table for question 6, high demand with favourable competition.

**Slicers.** Weight set, city, segment, owner type, minimum capacity.

**Navigation.** Any point drills through to Page 4.

---

## Page 4 — Parking Lot Deep Dive

**Question:** Why is this specific lot recommended?
**Audience:** The BD rep about to make the call, and the interviewer probing hardest.

This page is where the project's explainability claim is either honoured or exposed, so it should be built with more care than the other four combined. It is a drill-through page filtered to a single `parking_id`.

**Header.** Lot name, code, locality, city, parking type, capacity, tariff, operating hours, owner name and owner type. Enough that the rep knows what they are calling about.

**KPI cards.** `acquisition_score`, `attractiveness_score`, `feasibility_score`, `rank_overall`, segment label, and modelled monthly contribution.

**Score decomposition — the essential visual.** A table or waterfall reading directly from `lot_dimension_score`, one row per pillar, showing `dimension_name`, `subscore`, `weight_applied` and `weighted_contribution`, with the total reconciling to `acquisition_score`. A waterfall is the more persuasive form because it shows the total being built from its parts. Beside it, a radar or bar chart comparing this lot's five subscores against the portfolio mean, so a reader sees immediately which pillar is carrying the lot and which is dragging it.

**Demand profile.** A line chart of `avg_occupancy_rate` by `hour_of_day` from `fact_lot_hourly_profile`, with two series for weekday and weekend. This is where a rep discovers that a lot peaks at 8 p.m. rather than 11 a.m., which changes the pitch.

**Competitive context.** A card set from `competition` — competitors within 500 m and 1 km, nearest competitor distance, competitor average tariff against this lot's tariff, and aggregator-listed count. The tariff comparison is the number a rep will actually quote.

**Owner and deal context.** Willingness to digitise, contract flexibility, decision-maker accessibility, management system, documentation readiness, operational complexity, expected commission, estimated onboarding cost and setup days. Present the 1–5 ordinals with their anchored meanings rather than as bare numbers, because "willingness: 4" means nothing to a reader who has not read the data dictionary.

**Pipeline status.** Current funnel stage, pipeline status, contact attempts, lead source, assigned rep, and loss reason where applicable.

**Slicers.** Weight set only. Everything else is fixed by the drill-through context.

---

## Page 5 — BD Strategy

**Question:** Where should the BD team spend its effort?
**Audience:** BD team lead allocating rep time.

**KPI cards.** Overall conversion rate, leads to onboarded. Mean days to conversion. Count of active leads. The stage with the steepest drop-off, as a text card — a card that names a problem rather than reporting a number. Count of owners controlling more than one lot, since those are the leverage points.

**Visuals.** A funnel chart of distinct leads by stage, ordered by `stage_order`, with stage-to-stage conversion percentages labelled. A bar chart of loss reasons, ideally cross-tabulated against the stage at which each loss occurred, so it is clear whether documentation problems kill deals early or late. A conversion-rate-by-lead-source bar chart answering question 13, with lead volume shown alongside, because a source with a 100% conversion rate on two leads is noise. A table of owners ranked by feasibility with their lot count and combined capacity, answering question 11 — this is the multi-lot leverage view. A prioritised call list: `ACQUIRE_NOW` and `PURSUE` lots not yet contacted, ordered by score, with the `bd_action` text.

**Slicers.** City, lead source, pipeline status, assigned rep.

**Framing note.** Because loss reasons are generated in correlation with owner attributes (assumption A-22), the conversion-driver visuals demonstrate method rather than reveal behaviour. Page 5 should carry a visible note to that effect. A dashboard that quietly presents planted relationships as insight is the single most damaging thing this project could do to its own credibility.

---

## Accessibility and craft

Colour must never be the only signal. The four segments need a second encoding — position in the matrix quadrants, marker shape in scatter plots, or an explicit text label in tables — so the report remains readable in greyscale and for colour-blind users. Avoid red-green as the sole distinction between good and bad; a blue-to-orange divergent scale carries the same meaning and survives the most common forms of colour vision deficiency.

Keep to a small deliberate palette: one accent for the primary metric, one neutral for context, and one alert colour used sparingly. Four segment colours plus five pillar colours is already nine, which is at the upper limit of what a reader can hold.

Label every axis with its unit — score out of 100, capacity in bays, tariff in rupees per hour, distance in metres, contribution in rupees per month. Any visual showing a modelled monetary figure must say "modelled" in its title, not in a footnote.

Numbers that are relative must be described as relative. A score of 100 means best among the lots in this dataset, not best possible, and a subtitle saying so costs nothing and prevents a misreading that would otherwise go uncorrected.

---

## Measures the validation layer must create

| Measure | Description | Rough logic |
|---------|-------------|-------------|
| `Avg Acquisition Score` | Mean headline score across the filtered lots | `AVERAGE(lot_score[acquisition_score])` |
| `Weighted Acquisition Score` | Capacity-weighted mean, so large lots influence locality roll-ups proportionally | `DIVIDE(SUMX(lot_score, score × capacity), SUM(capacity))` |
| `Lots in Segment` | Count of lots in the selected segment | `CALCULATE(DISTINCTCOUNT(parking_id), ALLEXCEPT(segment))` |
| `Acquire Now Count` | Size of the immediate opportunity | `CALCULATE([Lots in Segment], segment_code = "ACQUIRE_NOW")` |
| `Segment Share` | Share of the portfolio in each segment | `DIVIDE([Lots in Segment], [Total Scored Lots])` |
| `Locality Coverage Gap` | Localities with demand above the median but no live network site | Count of localities where live site count = 0 and mean demand subscore > median |
| `Network Site Count` | Live sites in the current footprint | `CALCULATE(COUNTROWS(existing_network_sites), site_status = "Live")` |
| `Modelled Monthly Contribution` | Estimated platform income per lot per month | `gross revenue × booking share × commission ÷ months` — always labelled modelled |
| `Competitor Density Ratio` | Competitor capacity per unit of estimated demand | `DIVIDE(competitor_total_capacity_1km, demand proxy)` |
| `Tariff vs Competitor` | This lot's price position against local competitors | `hourly_rate_inr − competitor_avg_hourly_rate_inr` |
| `Funnel Stage Leads` | Distinct leads reaching the selected stage | `DISTINCTCOUNT(outreach_events[lead_id])` |
| `Stage Conversion Rate` | Proportion of the previous stage that advanced | Current stage leads ÷ prior stage leads, using `stage_order` |
| `Overall Conversion Rate` | Leads onboarded as a share of all leads | Won leads ÷ total leads |
| `Avg Days To Conversion` | Mean cycle time for won leads | `AVERAGE(outreach[days_to_conversion])` |
| `Steepest Dropoff Stage` | Names the worst-performing funnel transition | Stage with the minimum `Stage Conversion Rate`, returned as text |
| `Pillar Contribution` | A pillar's weighted contribution for the selected lot | `SUM(lot_dimension_score[weighted_contribution])` |
| `Pillar vs Portfolio Mean` | This lot's subscore against the portfolio average for that pillar | Subscore − `CALCULATE(AVERAGE(subscore), ALL(parking_lots))` |
| `Rank Stability Top 20` | Lots remaining in the top 20 across all four weight sets | Count of `parking_id` whose `rank_overall ≤ 20` for every `weight_set_id` |
| `Rank Change vs Baseline` | Movement in rank between the selected weight set and the baseline | Selected rank − baseline rank for the same lot |
| `Naive Rank` | Rank by capacity alone, for the question 16 comparison | `RANKX(ALL(parking_lots), capacity_cars)` |
| `Model vs Naive Divergence` | How far the model departs from the naive screen | `Naive Rank − rank_overall` |
| `Segment Min Attractiveness` | Threshold read from configuration to drive the matrix reference line | `MAX(segment_rule[min_attractiveness])` filtered to the segment |
| `Segment Min Feasibility` | As above, for the horizontal reference line | `MAX(segment_rule[min_feasibility])` filtered to the segment |
| `Owner Lot Count` | Lots controlled by one operator — the leverage measure | `CALCULATE(DISTINCTCOUNT(parking_id), ALLEXCEPT(owners))` |
| `Owner Combined Capacity` | Total bays a single negotiation would unlock | `SUM(capacity_cars)` grouped by owner |

---

## Out of scope for the dashboard

No row-level security. There is one audience and no confidential data, so RLS would be complexity for its own sake.

No scheduled refresh, gateway configuration or Power BI Service deployment. The dataset is a static synthetic snapshot; a refresh schedule would imply the numbers change, which they do not.

No embedding, no apps, no subscriptions.

No real-time or near-real-time data. This is a decision aid consulted when planning BD effort, not an operational tool. Anything suggesting live monitoring — a "last updated" ticker, a streaming tile — would misrepresent what the project is.

No forecasting visuals or Power BI's built-in trend forecasting. The underlying revenue chain rests on multiplicative synthetic assumptions, so a forecast line would carry an authority the data cannot support.
