# SQL Analytics Findings

## Scope and provenance

The layer was executed against PostgreSQL 17.5 database `parkitup`: 120 candidate lots, 17 localities, 43,800 daily facts, 5,760 hourly profiles, 120 synthetic leads, and 1,920 scenario score rows. Results involving operations, outreach, commercial terms, or network presence are synthetic demonstrations, not claims about PARK It Up.

## Actual findings

- Overall synthetic lead-to-onboarded conversion is 10.00% (12 of 120).
- Stage reach is 120 identified, 94 contacted, 63 meetings, 42 proposals, 31 negotiations, 23 document collections, and 12 onboarded.
- The largest proportional funnel drop is Documents Collected to Onboarded: 47.83% (11 of 23). The largest absolute pre-final loss is Contacted to Meeting Held: 31 leads.
- Partner Network leads convert best in this sample at 25.00% (3 of 12); Field Survey is lowest at 4.76% (1 of 21).
- Private Company is the only owner type with synthetic wins: 12 of 64 leads (18.75%). This concentration is a generator limitation, not causal evidence.
- Connaught Place, Nehru Place, and Karol Bagh lead the independent whitespace score at 67.94, 66.35, and 62.69. Lajpat Nagar ranks fourth at 49.73 and has zero hypothetical live-network coverage.
- The top acquisition target is parking 52, MCD Parking in Lajpat Nagar: acquisition score 78.53, demand 81.91, feasibility 74.73, expected monthly platform revenue INR 181,556.39, and 100% top-10 scenario stability.
- The top ten contain four Connaught Place lots, three Nehru Place lots, two Lajpat Nagar lots, and one Karol Bagh lot.

## Known limitations

- The schema has no explicit Interested funnel stage. `owner_interest_level >= 3` is reported separately as a proxy.
- Competitor capacity is missing for all candidates, so locality competitor capacity remains null and competition analysis uses count/distance/price proxies, consistent with scoring.
- Existing network sites and all BD outcomes are synthetic.
- Scores and percentile thresholds are relative to this controlled 120-lot universe.
