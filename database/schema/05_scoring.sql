-- =====================================================================
-- 05_scoring.sql : scoring configuration and results
-- Depends on: 01_reference.sql, 02_core_entities.sql
--
-- CENTRAL DESIGN DECISION
-- Weights and segment thresholds are stored as DATA, not written into SQL or
-- Python. Two consequences that matter:
--   1. Sensitivity analysis (business questions 9 and 10) becomes a matter of
--      inserting another weight set and re-running, not editing code.
--   2. Every published score is traceable to the exact weight set that
--      produced it, because weight_set_id is part of the results primary key.
-- scoring implements the calculation. this schema only fixes the contract.
-- =====================================================================
SET search_path TO parkitup, public;

-- ---------------------------------------------------------------------
-- scoring_weight_set : a named, versioned weighting scenario
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scoring_weight_set (
    weight_set_id   SMALLINT     PRIMARY KEY,
    weight_set_code TEXT         NOT NULL UNIQUE,
    description     TEXT         NOT NULL,
    is_default      BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Partial unique index: at most one weight set may be flagged default.
CREATE UNIQUE INDEX IF NOT EXISTS uq_scoring_weight_set_single_default
    ON scoring_weight_set (is_default) WHERE is_default;

COMMENT ON TABLE scoring_weight_set IS
  'PROVENANCE: config. Named weighting scenarios. The baseline set encodes the '
  'initial business judgement; the alternates exist to test how fragile the '
  'recommendations are to that judgement.';
COMMENT ON INDEX uq_scoring_weight_set_single_default IS
  'Guarantees exactly one default scenario, so reports cannot silently pick '
  'a different weighting than intended.';

-- ---------------------------------------------------------------------
-- scoring_weight : the weight of each pillar within a weight set
--
-- NOTE ON A CONSTRAINT THAT CANNOT BE A CHECK: weights within a set must sum
-- to 1.0. That is a cross-row invariant, and PostgreSQL CHECK constraints are
-- row-scoped. Rather than reach for a trigger (which hides logic from the
-- reader), this is enforced as data-quality rule DQ-020 in
-- sql/data_quality/dq_checks.sql, which fails loudly if any set is malformed.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scoring_weight (
    weight_set_id  SMALLINT      NOT NULL
                   REFERENCES scoring_weight_set (weight_set_id) ON DELETE CASCADE,
    dimension_code TEXT          NOT NULL
                   REFERENCES dim_score_dimension (dimension_code),
    weight         NUMERIC(5,4)  NOT NULL
                   CHECK (weight >= 0 AND weight <= 1),
    CONSTRAINT pk_scoring_weight PRIMARY KEY (weight_set_id, dimension_code)
);

COMMENT ON TABLE scoring_weight IS
  'PROVENANCE: config. One row per pillar per weight set. Weights within a '
  'set must sum to 1.0 - enforced by data-quality rule DQ-020, not by a '
  'CHECK constraint, because the invariant spans rows.';

-- ---------------------------------------------------------------------
-- segment_rule : the ACQUIRE NOW / PURSUE / DEVELOP / AVOID decision table
--
-- Thresholds live here so they are visible, versionable and arguable rather
-- than buried in a CASE statement. Bounds are inclusive lower / exclusive
-- upper. Rules are evaluated in priority order and the first match wins, so
-- the rule set is total and unambiguous by construction.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS segment_rule (
    segment_code       TEXT      PRIMARY KEY
                       CHECK (segment_code IN ('ACQUIRE_NOW','PURSUE','DEVELOP','AVOID')),
    segment_label      TEXT      NOT NULL UNIQUE,
    eval_priority      SMALLINT  NOT NULL UNIQUE CHECK (eval_priority >= 1),
    min_attractiveness NUMERIC(5,2)
                       CHECK (min_attractiveness IS NULL
                              OR min_attractiveness BETWEEN 0 AND 100),
    min_feasibility    NUMERIC(5,2)
                       CHECK (min_feasibility IS NULL
                              OR min_feasibility BETWEEN 0 AND 100),
    max_feasibility    NUMERIC(5,2)
                       CHECK (max_feasibility IS NULL
                              OR max_feasibility BETWEEN 0 AND 100),
    bd_action          TEXT      NOT NULL,
    rationale          TEXT      NOT NULL,
    CONSTRAINT ck_segment_feasibility_band
        CHECK (min_feasibility IS NULL OR max_feasibility IS NULL
               OR min_feasibility < max_feasibility)
);

COMMENT ON TABLE segment_rule IS
  'PROVENANCE: config. Decision table mapping (attractiveness, feasibility) to '
  'a BD action. Evaluated in eval_priority order, first match wins; the '
  'lowest-priority rule is the catch-all so every lot receives a segment.';
COMMENT ON COLUMN segment_rule.bd_action IS
  'The concrete instruction handed to the BD team. A segment that does not '
  'change what somebody does on Monday morning is not worth computing.';

-- ---------------------------------------------------------------------
-- lot_dimension_score : the explainability layer, and the source of truth
-- GRAIN: one row per lot per weight set per pillar.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lot_dimension_score (
    parking_id            INT           NOT NULL
                          REFERENCES parking_lots (parking_id) ON DELETE CASCADE,
    weight_set_id         SMALLINT      NOT NULL
                          REFERENCES scoring_weight_set (weight_set_id) ON DELETE CASCADE,
    dimension_code        TEXT          NOT NULL
                          REFERENCES dim_score_dimension (dimension_code),
    subscore              NUMERIC(5,2)  NOT NULL
                          CHECK (subscore BETWEEN 0 AND 100),
    weight_applied        NUMERIC(5,4)  NOT NULL
                          CHECK (weight_applied BETWEEN 0 AND 1),
    weighted_contribution NUMERIC(6,3)  NOT NULL
                          CHECK (weighted_contribution >= 0),
    CONSTRAINT pk_lot_dimension_score
        PRIMARY KEY (parking_id, weight_set_id, dimension_code)
);

COMMENT ON TABLE lot_dimension_score IS
  'PROVENANCE: derived (scoring output). The audit trail behind every headline '
  'score: each pillar subscore on a 0-100 scale, the weight applied, and the '
  'resulting contribution. This table is what makes the model explainable - '
  'the deep-dive dashboard page reads directly from it.';
COMMENT ON COLUMN lot_dimension_score.weighted_contribution IS
  'subscore * weight_applied. Stored rather than recomputed so that a '
  'published score can be reconciled long after the code has moved on.';

-- ---------------------------------------------------------------------
-- lot_score : headline results, one row per lot per weight set
--
-- The five pillar subscores are NOT repeated here - they live in
-- lot_dimension_score. This table holds only the aggregates and the decision.
-- The aggregates are a deliberate, VERIFIED redundancy: DQ-021 reconciles
-- acquisition_score against SUM(weighted_contribution) within tolerance.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lot_score (
    parking_id           INT           NOT NULL
                         REFERENCES parking_lots (parking_id) ON DELETE CASCADE,
    weight_set_id        SMALLINT      NOT NULL
                         REFERENCES scoring_weight_set (weight_set_id) ON DELETE CASCADE,
    attractiveness_score NUMERIC(5,2)  NOT NULL
                         CHECK (attractiveness_score BETWEEN 0 AND 100),
    feasibility_score    NUMERIC(5,2)  NOT NULL
                         CHECK (feasibility_score BETWEEN 0 AND 100),
    acquisition_score    NUMERIC(5,2)  NOT NULL
                         CHECK (acquisition_score BETWEEN 0 AND 100),
    segment_code         TEXT          NOT NULL
                         REFERENCES segment_rule (segment_code),
    rank_overall         INT           CHECK (rank_overall IS NULL OR rank_overall >= 1),
    scored_at            TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT pk_lot_score PRIMARY KEY (parking_id, weight_set_id),
    CONSTRAINT uq_lot_score_rank UNIQUE (weight_set_id, rank_overall)
);

CREATE INDEX IF NOT EXISTS ix_lot_score_segment ON lot_score (weight_set_id, segment_code);

COMMENT ON TABLE lot_score IS
  'PROVENANCE: derived (scoring output). Headline result per lot per weighting '
  'scenario. weight_set_id in the primary key is what makes sensitivity '
  'analysis non-destructive: alternate scenarios coexist with the baseline '
  'instead of overwriting it.';
COMMENT ON COLUMN lot_score.attractiveness_score IS
  'Weighted blend of DEMAND, REVENUE, COMPETITION and STRATEGIC_FIT, '
  'renormalised to 0-100. The X axis of the Acquisition Matrix.';
COMMENT ON COLUMN lot_score.feasibility_score IS
  'The FEASIBILITY pillar on its own 0-100 scale. Kept separate from '
  'attractiveness because a lot that is wonderful and unobtainable requires a '
  'different BD response than one that is mediocre and easy - averaging the '
  'two into a single number would hide exactly the distinction the BD team '
  'needs. The Y axis of the Acquisition Matrix.';
COMMENT ON CONSTRAINT uq_lot_score_rank ON lot_score IS
  'Ranks must be unique within a weighting scenario - catches tie-handling '
  'bugs in the scoring engine ranking logic.';
