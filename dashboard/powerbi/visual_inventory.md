# Visual Inventory

Every visual on the redesigned dashboard, why it is there, and what was taken
away. Counts: dashboard carried 34 visual elements across five pages; the redesign
carries 22.

## Page 1 - Executive Overview

| Visual | Role | Purpose | Kept because |
| --- | --- | --- | --- |
| KPI strip, 4 cells | Supporting | Size of the opportunity and of the addressable market | Each cell changes a decision: fund BD or not, how much revenue is at stake, how many markets to cover |
| Opportunity map | **Primary** | Where the actionable lots are concentrated | Answers the page question directly; concentration is the finding |
| Strongest targets, 6 rows | Secondary | The shortlist a manager will act on | Names the lots without pre-empting Page 3's full ranking |
| Portfolio shape strip | Supporting | How much of the universe is actionable | One strip shows 25 of 120 instantly |
| Three findings | Supporting | The interpretation a reader would otherwise have to derive | Each is a number plus a consequence |

## Page 2 - Market Opportunity

| Visual | Role | Purpose | Kept because |
| --- | --- | --- | --- |
| KPI strip, 4 cells | Supporting | Market count, leader, concentration, untouched markets | All four are market-level and none repeat Page 1 |
| Demand vs coverage scatter | **Primary** | Which markets are under-served relative to demand | The two axes are the expansion decision |
| Opportunity ranking, 10 bars | Secondary | Order of preference between markets | A scatter shows position, not rank order |
| Market decision table, 8 rows | Supporting | The numbers behind the ranking | Lets a reader audit the ranking |

## Page 3 - Acquisition Priority

| Visual | Role | Purpose | Kept because |
| --- | --- | --- | --- |
| Filter bar, 4 slicers + reset | Supporting | Scope the ranking | Four dimensions a BD manager actually filters by |
| Attractiveness vs feasibility matrix | **Primary** | Which lots qualify, and why | The segmentation rule is visible in the washes |
| What each segment means, 4 rows | Secondary | The play each segment implies | Turns a label into an instruction |
| Priority ranking, 10 rows | Supporting | The ordered shortlist with robustness | Persistence shows where the ranking stops being reliable |

## Page 4 - Parking Lot Deep Dive

| Visual | Role | Purpose | Kept because |
| --- | --- | --- | --- |
| Identity header + recommendation | Supporting | What this lot is and the call | The recommendation must be unmissable |
| Score breakdown with locality markers | **Primary** | Which pillars earn the score, against the market | Bar plus reference marker answers "is this good?" in one read |
| Against the locality, 6 rows | Secondary | Hard operational and economic comparison | Scores need non-score evidence behind them |
| Typical day | Supporting | When demand actually occurs | Peak-hour pressure is a commercial argument |
| Reasons on record + fact strip | Supporting | The recorded case for and against | Model-generated flags, not written narrative |

## Page 5 - BD Action Center

| Visual | Role | Purpose | Kept because |
| --- | --- | --- | --- |
| KPI strip, 4 cells | Supporting | Pipeline throughput | Standard funnel health |
| Pipeline funnel | **Primary** | Where lots are lost | Locates the leak |
| Why deals are lost | Secondary | The cause of the leak | Uses the full closed-lost population and is actionable |
| Next actions, 8 rows | Supporting | The work queue across segments | Mixing segments makes the action column informative |

## Removed

| Removed | Page | Reason | Replaced by |
| --- | --- | --- | --- |
| 2 KPI cards (`Lots analyzed`, `Average score`) | 1 | Six cards consumed the widest band on the page and neither changed a decision | Folded into the `Candidate universe` cell and its subtitle |
| Per-card accent bars | 1, 2, 5 | Six different accent colours in one row read as a rainbow with no meaning | One card, hairline dividers, colour only where semantic |
| 4-bar priority chart | 1 | Four bars, four gridlines and an axis label to convey four numbers | Single stacked strip |
| Top-targets rows 7-9 | 1 | Executive page does not need a partial ranking | Page 3 owns the full ranking |
| Lat/lon axes, ticks and gridlines on the map | 1 | Degrees are not a business quantity and the frame read as a scatter plot | Aspect-correct map with locality labels |
| 3 duplicated KPI cards (`Available capacity`, `High-priority lots`, `Average demand`) | 2 | Repeated Page 1 verbatim | Market-specific KPIs including target concentration |
| `Whitespace` table column | 2 | `HIGH_WHITESPACE` on every visible row: zero variance | Coverage % with a threshold flag; field kept in the model |
| Four-colour `market_class` encoding | 2 | Reused the segment hues for a different meaning on one page | Strong / not-strong split, class shown as text in the table |
| Scatter legend | 3 | Redundant once each point sits on the wash of its own segment | Quadrant labels and washes |
| `Owner type` and `Score` slicers | 3 | Neither changed this page's decision; five chips crowded the row | Four slicers plus a visible reset |
| `Top 20 (first 10 shown)` framing | 3 | A title that admits the visual does not fit its own brief | Honest `top 10 of 120` scope note |
| Five-colour score breakdown | 4 | Red marked the lot's *best* pillar; colour encoded nothing | One colour, locality reference markers, feasibility ruled off |
| 3 score rows in the benchmark table | 4 | Duplicated the bars now carrying locality markers | Table reduced to non-score evidence |
| Closed hours in the day trend | 4 | 06:00-23:00 closing looked like demand collapsing to zero | Trend restricted to operating hours, stated in the card note |
| `Largest drop` and `Robust Top 10` KPI cards | 5 | Drop is annotated on the funnel; persistence belongs to Page 3 | Four funnel KPIs |
| `Acquisition Rate by Lead Source` | 5 | Seven subsamples of 9-29 leads, already caveated as generator-shaped | `Why deals are lost` over all 64 closed-lost leads |
| `Most Robust Acquisition Opportunities` table | 5 | Listed the same seven lots as the table beside it | Merged into one queue with a persistence column |
| Uniform `Immediate outreach` action column | 5 | Identical on every row, so it carried no information | Mixed-segment queue with distinct actions and blockers |
