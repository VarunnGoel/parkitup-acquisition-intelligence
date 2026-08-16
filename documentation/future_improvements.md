# Future Improvements

Everything here is deferred work, not planned work. The project is complete as an
analytical exercise; this file exists so that improvements identified during the
final audit are recorded rather than bolted on.

The organising principle: almost every limitation in this project traces back to
one cause — the operational and commercial layer is modelled rather than
observed. So the roadmap is ordered by what real PARK It Up data would unlock,
most valuable first.

---

## What real data would change

### 1. Actual booking history replaces the demand proxy

**Today.** The Demand pillar is `0.50 × observed demand + 0.40 × location demand
+ 0.10 × headroom`, where "observed" occupancy is generated from a location
signal and "location demand" is built from metro distance, POI counts, transit
stops and a market prior. This is the heaviest pillar at 30% and it carries 44.7%
of the variance in the composite, so it is also the most consequential
assumption in the model.

**The specific weakness.** Sparse OpenStreetMap POI coverage is indistinguishable
from genuinely low activity. A lot beside a busy metro station in an unmapped
neighbourhood scores low for a data-coverage reason, not a demand reason. The
project treats zero counts as incomplete rather than as evidence of absence, but
that mitigation cannot recover information that is not there.

**With real data.** Observed occupancy and booking volume replace the proxy
entirely, and the location component drops from 40% of the pillar to a small
prior used only for lots with no operating history. The headroom term — currently
deliberately capped at 10% so a weakly utilised lot cannot rank on proxy data
alone — could be widened, because the gap between potential and realised demand
would be measurable rather than inferred.

### 2. Actual revenue replaces the illustrative economics

**Today.** Expected monthly platform contribution is an identity: net bookings ×
dwell hours × tariff × a 0.76 realisation factor × commission × 30. Every term
except tariff is synthetic, and the realisation factor is the mean of a generated
distribution restated as a constant in three separate calculation sites.

**With real data.** The identity is replaced by observed contribution per lot,
and the realisation factor becomes a measured collection rate that almost
certainly varies by lot type and payment method rather than being one number.
The Revenue pillar currently censors 6 of 120 lots at exactly 0 or exactly 100
after winsorisation; a wider observed distribution would likely reduce that.

### 3. Actual acquisition history makes feasibility empirical

This is the single highest-value improvement, and the one place where machine
learning would genuinely earn its place.

**Today.** Acquisition Feasibility is an 11-component weighted index over owner
attributes — willingness, contract flexibility, digital readiness,
documentation, decision-maker access, operational simplicity, onboarding cost,
setup speed, exclusivity, capex need and owner-type friction. Every weight is a
judgement and every input is synthetic. It is the most assumption-laden pillar
while carrying real influence over the segmentation.

**With real data.** A few hundred labelled outreach outcomes — signed, refused,
stalled, and why — turn this into a supervised classification problem with an
actual target variable. Fit a probability of signing, calibrate it, and report it
as a probability rather than an index. That is a defensible use of a model
because the target exists and the coefficients would be estimated rather than
asserted. The current project declines ML precisely because neither is true yet.

**What to collect to make this possible.** Outcome per approach, the reason for
refusal, elapsed time to decision, and which owner attributes were verified
versus assumed at the point of contact. Without the last one, the model would
learn from attributes recorded after the fact, which is a leakage trap.

### 4. Actual customer demand improves location estimation

**Today.** Location demand uses OSM proximity and counts, and distance is
haversine — straight-line, ignoring roads, one-way systems, barriers and actual
walking routes. A lot 300 m away across a rail line is treated as closer than one
500 m away on the same street.

**With real data.** Origin-destination data from the platform's own app — where
users search, where they fail to find parking — measures demand directly instead
of inferring it from what is nearby. Unserved search volume by area would be the
strongest possible input to the Strategic Fit pillar, because it identifies
whitespace by observed demand rather than by absence of supply. Routing distance
would replace haversine.

### 5. Actual competitor data replaces the supply-pressure proxy

**Today.** Competitor capacity is null for every candidate in OpenStreetMap, so
the Competition pillar cannot use it. Instead it uses
`ln(1 + competitor count within 1 km) / market demand prior` as a count-based
supply-pressure proxy, plus aggregator penetration, competitor distance and
tariff headroom. The project states this openly rather than imputing capacity it
does not have.

**With real data.** Competitor capacity, occupancy and pricing convert supply
pressure from a count density into a genuine supply-versus-demand ratio. That
also unlocks the one documented business question the project cannot currently
answer at all: which localities have strong demand and weak supply, in capacity
terms rather than count terms.

### 6. Actual contract economics improve contribution margin

**Today.** Commission is generated per lot from owner attributes, and onboarding
cost from capacity and complexity. Neither reflects real negotiation. The model
therefore ranks on gross platform contribution, not margin.

**With real data.** Real contract terms allow contribution *after* onboarding
cost, revenue share and servicing cost — which is the number a CFO would ask
for. Payback period per lot becomes computable, and that is arguably a better
ranking variable than monthly contribution because it internalises acquisition
cost rather than treating it as a feasibility penalty.

### 7. Actual acquisition outcomes validate the model itself

**Today.** There is no outcome validation whatsoever. Nobody has verified that
high-scoring lots perform better, because none of the 120 have been approached.
Every claim in the project is about internal consistency — monotonicity,
reconciliation, sensitivity — and none is about predictive accuracy.

**With real data.** The test is straightforward and the project is structured to
support it: compare conversion rate and time-to-signature for lots the model
scored high against lots it scored low. If the ranking has predictive content,
the weights are earning their place. If it does not, they are wrong and the
sooner that is known the better. This is the improvement that would turn the
project from a defensible framework into a validated one.

---

## Improvements that do not need real data

Recorded honestly as things a reviewer could reasonably ask for. None was
implemented because none changes a conclusion.

**Holiday and festival calendar.** The daily generator has weekday/weekend and
seasonal variation but no festival effects, which are large in Delhi retail
parking. Not implemented because asserting festival dates from memory would put
invented facts into the dataset — an incomplete calendar was preferable to a
wrong one. A sourced public calendar would fix it properly.

**Locality sample depth.** 17 localities carry between 3 and 11 lots each. That
is thin for locality-level means, which is why locality analysis reports
opportunity counts and whitespace rather than treating a 3-lot average as
reliable. Widening the bounding box or lowering the capacity floor would deepen
the thin markets.

**Weight sensitivity breadth.** Four alternative weightings were tested against
the base case. That is four points in a five-dimensional simplex. A systematic
sweep — random Dirichlet draws over the weight space, reporting the share of
draws in which each lot stays in the top 10 — would give a much stronger
robustness statement than four hand-picked scenarios. This is the most valuable
item on this list and it needs no new data.

**Routing distance.** Replacing haversine with road or walking distance from a
routing engine would improve the metro-access and competitor-distance
components. It brings a service dependency, which is why it was declined.

**Two-wheelers.** Out of scope throughout, and a real omission in the Indian
market — two-wheeler parking is a large share of demand and has different
economics entirely. Including it would mean a second capacity dimension and a
second tariff structure across the whole model.

**Undocumented analysis needs a home.** The audit found substantial working
analysis with no entry in the business-question catalogue: peer benchmarking and
rank-explanation views, network strategy classification, multivariate outlier
review, and the entire model-validation layer. Either document these as
first-class questions or accept them as internal tooling — but they should not
sit in the repository unlabelled.

**Two business questions have no implementation.** Q11, ranking operators by
acquisition ease at owner grain, and Q16, comparing the model ranking against a
naive capacity proxy to expose false positives. Q16 in particular is the more
interesting of the two, because "lots a simple heuristic would have chosen and
the model rejects" is exactly the output that demonstrates the model earns its
complexity.

---

## Explicitly out of scope

Recorded so that "why didn't you..." has an answer rather than a shrug.

**Price recommendation.** The tariff data is present and the temptation is
obvious. With no elasticity data, recommending a price change would be
irresponsible — the project analyses price only as competitive context and says
so. This would need a pricing experiment, not a model.

**Demand forecasting.** A time series exists, so forecasting looks available.
Forecasting a synthetic series predicts the generator. With real history a
seasonal forecast would be reasonable, but it answers a different question from
acquisition prioritisation.

**A second front end.** A Streamlit simulator was built and then deliberately
retired. Two surfaces that each compute scores are two sources of truth. Power BI
consumes the analytical layer rather than recomputing it, and a regression test
asserts the app stays gone. Rebuilding it would undo a deliberate decision.

**Geospatial libraries.** Distance work is haversine between point pairs, about
fifteen lines of numpy. GeoPandas and Shapely bring GEOS and PROJ for no gain
here. Recorded in the requirements file alongside seven other declined
dependencies.

---

## Deliberately not doing

The project is complete. Further work would add volume, not correctness. The
tests that matter are in place, the numbers reconcile across SQL, Python and the
dashboard, and the limitations are documented where a reader will actually see
them rather than in an appendix.

Anything identified from here belongs in this file.
