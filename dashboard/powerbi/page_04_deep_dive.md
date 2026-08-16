# Page 4 - Parking Lot Deep Dive

**Business question:** Why should PARK It Up acquire this lot?

**Default state:** the rank 1 lot, reached by drill-through from Pages 1, 3 or 5.

**Decision supported:** whether to open a commercial conversation on this
specific lot, and what to raise in it.

## Layout

| Region | Grid | Contents |
| --- | --- | --- |
| Identity | cols 0-12, rows 0-3 | lot header and recommendation |
| Primary | cols 0-6, rows 3-14 | where the score comes from |
| Secondary | cols 6-12, rows 3-14 | against the locality |
| Supporting | cols 0-6, rows 14-24 | typical day |
| Supporting | cols 6-12, rows 14-24 | reasons on record |

## Visuals

1. **Identity header** - lot name, `lot_code`, locality, parking type, capacity,
   hourly rate, operating hours; rank and score; then the recommendation badge in
   the segment colour with the `recommendation` sentence from
   `FactAcquisitionScore` beside it.
2. **Where the score comes from** (primary) - horizontal bars for the five
   component subscores from `FactScoreComponent`, each labelled with its weight,
   all in one colour. The locality average for the same pillar is drawn as a
   reference marker on the bar, with the signed gap in text. A rule separates the
   four attractiveness pillars from feasibility, which is scored on its own axis
   and is not averaged into them.

   This single chart replaced a five-colour bar chart plus three duplicated rows
   of the benchmark table. Radar was considered and rejected: with five pillars a
   radar hides the size of each gap, which is the point of the visual.
3. **Against the locality** (secondary) - peak occupancy (p90), average
   occupancy, revenue per space, modelled monthly revenue, capacity, and
   competitors within 1 km, each with the market average and a signed gap in the
   metric's own unit. Percentage-point gaps read `pts`, rupee gaps read `INR`.
   Favourable gaps are green; for competitor count, fewer is favourable.
4. **Typical day** - weekday and weekend hourly occupancy from
   `FactHourlyProfile`, **restricted to the site's operating hours**. The dashboard
   version plotted all 24 hours, so the 06:00-23:00 closing time appeared as
   occupancy collapsing to zero at 23:00. The busiest hour is marked. Weekend is
   a neutral dashed line rather than a second hue.
5. **Reasons on record** - `positive_reason_flags` and
   `constraint_reason_flags` split into *Supports acquisition* and *Needs
   resolving*, then a fact strip: onboarding cost, setup days, documentation
   readiness out of 5, operational complexity out of 5, nearest competitor,
   competitor average rate, exclusivity. Numeric 1-5 fields are shown as `n/5`
   rather than as a bare code.

## Interactions

- Drill-through carries `parking_id` only; page slicers are not inherited.
- A back button returns to the originating page.
- Reason flags and the fact strip are read-only text and do not cross-filter.

## Acceptance checks

For rank 1, MCD Parking: score 78.5, capacity 347, hours 06:00-23:00, p90 peak
occupancy 89.5% against a 65.6% market average, average occupancy 62.0% against
39.4%, revenue per space INR 344 against INR 217, busiest hour 96% at 18:00. All
hours outside 06:00-22:00 must be excluded from the trend, and their stored
occupancy must be zero.
