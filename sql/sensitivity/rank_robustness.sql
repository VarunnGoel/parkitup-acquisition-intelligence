-- Rank robustness across scoring scenarios; LAG/LEAD expose adjacent scenario shifts.
SET search_path TO parkitup, public;
WITH scenario_ranks AS (
 SELECT l.parking_id, a.scenario_code, a.scenario_id, l.rank_overall,
        LAG(l.rank_overall) OVER (PARTITION BY l.parking_id ORDER BY a.scenario_id) AS prior_scenario_rank,
        LEAD(l.rank_overall) OVER (PARTITION BY l.parking_id ORDER BY a.scenario_id) AS next_scenario_rank
 FROM lot_scenario_score l JOIN acquisition_scenario a USING (scenario_id)
)
SELECT r.*, r.rank_overall - r.prior_scenario_rank AS change_from_prior,
       r.next_scenario_rank - r.rank_overall AS change_to_next
FROM scenario_ranks r WHERE r.parking_id IN
 (SELECT parking_id FROM vw_bd_acquisition_targets ORDER BY rank LIMIT 20)
ORDER BY parking_id, scenario_id;
