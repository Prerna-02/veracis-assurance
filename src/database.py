import json
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"
OPERATIONAL_INTEGRITY_QUERY_PATH = (
    PROJECT_ROOT / "sql" / "operational_integrity_query.sql"
)
MODEL_RISK_CONTROLS_QUERY_PATH = (
    PROJECT_ROOT / "sql" / "model_risk_controls_query.sql"
)


def connect_database(db_path):
    """Open SQLite with foreign-key enforcement enabled."""

    connection = sqlite3.connect(Path(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_schema(connection):

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    connection.executescript(schema_sql)


def _json_text(value):

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def build_provisional_run_id(obligations_data, methodology):
    obligation_set_version = obligations_data[
        "obligation_set_version"
    ]
    methodology_version = methodology["methodology_version"]
    as_at_date = methodology["evidence_rules"]["as_at_date"]

    return (
        f"assessment:{obligation_set_version}:"
        f"{methodology_version}:{as_at_date}"
    )


def load_assessment_run(
    connection,
    run_id,
    obligations_data,
    methodology,
):


    connection.execute(
        """
        INSERT INTO assessment_runs (
            run_id,
            methodology_version,
            obligation_set_version,
            as_at_date
        ) VALUES (?, ?, ?, ?)
        """,
        (
            run_id,
            methodology["methodology_version"],
            obligations_data["obligation_set_version"],
            methodology["evidence_rules"]["as_at_date"],
        ),
    )


def load_obligations(connection, obligations_data):

    rows = []

    for obligation in sorted(
        obligations_data["obligations"],
        key=lambda item: item["obligation_id"],
    ):
        rows.append(
            (
                obligation["obligation_id"],
                obligation["source"],
                obligation["clause_ref"],
                obligation["dimension"],
                obligation["requirement_text"],
                _json_text(
                    sorted(obligation["required_evidence_types"])
                ),
            )
        )

    connection.executemany(
        """
        INSERT INTO obligations (
            obligation_id,
            source,
            clause_reference,
            dimension_code,
            requirement_text,
            required_evidence_types_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (obligation_id) DO UPDATE SET
            source = excluded.source,
            clause_reference = excluded.clause_reference,
            dimension_code = excluded.dimension_code,
            requirement_text = excluded.requirement_text,
            required_evidence_types_json =
                excluded.required_evidence_types_json
        """,
        rows,
    )


def load_evidence_observations(
    connection,
    canonical_records,
    obligations_data,
):


    valid_obligation_ids = {
        obligation["obligation_id"]
        for obligation in obligations_data["obligations"]
    }
    rows = []

    for record in sorted(
        canonical_records,
        key=lambda item: item.observation_id,
    ):
        validated_obligation_id = (
            record.obligation_id
            if record.obligation_id in valid_obligation_ids
            else None
        )

        rows.append(
            (
                record.observation_id,
                record.source_dataset,
                record.source_position,
                record.origin_system,
                record.source_record_id,
                record.obligation_id,
                validated_obligation_id,
                record.evidence_type,
                record.title,
                (
                    record.event_date.isoformat()
                    if record.event_date is not None
                    else None
                ),
                record.date_basis,
                record.raw_date_value,
                record.raw_status,
                record.normalized_status,
                record.owner,
                record.version,
                record.digest,
                record.source_category,
            )
        )

    connection.executemany(
        """
        INSERT INTO evidence_observations (
            observation_id,
            source_dataset,
            source_position,
            origin_system,
            source_record_id,
            claimed_obligation_id,
            validated_obligation_id,
            evidence_type,
            title,
            event_date,
            date_basis,
            raw_date_value,
            raw_status,
            normalized_status,
            owner,
            version,
            digest,
            source_category
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (observation_id) DO UPDATE SET
            source_dataset = excluded.source_dataset,
            source_position = excluded.source_position,
            origin_system = excluded.origin_system,
            source_record_id = excluded.source_record_id,
            claimed_obligation_id = excluded.claimed_obligation_id,
            validated_obligation_id = excluded.validated_obligation_id,
            evidence_type = excluded.evidence_type,
            title = excluded.title,
            event_date = excluded.event_date,
            date_basis = excluded.date_basis,
            raw_date_value = excluded.raw_date_value,
            raw_status = excluded.raw_status,
            normalized_status = excluded.normalized_status,
            owner = excluded.owner,
            version = excluded.version,
            digest = excluded.digest,
            source_category = excluded.source_category
        """,
        rows,
    )


def load_data_quality_issues(connection, run_id, quality_issues):
    rows = [
        (
            run_id,
            issue.issue_id,
            issue.observation_id,
            issue.issue_type,
            issue.severity,
            issue.field_name,
            issue.message,
            int(issue.review_required),
            issue.assessment_action,
        )
        for issue in sorted(quality_issues, key=lambda item: item.issue_id)
    ]

    connection.executemany(
        """
        INSERT INTO data_quality_issues (
            run_id,
            issue_id,
            observation_id,
            issue_type,
            severity,
            field_name,
            message,
            review_required,
            assessment_action
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def load_reconciliation_groups(
    connection,
    run_id,
    reconciliation_groups,
):


    for group in sorted(
        reconciliation_groups,
        key=lambda item: item.group_id,
    ):
        connection.execute(
            """
            INSERT INTO reconciliation_groups (
                run_id,
                group_id,
                digest,
                group_type,
                review_required,
                assessment_handling,
                message
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                group.group_id,
                group.digest,
                group.group_type,
                int(group.review_required),
                group.assessment_handling,
                group.message,
            ),
        )

        connection.executemany(
            """
            INSERT INTO reconciliation_members (
                run_id,
                group_id,
                observation_id
            ) VALUES (?, ?, ?)
            """,
            [
                (run_id, group.group_id, observation_id)
                for observation_id in group.observation_ids
            ],
        )


def load_obligation_results(
    connection,
    run_id,
    obligation_assessments,
):

    rows = [
        (
            run_id,
            assessment.obligation_id,
            assessment.dimension,
            assessment.status,
            int(assessment.review_required),
            assessment.reason,
        )
        for assessment in sorted(
            obligation_assessments,
            key=lambda item: item.obligation_id,
        )
    ]

    connection.executemany(
        """
        INSERT INTO obligation_results (
            run_id,
            obligation_id,
            dimension_code,
            obligation_status,
            review_required,
            reason
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def load_evidence_evaluations(
    connection,
    run_id,
    obligation_assessments,
    reconciliation_groups,
):


    group_ids_by_digest = {
        group.digest: group.group_id
        for group in reconciliation_groups
    }

    for assessment in sorted(
        obligation_assessments,
        key=lambda item: item.obligation_id,
    ):
        for evaluation in assessment.evidence_evaluations:
            reconciliation_group_id = None

            if evaluation.reconciliation_type is not None:
                reconciliation_group_id = group_ids_by_digest.get(
                    evaluation.digest
                )

                if reconciliation_group_id is None:
                    raise ValueError(
                        "Evidence evaluation references reconciliation "
                        f"type {evaluation.reconciliation_type!r} without "
                        "a matching reconciliation group."
                    )

            connection.execute(
                """
                INSERT INTO evidence_evaluations (
                    run_id,
                    obligation_id,
                    assessment_unit_id,
                    digest,
                    reconciliation_group_id,
                    reconciliation_type,
                    type_matches,
                    date_state,
                    status_state,
                    qualifies_for_met,
                    supports_partial,
                    review_required,
                    decision_basis,
                    reasons_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    assessment.obligation_id,
                    evaluation.assessment_unit_id,
                    evaluation.digest,
                    reconciliation_group_id,
                    evaluation.reconciliation_type,
                    int(evaluation.type_matches),
                    evaluation.date_state,
                    evaluation.status_state,
                    int(evaluation.qualifies_for_met),
                    int(evaluation.supports_partial),
                    int(evaluation.review_required),
                    evaluation.decision_basis,
                    _json_text(list(evaluation.reasons)),
                ),
            )

            connection.executemany(
                """
                INSERT INTO evaluation_observations (
                    run_id,
                    obligation_id,
                    assessment_unit_id,
                    observation_id
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        assessment.obligation_id,
                        evaluation.assessment_unit_id,
                        observation_id,
                    )
                    for observation_id in evaluation.observation_ids
                ],
            )


def load_dimension_results(
    connection,
    run_id,
    dimension_assessments,
):


    rows = [
        (
            run_id,
            assessment.dimension_code,
            assessment.dimension_name,
            assessment.weight,
            assessment.score,
            assessment.dimension_status,
            int(assessment.review_required),
            assessment.reason,
        )
        for assessment in sorted(
            dimension_assessments,
            key=lambda item: item.dimension_code,
        )
    ]

    connection.executemany(
        """
        INSERT INTO dimension_results (
            run_id,
            dimension_code,
            dimension_name,
            weight,
            score,
            dimension_status,
            review_required,
            reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def load_traceability_database(
    db_path,
    run_id,
    obligations_data,
    methodology,
    canonical_records,
    quality_issues,
    reconciliation_groups,
    obligation_assessments,
    dimension_assessments,
):


    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect_database(db_path)

    try:
        initialize_schema(connection)

        with connection:
            connection.execute(
                "DELETE FROM assessment_runs WHERE run_id = ?",
                (run_id,),
            )

            load_obligations(connection, obligations_data)
            load_evidence_observations(
                connection,
                canonical_records,
                obligations_data,
            )
            load_assessment_run(
                connection,
                run_id,
                obligations_data,
                methodology,
            )
            load_data_quality_issues(
                connection,
                run_id,
                quality_issues,
            )
            load_reconciliation_groups(
                connection,
                run_id,
                reconciliation_groups,
            )
            load_obligation_results(
                connection,
                run_id,
                obligation_assessments,
            )
            load_evidence_evaluations(
                connection,
                run_id,
                obligation_assessments,
                reconciliation_groups,
            )
            load_dimension_results(
                connection,
                run_id,
                dimension_assessments,
            )
    finally:
        connection.close()

    return db_path.resolve()


def get_database_counts(connection):
    """Return dynamic row counts for the audit-store summary."""

    table_names = (
        "assessment_runs",
        "obligations",
        "evidence_observations",
        "data_quality_issues",
        "reconciliation_groups",
        "reconciliation_members",
        "obligation_results",
        "evidence_evaluations",
        "evaluation_observations",
        "dimension_results",
    )

    return {
        table_name: connection.execute(
            f"SELECT COUNT(*) FROM {table_name}"
        ).fetchone()[0]
        for table_name in table_names
    }


def run_operational_integrity_query(connection):
    """Execute the standalone SQL audit path for Operational Integrity."""

    query_sql = OPERATIONAL_INTEGRITY_QUERY_PATH.read_text(
        encoding="utf-8"
    )
    return connection.execute(query_sql).fetchall()


def run_model_risk_controls_query(connection):
    """Execute the standalone SQL audit path for model-risk controls."""

    query_sql = MODEL_RISK_CONTROLS_QUERY_PATH.read_text(
        encoding="utf-8"
    )
    return connection.execute(query_sql).fetchall()
