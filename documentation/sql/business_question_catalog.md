# SQL Business Question Catalog

the SQL analytics layer uses the implemented PostgreSQL schema as its source of truth. Operational, owner, outreach, commercial, and network data are synthetic; results demonstrate analytical method and must not be presented as real PARK It Up performance.

| Difficulty | Business question | Why it matters | SQL concepts | Output / interpretation |
|---|---|---|---|---|
| Beginner | How large is the candidate market by locality and parking type? | Establishes supply structure before ranking. | `GROUP BY`, `CASE`, ordering | Lot count, spaces, average capacity, price bands, dominant types. |
| Beginner | Which lots and localities have the highest occupancy and revenue? | Separates demand/economics from model recommendations. | joins, aggregation | Parking and locality performance rankings. |
| Intermediate | Which large lots are underused, and which small lots outperform? | Prevents capacity from being mistaken for quality. | CTE, percentile, conditional filtering | Utilization pattern candidates. |
| Intermediate | Which lots are high-price/weak-revenue or high-use/lower-price candidates? | Exposes pricing and utilization interaction without prescribing a price change. | `CUME_DIST`, `CASE`, CTE | Analytical pricing flags. |
| Advanced | Which peak hours matter? | Uses observed portfolio behavior instead of arbitrary clock hours. | percentile CTEs, aggregation, joins | Top-quartile hours within weekday/weekend profiles and lot-level peak demand. |
| Advanced | Where is demand high but competition relatively low? | Identifies parking-level whitespace. | `NTILE`, CTE, multivariate segmentation | High-demand/low-competition candidates and adverse market patterns. |
| Advanced | Which markets combine demand with limited platform coverage? | Supports independent expansion decisions. | multi-stage aggregation, window ranking | `vw_locality_summary` whitespace score and rank. |
| Advanced | Which targets strengthen clusters versus open markets? | Separates network density from geographic expansion. | joins, `CASE` | Cluster, new-market, redundancy, and remote-expansion groups. |
| Advanced | What are the top targets overall and within locality? | Produces an actionable portfolio and local alternatives. | `ROW_NUMBER`, `RANK`, `PARTITION BY`, `SUM OVER` | Top 10/20 and top three per locality. |
| Advanced | Where does the BD funnel lose leads? | Directs process improvement at the largest stage loss. | conditional aggregation, `LAG`, `LEAD`, first-value window | Stage conversion and drop-off in `vw_bd_funnel`. |
| Advanced | Which lead sources and owner types convert best? | Helps allocate limited outreach effort. | joins, filtered aggregates, date averages | Conversion and average days to acquisition by segment. |
| Advanced | Does capacity or digital readiness relate to conversion? | Tests whether BD prioritization traits align with outcomes. | `NTILE`, conditional aggregation | Conversion by capacity quartile and digital-payment status. |
| Advanced | How does each lot compare with peers? | Makes recommendations interview-defensible. | multiple `AVG OVER`, `RANK`, `DENSE_RANK` | `vw_parking_benchmarks`. |
| Advanced | Why did a lot rank high or low? | Exposes components, relative context, and reason flags. | window benchmarks, arrays, `CASE` | `vw_parking_rank_explanation`, filterable by `parking_id`. |
| Advanced | Are recommendations robust? | Shows whether target ranks depend on scenario assumptions. | `LAG`, `LEAD`, scenario joins | Adjacent scenario rank movement and stored stability percentage. |

## Difficulty Progression

- Beginner: `SELECT`, `WHERE`, `GROUP BY`, `ORDER BY`, `CASE` in `01_market_structure.sql`.
- Intermediate: joins, `HAVING`, filtered aggregation, date arithmetic, and readable CTEs in revenue and BD analysis.
- Advanced: peer windows, ranking, funnel progression, scenario comparison, and multi-stage market whitespace analysis.

## Important Definitions

- Revenue per space: average daily gross parking revenue divided by candidate capacity.
- Revenue per occupied space: average daily gross revenue divided by average occupied capacity; it is an efficiency context metric, not profit.
- Booking efficiency: average daily platform bookings divided by capacity.
- Peak hour: an hour in the top quartile of portfolio-average occupancy within its day type (`Weekday` or `Weekend`).
- Market whitespace: locality average demand score multiplied by uncovered candidate/network capacity share. It deliberately does not use acquisition score.
- Interested proxy: `owner_interest_level >= 3` among contacted leads. The actual schema has no formal `INTERESTED` funnel stage.
