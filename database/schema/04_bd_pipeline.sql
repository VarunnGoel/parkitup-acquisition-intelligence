-- =====================================================================
-- 04_bd_pipeline.sql : business development outreach and funnel
-- Depends on: 02_core_entities.sql, 01_reference.sql
-- =====================================================================
SET search_path TO parkitup, public;

-- ---------------------------------------------------------------------
-- outreach
-- One lead record per parking lot.
--
-- REMOVED from the proposed field list, with reasons:
--   contacted BOOLEAN     -> redundant, equals (contact_attempts > 0)
--   meeting_completed     -> a funnel stage, not an attribute
--   owner_interested      -> a funnel stage, not an attribute
--   partnership_status    -> replaced by furthest_stage_id + pipeline_status,
--                            which cannot contradict each other
--   days_to_conversion    -> now a GENERATED column, so it cannot drift
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outreach (
    lead_id             INT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- UNIQUE enforces the 1:1 business rule: one lead per lot.
    parking_id          INT       NOT NULL UNIQUE
                        REFERENCES parking_lots (parking_id) ON DELETE CASCADE,
    lead_source         TEXT      NOT NULL
                        CHECK (lead_source IN (
                            'Field Survey','Inbound Enquiry','Referral',
                            'Cold Call','Desk Research','Broker','Partner Network')),
    first_contact_date  DATE,
    contact_attempts    SMALLINT  NOT NULL DEFAULT 0
                        CHECK (contact_attempts >= 0 AND contact_attempts <= 50),
    furthest_stage_id   SMALLINT  NOT NULL
                        REFERENCES dim_funnel_stage (stage_id),
    pipeline_status     TEXT      NOT NULL
                        CHECK (pipeline_status IN ('Active','Won','Lost')),
    lost_reason         TEXT
                        CHECK (lost_reason IS NULL OR lost_reason IN (
                            'No Response','Commission Too Low','Wants Fixed Rent',
                            'Exclusivity Refused','Documentation Unavailable',
                            'Competitor Signed','Owner Not Decision Maker')),
    documents_available BOOLEAN   NOT NULL DEFAULT FALSE,
    owner_interest_level SMALLINT
                        CHECK (owner_interest_level IS NULL
                               OR owner_interest_level BETWEEN 1 AND 5),
    conversion_date     DATE,
    assigned_bd_rep     TEXT      NOT NULL,
    -- date - date yields INTEGER in PostgreSQL. Generated so the metric can
    -- never disagree with the dates it is derived from.
    days_to_conversion  INT       GENERATED ALWAYS AS
                        (conversion_date - first_contact_date) STORED,

    -- A lost lead must say why; a live or won lead must not carry a loss reason.
    CONSTRAINT ck_outreach_lost_reason_iff_lost CHECK (
        (pipeline_status =  'Lost' AND lost_reason IS NOT NULL)
     OR (pipeline_status <> 'Lost' AND lost_reason IS NULL)
    ),
    -- A won lead must have a conversion date; nothing else may have one.
    CONSTRAINT ck_outreach_conversion_date_iff_won CHECK (
        (pipeline_status =  'Won' AND conversion_date IS NOT NULL)
     OR (pipeline_status <> 'Won' AND conversion_date IS NULL)
    ),
    -- Contact attempts and a first contact date imply each other.
    CONSTRAINT ck_outreach_contact_consistent CHECK (
        (contact_attempts = 0 AND first_contact_date IS NULL)
     OR (contact_attempts > 0 AND first_contact_date IS NOT NULL)
    ),
    -- Time cannot run backwards.
    CONSTRAINT ck_outreach_conversion_after_contact CHECK (
        conversion_date IS NULL
     OR first_contact_date IS NULL
     OR conversion_date >= first_contact_date
    )
);

CREATE INDEX IF NOT EXISTS ix_outreach_status ON outreach (pipeline_status);
CREATE INDEX IF NOT EXISTS ix_outreach_stage  ON outreach (furthest_stage_id);

COMMENT ON TABLE outreach IS
  'PROVENANCE: synthetic. Simulated BD lead records. Contains no real PARK It '
  'Up pipeline data, no real contact details and no real operator names. '
  'Grain: one row per parking lot.';
COMMENT ON COLUMN outreach.furthest_stage_id IS
  'The deepest funnel stage this lead ever reached. Funnel drop-off (business '
  'question 12) is the distribution of this column across all leads.';
COMMENT ON COLUMN outreach.pipeline_status IS
  'Active = still in play. Won = onboarded. Lost = terminated, with a reason. '
  'Kept separate from furthest_stage_id because a lead can die at any stage, '
  'and encoding losses as stages would destroy the stage ordering.';
COMMENT ON COLUMN outreach.days_to_conversion IS
  'Generated column: conversion_date - first_contact_date, in days. NULL for '
  'any lead that has not converted. Basis of BD cycle-time analysis.';
COMMENT ON COLUMN outreach.assigned_bd_rep IS
  'Synthetic rep identifier (for example "BD-03"). Deliberately not a real '
  'person name.';

-- ---------------------------------------------------------------------
-- outreach_events
-- Stage-entry log. Small (one row per stage actually reached per lead) but it
-- is what makes stage-to-stage conversion rates and inter-stage cycle times
-- computable. Without it, only the final resting stage is knowable.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outreach_events (
    event_id     BIGINT    GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lead_id      INT       NOT NULL
                 REFERENCES outreach (lead_id) ON DELETE CASCADE,
    stage_id     SMALLINT  NOT NULL
                 REFERENCES dim_funnel_stage (stage_id),
    event_date   DATE      NOT NULL,
    channel      TEXT      NOT NULL
                 CHECK (channel IN ('Phone','In-Person','Email','WhatsApp','Video Call')),
    -- A lead enters any given stage at most once. Prevents duplicate stage
    -- rows from inflating funnel conversion denominators.
    CONSTRAINT uq_outreach_event_lead_stage UNIQUE (lead_id, stage_id)
);

CREATE INDEX IF NOT EXISTS ix_outreach_events_lead ON outreach_events (lead_id);

COMMENT ON TABLE outreach_events IS
  'PROVENANCE: synthetic. Log of funnel stage entries. Grain: one row per '
  'lead per stage reached. Enables stage-to-stage conversion and cycle time; '
  'business rule - the set of stages present for a lead must be contiguous '
  'from stage 1 up to outreach.furthest_stage_id (validated in the data '
  'quality layer, as it spans rows and cannot be a CHECK constraint).';
