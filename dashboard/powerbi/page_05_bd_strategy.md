# Page 5 - BD Action Center

**Business question:** What should the BD team do next?

**Default state:** all 120 leads, all segments.

**Decision supported:** where the pipeline is losing lots, why, and which named
lots get worked this week.

## Layout

| Region | Grid | Contents |
| --- | --- | --- |
| KPI strip | cols 0-12, rows 0-3 | four funnel KPI cells |
| Primary | cols 0-6, rows 3-14 | where the pipeline leaks |
| Secondary | cols 6-12, rows 3-14 | why deals are lost |
| Supporting | cols 0-12, rows 14-24 | next actions |

## Visuals

1. **KPI strip** - leads worked, onboarded, lead-to-live conversion, and average
   cycle time for won leads. *Largest drop* was removed because the funnel now
   annotates every drop, and *Robust Top 10* was removed because persistence
   belongs to Page 3.
2. **Where the pipeline leaks** (primary) - the seven `AggBDFunnel` stages as
   horizontal bars against a faint full-cohort track, so remaining and lost are
   both visible. Each transition is annotated with the absolute and percentage
   drop, and the worst step is bolded in negative red. The bars themselves stay
   one colour: red on the `Onboarded` bar would read as onboarding being bad.
3. **Why deals are lost** (secondary) - `lost_reason` counts across the 64
   closed-lost leads, the two leading reasons in negative red and the rest
   neutral. This replaced *Acquisition Rate by Lead Source*, which split 120 leads
   into seven subsamples of 9 to 29 and which the validation findings already caveat
   as generator-shaped. Loss reasons use the full closed-lost population and point
   at something the team can change: 64% of losses are owner authority or
   commission terms, both testable before a lot enters the pipeline.
4. **Next actions** - the highest-scoring lots from three segments, five
   `ACQUIRE_NOW`, two `PURSUE`, one `DEVELOP`. Columns: segment, lot, locality,
   score, feasibility, modelled monthly revenue, top-10 persistence, next action,
   blocker on record.

   The dashboard page carried two tables listing the same seven `ACQUIRE_NOW` lots,
   with an action column reading *Immediate outreach* on every row. Mixing
   segments makes the action column carry information, and pairing each `PURSUE`
   row with its recorded blocker states what has to be resolved first.

## Interactions

- Selecting a funnel stage filters the loss-reason chart and the action table to
  the leads that reached that stage.
- Selecting a loss reason filters the action table to lots whose owner or
  documentation attributes match.
- Selecting an action row enables drill-through to Page 4.
- `Next action` text is derived from `DimPrioritySegment.bd_action`, not invented
  per row.

## Acceptance checks

120 leads, 12 onboarded, 10.0% conversion, 55-day average cycle. Funnel
120 / 94 / 63 / 42 / 31 / 23 / 12, worst step `Onboarded` at 47.8%. 64 closed-lost
leads, led by *Owner Not Decision Maker* at 23 and *Commission Too Low* at 18,
together 41 of 64.
