-- Locality whitespace and network-density versus expansion decisions.
SET search_path TO parkitup, public;
SELECT * FROM vw_locality_summary ORDER BY whitespace_rank;

SELECT t.parking_id, t.parking_name, t.locality, t.acquisition_score,
       p.nearest_live_network_distance_km,
       CASE WHEN p.live_network_site_count > 0 AND p.nearest_live_network_distance_km BETWEEN 0.4 AND 6
              THEN 'STRENGTHEN_CLUSTER'
            WHEN p.live_network_site_count = 0 THEN 'OPEN_NEW_MARKET'
            WHEN p.nearest_live_network_distance_km < 0.4 THEN 'NETWORK_REDUNDANCY_RISK'
            ELSE 'REMOTE_EXPANSION' END AS network_strategy
FROM vw_bd_acquisition_targets t JOIN parking_acquisition_score p USING (parking_id)
WHERE t.priority_segment IN ('ACQUIRE_NOW','PURSUE')
ORDER BY t.rank;
