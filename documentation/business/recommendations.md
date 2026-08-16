# Business Recommendations

Recommendations supported by the analysis, and nothing beyond it.

**Read this first.** The operational and commercial layer of this dataset is
modelled, not observed. So there are two kinds of statement below and they are
labelled throughout:

- **Supported** — follows from the analysis and would hold for any dataset with
  this structure. These are recommendations about *process and allocation*.
- **Illustrative** — the pattern is real in this dataset but the dataset is
  synthetic, so it demonstrates what the analysis would say rather than making a
  claim about Delhi parking.

Nothing here is a claim about real PARK It Up performance.

---

## The BD manager's test

The question I held the whole project against: *if I had 20 BD calls available
this month, would this help me decide who to call?*

Yes, and specifically in three ways. It cuts 120 candidates to 25 worth active
capacity. It tells me those 25 are geographically concentrated, so a rep can see
several in a day rather than crossing the NCR. And it names a specific blocker
for the 15 lots that are commercially attractive but hard to close, so the first
conversation can be aimed at the blocker rather than at the commercials.

What it does not do is decide anything. Which brings us to the boundary.

### Prioritisation is not an acquisition decision

| The model does | The model does not |
|---|---|
| Rank candidates by relative attractiveness | Value a lot |
| Separate attractive from closeable | Predict whether an owner will sign |
| Name the constraint to resolve first | Negotiate terms |
| Allocate scarce BD attention across markets | Verify ownership or title |
| Flag when a ranking is assumption-sensitive | Inspect the site |
| — | Assess legal, structural or permit risk |
| — | Perform financial diligence |

This distinction is the reason the output is a *queue*, not an answer. A model
that claimed the second column would be wrong and would be caught being wrong the
first time a rep visited a site.

---

## Market recommendations

**Supported: concentrate, do not spread.** All 25 priority targets sit in six of
the 17 micro-markets, and 22 of them in only four. That is the strongest
structural finding in the analysis and it is a resource-allocation conclusion, not
a claim about any particular locality. When opportunity is that concentrated,
spreading a small BD team across 17 markets is strictly worse than saturating a
handful.

**Supported: treat market entry and market deepening as different decisions.**
Localities where the platform already has a live site need a *deepening* play —
add adjacent lots, watch for cannibalisation inside 400 m. Localities with no
live site need an *entry* play, which is a different conversation and a different
cost. The Strategic Fit pillar penalises lots within 400 m of an existing live
site and rewards roughly 1.5-6 km spacing, so the model already separates these.

**Illustrative: where the opportunity concentrates in this dataset.**

| Locality | Market type | Candidates | Priority targets | Avg score | Whitespace |
|---|---|---|---|---|---|
| Nehru Place | Commercial | 11 | 9 | 65.7 | 93.8 |
| Connaught Place | CBD | 11 | 7 | 63.4 | 100.0 |
| Karol Bagh | Retail high street | 10 | 4 | 56.4 | 71.1 |
| Lajpat Nagar | Retail high street | 6 | 2 | 56.4 | 54.9 |
| Golf Course Road | Commercial | 5 | 2 | 48.6 | 15.5 |
| Noida Sector 62 | IT/office park | 4 | 1 | 43.4 | 11.6 |

Two things are worth reading off this table as *method*, not as fact. Nehru Place
and Connaught Place both score near-maximum whitespace with only one live site
each — that is what "high demand, thin platform coverage" looks like when the
metric works. And Golf Course Road reaches two priority targets on low demand
(26.1 average) and low whitespace, carried instead by weak competition and strong
owner readiness. That is the model behaving as designed: an easy-to-sign lot in a
quiet market can still deserve attention, and it will be a different conversation
from a Nehru Place lot.

**Supported: eleven of the seventeen localities produced zero priority targets.**
The useful action there is to stop spending attention, and to record what would
have to change for them to re-enter consideration — which is what the Avoid
segment's action note says. A market with no targets is a finding, not a gap in
the analysis.

---

## Parking-level recommendations

**Supported: work the four segments differently.** This is the core operating
recommendation and it follows directly from holding feasibility on its own axis.

| Segment | Lots | What it means | BD action |
|---|---|---|---|
| Acquire Now | 25 | Attractive and closeable | Named-owner outreach this month; commercial diligence |
| Pursue | 15 | Attractive, hard to close | Senior BD resolves the named constraint before any commercial conversation |
| Develop | 21 | Moderate but easy | Batched low-cost outreach; good ground for junior reps |
| Avoid | 59 | Neither | No active capacity; revisit only if the market or owner posture changes |

The Pursue segment is the part that earns the model its keep. Those 15 lots would
be indistinguishable from Acquire Now on a single composite ranking, and
approaching them with a standard commercial pitch would waste the meeting. They
need the blocker cleared first — and the reason codes say which blocker.

**Supported: sequence by cluster, not strictly by rank.** The top 10 spans four
localities. A rep working Nehru Place can cover several targets in a day. Strict
rank order would have them criss-crossing the NCR for a difference of two score
points that the sensitivity analysis says is not meaningful anyway.

**Supported: trust the shortlist, not the ordering below it.** 8 of 120 lots hold
top-10 rank in every primary scenario and 2 mostly hold. The other 110 do not.
Any recommendation that depends on lot #47 outranking lot #52 is unsupportable,
and the dashboard says so on the page rather than in a footnote.

**Illustrative: the top six and what drives each.**

| # | Lot | Locality | Score | Driver | Constraint |
|---|---|---|---|---|---|
| 1 | MCD Parking | Lajpat Nagar | 78.3 | Strong on four pillars simultaneously | Competitor price pressure |
| 2 | Office Complex · Nehru Place #18 | Nehru Place | 76.4 | Maximum revenue potential, high demand | High onboarding cost; decision maker blocked |
| 3 | Basement · Connaught Place #1 | Connaught Place | 75.6 | Highest demand in the portfolio | Dense competition |
| 4 | Office Complex · Nehru Place #17 | Nehru Place | 73.7 | Strong revenue with the best feasibility in the top five | None recorded |
| 5 | Basement · Connaught Place #6 | Connaught Place | 73.7 | Maximum revenue, strong demand | Competition and price pressure |
| 6 | Surface Lot · Lajpat Nagar #51 | Lajpat Nagar | 73.0 | Best competition and feasibility combination | Capex required |

Note that rank 6 gets there with a mid-range revenue score of 45.8 — the lowest in
the top ten. It is not a revenue story; it is a competitive-whitespace and
closeability story. Reading only the composite would hide that, which is why the
deep-dive page decomposes it.

---

## BD process recommendations

**Supported: qualify the decision maker before investing in a meeting.** The
largest single loss reason in the pipeline is "owner not decision maker" — 23 of
64 losses, more than a third. That is a *process* finding: it is about how
outreach is sequenced, not about which owner type is best. A five-minute
qualifying question ahead of a site visit addresses the single biggest leak.

**Supported: the funnel's worst stage is the last one.** Conversion holds between
66% and 78% at every stage until documentation-collected to onboarded, where it
drops to 52%. Late-stage loss is the most expensive kind — full BD cost incurred,
no signature. Whatever happens between documents and onboarding deserves
attention before top-of-funnel volume does.

| Stage | Leads | Conversion from prior |
|---|---|---|
| Identified | 120 | — |
| Contacted | 94 | 78.3% |
| Meeting done | 63 | 67.0% |
| Proposal sent | 42 | 66.7% |
| Negotiation | 31 | 73.8% |
| Documents collected | 23 | 74.2% |
| Onboarded | 12 | 52.2% |

**Supported: commission objections are a pricing-policy problem, not a rep
problem.** "Commission too low" accounts for 18 of 64 losses, second only to
decision-maker access. Eighteen separate reps failing the same way is a signal
about the standard offer, not about execution. The right response is to test a
commission band, which is a policy decision the model cannot make.

**Illustrative: operator-type prioritisation.** In this dataset, mall management
(67.6 mean feasibility) and private companies (65.6) score highest, while
government and municipal owners score lowest at 38.2 — driven by decision-maker
access and contract flexibility. Owner posture is synthetic, so treat this as
*the shape of the question* rather than as guidance. It matters commercially
because government and municipal owners hold 24 of the 120 lots, so a fifth of
the candidate universe sits behind the hardest access problem. The defensible
version is the process recommendation above: qualify access first, regardless of
owner type.

**Illustrative: conversion by priority segment.** Acquire Now converts at 24%
against 5% for Avoid in the synthetic funnel. This does not validate the model —
the relationship is built into the generator. It is included because it shows the
*measurement design* that real outreach data would use, and that comparison is
the first thing to run once real outcomes exist.

---

## Operational recommendations — what to collect

Ordered by how much it would improve the model per unit of effort to collect.
Full detail in `future_improvements.md`.

1. **Outcome per approach, with the refusal reason.** Cheapest to collect,
   highest value. It is the only thing that can validate whether the ranking has
   predictive content, and it is the missing target variable that would let
   feasibility become an estimated probability instead of an assumed index.
2. **Whether owner attributes were verified or assumed at contact.** Without
   this, a future model would learn from attributes recorded after the outcome
   was known — a leakage trap that would produce impressive and worthless
   accuracy.
3. **Observed occupancy for signed lots.** Replaces the heaviest and most
   assumption-laden input in the model.
4. **Unserved search demand by area from the app.** Measures whitespace by
   observed demand rather than by absence of supply, which is a fundamentally
   better signal than the current proxy.
5. **Real contract terms including servicing cost.** Enables ranking by payback
   period rather than gross contribution, which internalises acquisition cost
   instead of treating it as a feasibility penalty.
6. **Competitor capacity, even approximately.** The one gap that currently makes
   a documented business question unanswerable: strong-demand, weak-supply
   localities cannot be identified in capacity terms, only in count terms.

---

## Model recommendations

**With real data, in order.** Validate first — compare conversion for high-scored
against low-scored lots. If the ranking has no predictive content, the weights are
wrong and everything else is premature. Then replace the demand proxy with
observed occupancy. Then convert feasibility to a fitted probability of signing,
which is the one place a model genuinely belongs.

**Without real data, the single best improvement** is a systematic weight sweep.
Four alternative weightings were tested; that is four points in a
five-dimensional simplex. Random draws over the weight space, reporting the share
of draws in which each lot stays in the top 10, would replace "the shortlist
survived four scenarios" with a much stronger statement — and it needs no new
data.

**What not to add.** Price recommendations without elasticity data. Demand
forecasting on a synthetic series, which forecasts the generator. A second front
end, which would create a second source of truth. Each is recorded with its
reasoning in `future_improvements.md`.
