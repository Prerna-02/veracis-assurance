PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assessment_runs (
    run_id TEXT PRIMARY KEY,
    methodology_version TEXT NOT NULL,
    obligation_set_version TEXT NOT NULL,
    as_at_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS obligations (
    obligation_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    clause_reference TEXT NOT NULL,
    dimension_code TEXT NOT NULL,
    requirement_text TEXT NOT NULL,
    required_evidence_types_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_observations (
    observation_id TEXT PRIMARY KEY,
    source_dataset TEXT NOT NULL,
    source_position INTEGER NOT NULL,
    origin_system TEXT NOT NULL,
    source_record_id TEXT,
    claimed_obligation_id TEXT,
    validated_obligation_id TEXT,
    evidence_type TEXT,
    title TEXT,
    event_date TEXT,
    date_basis TEXT NOT NULL,
    raw_date_value TEXT,
    raw_status TEXT,
    normalized_status TEXT NOT NULL,
    owner TEXT,
    version TEXT,
    digest TEXT,
    source_category TEXT,
    FOREIGN KEY (validated_obligation_id)
        REFERENCES obligations (obligation_id)
);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    run_id TEXT NOT NULL,
    issue_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    field_name TEXT,
    message TEXT NOT NULL,
    review_required INTEGER NOT NULL CHECK (review_required IN (0, 1)),
    assessment_action TEXT NOT NULL,
    PRIMARY KEY (run_id, issue_id),
    FOREIGN KEY (run_id)
        REFERENCES assessment_runs (run_id) ON DELETE CASCADE,
    FOREIGN KEY (observation_id)
        REFERENCES evidence_observations (observation_id)
);

CREATE TABLE IF NOT EXISTS reconciliation_groups (
    run_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    digest TEXT NOT NULL,
    group_type TEXT NOT NULL,
    review_required INTEGER NOT NULL CHECK (review_required IN (0, 1)),
    assessment_handling TEXT NOT NULL,
    message TEXT NOT NULL,
    PRIMARY KEY (run_id, group_id),
    FOREIGN KEY (run_id)
        REFERENCES assessment_runs (run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reconciliation_members (
    run_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    PRIMARY KEY (run_id, group_id, observation_id),
    FOREIGN KEY (run_id, group_id)
        REFERENCES reconciliation_groups (run_id, group_id)
        ON DELETE CASCADE,
    FOREIGN KEY (observation_id)
        REFERENCES evidence_observations (observation_id)
);

CREATE TABLE IF NOT EXISTS obligation_results (
    run_id TEXT NOT NULL,
    obligation_id TEXT NOT NULL,
    dimension_code TEXT NOT NULL,
    obligation_status TEXT NOT NULL
        CHECK (obligation_status IN ('MET', 'PARTIAL', 'NOT_MET')),
    review_required INTEGER NOT NULL CHECK (review_required IN (0, 1)),
    reason TEXT NOT NULL,
    PRIMARY KEY (run_id, obligation_id),
    FOREIGN KEY (run_id)
        REFERENCES assessment_runs (run_id) ON DELETE CASCADE,
    FOREIGN KEY (obligation_id)
        REFERENCES obligations (obligation_id)
);

CREATE TABLE IF NOT EXISTS evidence_evaluations (
    run_id TEXT NOT NULL,
    obligation_id TEXT NOT NULL,
    assessment_unit_id TEXT NOT NULL,
    digest TEXT,
    reconciliation_group_id TEXT,
    reconciliation_type TEXT,
    type_matches INTEGER NOT NULL CHECK (type_matches IN (0, 1)),
    date_state TEXT NOT NULL,
    status_state TEXT NOT NULL,
    qualifies_for_met INTEGER NOT NULL CHECK (qualifies_for_met IN (0, 1)),
    supports_partial INTEGER NOT NULL CHECK (supports_partial IN (0, 1)),
    review_required INTEGER NOT NULL CHECK (review_required IN (0, 1)),
    decision_basis TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    PRIMARY KEY (run_id, obligation_id, assessment_unit_id),
    FOREIGN KEY (run_id, obligation_id)
        REFERENCES obligation_results (run_id, obligation_id)
        ON DELETE CASCADE,
    FOREIGN KEY (run_id, reconciliation_group_id)
        REFERENCES reconciliation_groups (run_id, group_id)
);

CREATE TABLE IF NOT EXISTS evaluation_observations (
    run_id TEXT NOT NULL,
    obligation_id TEXT NOT NULL,
    assessment_unit_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    PRIMARY KEY (
        run_id,
        obligation_id,
        assessment_unit_id,
        observation_id
    ),
    FOREIGN KEY (run_id, obligation_id, assessment_unit_id)
        REFERENCES evidence_evaluations (
            run_id,
            obligation_id,
            assessment_unit_id
        ) ON DELETE CASCADE,
    FOREIGN KEY (observation_id)
        REFERENCES evidence_observations (observation_id)
);

CREATE TABLE IF NOT EXISTS dimension_results (
    run_id TEXT NOT NULL,
    dimension_code TEXT NOT NULL,
    dimension_name TEXT NOT NULL,
    weight TEXT NOT NULL,
    score TEXT NOT NULL,
    dimension_status TEXT NOT NULL
        CHECK (dimension_status IN ('GREEN', 'AMBER', 'RED')),
    review_required INTEGER NOT NULL CHECK (review_required IN (0, 1)),
    reason TEXT NOT NULL,
    PRIMARY KEY (run_id, dimension_code),
    FOREIGN KEY (run_id)
        REFERENCES assessment_runs (run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_obligations_dimension
    ON obligations (dimension_code, obligation_id);

CREATE INDEX IF NOT EXISTS idx_evidence_validated_obligation
    ON evidence_observations (validated_obligation_id, observation_id);

CREATE INDEX IF NOT EXISTS idx_quality_observation
    ON data_quality_issues (run_id, observation_id, issue_type);

CREATE INDEX IF NOT EXISTS idx_obligation_results_dimension
    ON obligation_results (run_id, dimension_code, obligation_id);
