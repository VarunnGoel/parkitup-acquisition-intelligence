-- =====================================================================
-- 01_seed_reference.sql : configuration and factual reference data
--
-- SCOPE NOTE. This seeds only data that is either factual public record
-- (cities), deterministic (the calendar), or project configuration (funnel
-- stages, scoring pillars, weights, segment rules). It seeds NO simulated
-- observations. Localities, lots, owners, performance and pipeline rows are
-- source's responsibility.
-- =====================================================================
SET search_path TO parkitup, public;

-- ---------------------------------------------------------------------
-- dim_city : factual public record for the Delhi NCR study area
-- ---------------------------------------------------------------------
INSERT INTO dim_city (city_id, city_name, state_name, ncr_zone, is_core_delhi) VALUES
    (1, 'New Delhi',  'Delhi',        'Central NCR', TRUE),
    (2, 'Gurugram',   'Haryana',      'South NCR',   FALSE),
    (3, 'Noida',      'Uttar Pradesh','East NCR',    FALSE),
    (4, 'Ghaziabad',  'Uttar Pradesh','North NCR',   FALSE),
    (5, 'Faridabad',  'Haryana',      'South NCR',   FALSE)
ON CONFLICT (city_id) DO NOTHING;

-- ---------------------------------------------------------------------
-- dim_funnel_stage : the BD funnel ladder
-- Ordered 1..7. Loss reasons are NOT stages (see outreach.lost_reason).
-- ---------------------------------------------------------------------
INSERT INTO dim_funnel_stage
    (stage_id, stage_code, stage_name, stage_order, is_success_stage, stage_description) VALUES
    (1, 'IDENTIFIED',    'Identified',      1, FALSE,
        'Lot located and logged as a prospect. No contact attempted yet.'),
    (2, 'CONTACTED',     'Contacted',       2, FALSE,
        'Owner or site manager reached at least once.'),
    (3, 'MEETING_DONE',  'Meeting Held',    3, FALSE,
        'Substantive discussion completed with someone able to describe the site commercially.'),
    (4, 'PROPOSAL_SENT', 'Proposal Sent',   4, FALSE,
        'Commercial terms including commission rate formally presented.'),
    (5, 'NEGOTIATION',   'In Negotiation',  5, FALSE,
        'Owner engaged on terms; commission, exclusivity or capex under discussion.'),
    (6, 'DOCS_COLLECTED','Documents Collected', 6, FALSE,
        'Ownership proof, trade licence and bank details received.'),
    (7, 'ONBOARDED',     'Onboarded',       7, TRUE,
        'Agreement signed and lot live on the platform.')
ON CONFLICT (stage_id) DO NOTHING;

-- ---------------------------------------------------------------------
-- dim_score_dimension : the five pillars
-- ---------------------------------------------------------------------
INSERT INTO dim_score_dimension
    (dimension_code, dimension_name, pillar_group, display_order, description) VALUES
    ('DEMAND',        'Demand Potential',       'Attractiveness', 1,
        'Latent parking demand around the lot, evidenced by surrounding land '
        'use, transit proximity, POI density and observed occupancy pressure.'),
    ('REVENUE',       'Revenue Potential',      'Attractiveness', 2,
        'Expected economic value to the platform: capacity multiplied by '
        'achievable utilisation, price point and commission rate.'),
    ('COMPETITION',   'Competition Opportunity','Attractiveness', 3,
        'Attractiveness of the local supply picture. Scores HIGH where demand '
        'exists but competing or already-digitised supply is thin.'),
    ('STRATEGIC_FIT', 'Strategic Fit',          'Attractiveness', 4,
        'Contribution to network strategy: fills a coverage gap, extends a '
        'cluster, or sits in a priority micro-market without cannibalising '
        'the existing footprint.'),
    ('FEASIBILITY',   'Acquisition Feasibility','Feasibility',    5,
        'Realistic probability of closing: owner willingness, digital '
        'readiness, documentation, contract flexibility, onboarding cost and '
        'operational complexity.')
ON CONFLICT (dimension_code) DO NOTHING;

-- ---------------------------------------------------------------------
-- scoring_weight_set : baseline plus three sensitivity scenarios
-- ---------------------------------------------------------------------
INSERT INTO scoring_weight_set (weight_set_id, weight_set_code, description, is_default) VALUES
    (1, 'BASELINE_V1',     'Initial business judgement. Demand-led, with '
                           'revenue close behind and the remaining three '
                           'pillars balanced. The set all headline results use.', TRUE),
    (2, 'EQUAL_WEIGHT',    'All five pillars at 0.20. An analytical control, '
                           'not a proposal: if the ranking barely moves '
                           'between this and BASELINE_V1, the elaborate '
                           'weighting is not earning its keep and should be '
                           'reported as such.', FALSE),
    (3, 'DEMAND_LED',      'Stress test biased toward locations. Answers '
                           '"what if we chase footfall and accept harder '
                           'negotiations?"', FALSE),
    (4, 'FEASIBILITY_LED', 'Stress test biased toward closeability. Answers '
                           '"what if the constraint is BD bandwidth rather '
                           'than market quality?"', FALSE),
    (5, 'REVENUE_LED',    'Stress test biased toward platform economics. '
                           'Answers "what if monetisation is the binding '
                           'constraint?"', FALSE)
ON CONFLICT (weight_set_id) DO NOTHING;

-- ---------------------------------------------------------------------
-- scoring_weight : weights per set. Each set must sum to 1.0 (rule DQ-020).
-- ---------------------------------------------------------------------
INSERT INTO scoring_weight (weight_set_id, dimension_code, weight) VALUES
    -- BASELINE_V1 : 30 / 25 / 15 / 15 / 15
    (1, 'DEMAND',        0.3000),
    (1, 'REVENUE',       0.2500),
    (1, 'COMPETITION',   0.1500),
    (1, 'STRATEGIC_FIT', 0.1500),
    (1, 'FEASIBILITY',   0.1500),
    -- EQUAL_WEIGHT : control
    (2, 'DEMAND',        0.2000),
    (2, 'REVENUE',       0.2000),
    (2, 'COMPETITION',   0.2000),
    (2, 'STRATEGIC_FIT', 0.2000),
    (2, 'FEASIBILITY',   0.2000),
    -- DEMAND_LED
    (3, 'DEMAND',        0.4000),
    (3, 'REVENUE',       0.2500),
    (3, 'COMPETITION',   0.1000),
    (3, 'STRATEGIC_FIT', 0.1000),
    (3, 'FEASIBILITY',   0.1500),
    -- FEASIBILITY_LED
    (4, 'DEMAND',        0.2000),
    (4, 'REVENUE',       0.2000),
    (4, 'COMPETITION',   0.1000),
    (4, 'STRATEGIC_FIT', 0.1000),
    (4, 'FEASIBILITY',   0.4000),
    -- REVENUE_LED : 20 / 40 / 15 / 10 / 15
    (5, 'DEMAND',        0.2000),
    (5, 'REVENUE',       0.4000),
    (5, 'COMPETITION',   0.1500),
    (5, 'STRATEGIC_FIT', 0.1000),
    (5, 'FEASIBILITY',   0.1500)
ON CONFLICT (weight_set_id, dimension_code) DO NOTHING;

-- ---------------------------------------------------------------------
-- segment_rule : the decision table
--
-- THRESHOLD STATUS: PROVISIONAL. The numbers below are placeholders chosen to
-- be structurally sensible, not empirically calibrated - no scores exist yet.
-- the scoring engine must re-set them from the observed score distribution (the intent
-- is roughly the top third on attractiveness and above-median on
-- feasibility) and record the calibration in the methodology document.
-- Recorded as assumption A-14.
-- ---------------------------------------------------------------------
INSERT INTO segment_rule
    (segment_code, segment_label, eval_priority,
     min_attractiveness, min_feasibility, max_feasibility, bd_action, rationale) VALUES
    ('ACQUIRE_NOW', 'Acquire Now', 1, 65.00, 60.00, NULL,
        'Assign a named owner this week and open commercial discussions.',
        'Attractive market AND a closeable counterparty. Delay here costs '
        'real option value because these are exactly the lots a competitor '
        'would also want.'),
    ('PURSUE',      'Pursue',      2, 65.00, NULL,  60.00,
        'Work the constraint before the commercials: identify the decision '
        'maker, test a pilot or revisit exclusivity.',
        'The market case is strong but something about the counterparty '
        'blocks a quick close. Worth senior effort, not junior volume.'),
    ('DEVELOP',     'Develop',     3, 45.00, 60.00, NULL,
        'Batch into low-cost outreach. Good practice ground for junior reps.',
        'Only moderately attractive, but cheap and quick to sign. Useful for '
        'building network density and coverage credibility.'),
    ('AVOID',       'Avoid',       4, NULL,  NULL,  NULL,
        'No outreach. Re-evaluate only if the surrounding market changes.',
        'Catch-all with no bounds, so every lot receives a segment. Either '
        'the economics do not work or the lot cannot realistically be won.')
ON CONFLICT (segment_code) DO NOTHING;
