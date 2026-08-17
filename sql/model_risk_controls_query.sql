WITH selected_run AS (
    SELECT run_id
    FROM assessment_runs
    ORDER BY as_at_date DESC, run_id DESC
    LIMIT 1
)
SELECT
    dr.run_id,
    dr.dimension_code,
    dr.dimension_name,
    dr.weight,
    dr.score AS dimension_score,
    dr.dimension_status,
    dr.review_required AS dimension_review_required,

    obr.obligation_id,
    obr.obligation_status,
    obr.review_required AS obligation_review_required,
    obr.reason AS obligation_reason,

    ee.assessment_unit_id,
    ee.digest AS evaluation_digest,
    ee.reconciliation_type,
    ee.date_state,
    ee.status_state,
    ee.type_matches,
    ee.qualifies_for_met,
    ee.supports_partial,
    ee.decision_basis,
    ee.review_required AS evaluation_review_required,

    eo.observation_id,
    eo.source_dataset,
    eo.origin_system,
    eo.source_record_id,
    eo.claimed_obligation_id,
    eo.evidence_type,
    eo.title,
    eo.event_date,
    eo.date_basis,
    eo.raw_status,
    eo.normalized_status,
    eo.version,
    eo.digest AS observation_digest,

    dqi.issue_type,
    dqi.severity,
    dqi.field_name,
    dqi.message AS issue_message,
    dqi.assessment_action
FROM selected_run AS sr
JOIN dimension_results AS dr
    ON dr.run_id = sr.run_id
    AND dr.dimension_code = 'MRC'
JOIN obligation_results AS obr
    ON obr.run_id = dr.run_id
    AND obr.dimension_code = dr.dimension_code
LEFT JOIN evidence_evaluations AS ee
    ON ee.run_id = obr.run_id
    AND ee.obligation_id = obr.obligation_id
LEFT JOIN evaluation_observations AS evobs
    ON evobs.run_id = ee.run_id
    AND evobs.obligation_id = ee.obligation_id
    AND evobs.assessment_unit_id = ee.assessment_unit_id
LEFT JOIN evidence_observations AS eo
    ON eo.observation_id = evobs.observation_id
LEFT JOIN data_quality_issues AS dqi
    ON dqi.run_id = dr.run_id
    AND dqi.observation_id = eo.observation_id
ORDER BY
    obr.obligation_id,
    ee.assessment_unit_id,
    eo.source_dataset,
    eo.observation_id,
    dqi.issue_type;
