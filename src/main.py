from pathlib import Path
from itertools import groupby

from assess import assess_obligations
from database import (
    build_provisional_run_id,
    connect_database,
    get_database_counts,
    load_traceability_database,
    run_model_risk_controls_query,
    run_operational_integrity_query,
)
from ingest import (
    load_json,
    load_csv,
    load_registry_tsv,
    load_source_notes,
)
from reconcile import reconcile_evidence
from report import (
    build_assessment_report,
    serialize_report,
    sha256_bytes,
    write_assessment_report,
)
from score import score_dimensions
from validate import validate_evidence
from normalize import normalize_all_evidence



def count_missing(records):
    """Count blank values for each field in a list of records."""
    missing = {}

    if not records:
        return missing

    for field in records[0].keys():
        count = sum(
            1
            for record in records
            if record.get(field) in (None, "", "-")
        )

        if count > 0:
            missing[field] = count

    return missing


def unique_values(records, field):
    """Return sorted unique non-empty values for a field."""
    return sorted(
        {
            record.get(field)
            for record in records
            if record.get(field) not in (None, "", "-")
        }
    )


def format_dimension_traceability(rows):
    """Format row-level SQL lineage as a deterministic audit hierarchy."""

    if not rows:
        return "No traceability rows found."

    def value(row, field):
        item = row[field]
        return "none" if item in (None, "") else str(item)

    def boolean(row, field):
        item = row[field]
        return "none" if item is None else str(bool(item))

    ordered_rows = sorted(
        rows,
        key=lambda row: (
            value(row, "dimension_code"),
            value(row, "obligation_id"),
            value(row, "assessment_unit_id"),
            value(row, "source_dataset"),
            value(row, "observation_id"),
            value(row, "issue_type"),
            value(row, "issue_message"),
        ),
    )
    lines = []

    for _, dimension_group in groupby(
        ordered_rows,
        key=lambda row: row["dimension_code"],
    ):
        dimension_rows = list(dimension_group)
        dimension = dimension_rows[0]
        lines.extend(
            [
                f'{value(dimension, "dimension_name").upper()} AUDIT',
                "--------------------------------------------",
                "",
                f'Dimension: {value(dimension, "dimension_code")}',
                f'Name: {value(dimension, "dimension_name")}',
                f'Score: {value(dimension, "dimension_score")}',
                f'Status: {value(dimension, "dimension_status")}',
                "Review required: "
                f'{boolean(dimension, "dimension_review_required")}',
            ]
        )

        for _, obligation_group in groupby(
            dimension_rows,
            key=lambda row: row["obligation_id"],
        ):
            obligation_rows = list(obligation_group)
            obligation = obligation_rows[0]
            lines.extend(
                [
                    "",
                    f'Obligation: {value(obligation, "obligation_id")}',
                    f'Status: {value(obligation, "obligation_status")}',
                    "Review required: "
                    f'{boolean(obligation, "obligation_review_required")}',
                    f'Reason: {value(obligation, "obligation_reason")}',
                ]
            )

            for _, unit_group in groupby(
                obligation_rows,
                key=lambda row: row["assessment_unit_id"],
            ):
                unit_rows = list(unit_group)
                unit = unit_rows[0]
                lines.extend(
                    [
                        "",
                        "  Assessment unit: "
                        f'{value(unit, "assessment_unit_id")}',
                        f'  Digest: {value(unit, "evaluation_digest")}',
                        "  Reconciliation type: "
                        f'{value(unit, "reconciliation_type")}',
                        f'  Date state: {value(unit, "date_state")}',
                        f'  Status state: {value(unit, "status_state")}',
                        "  Type matches: "
                        f'{boolean(unit, "type_matches")}',
                        "  Qualifies for MET: "
                        f'{boolean(unit, "qualifies_for_met")}',
                        "  Supports PARTIAL: "
                        f'{boolean(unit, "supports_partial")}',
                        "  Decision basis: "
                        f'{value(unit, "decision_basis")}',
                        "  Review required: "
                        f'{boolean(unit, "evaluation_review_required")}',
                        "",
                        "  Source observations:",
                    ]
                )

                observation_groups = groupby(
                    unit_rows,
                    key=lambda row: (
                        row["source_dataset"],
                        row["observation_id"],
                    ),
                )

                for _, observation_group in observation_groups:
                    observation_rows = list(observation_group)
                    observation = observation_rows[0]

                    if observation["observation_id"] is None:
                        lines.append("    none")
                        continue

                    lines.extend(
                        [
                            "    "
                            f'{value(observation, "source_record_id")} | '
                            f'{value(observation, "source_dataset")} | '
                            f'{value(observation, "normalized_status")}',
                            "      Observation ID: "
                            f'{value(observation, "observation_id")}',
                            "      Evidence type: "
                            f'{value(observation, "evidence_type")}',
                            f'      Date: {value(observation, "event_date")}',
                        ]
                    )

                    issues = []
                    seen_issues = set()

                    for issue_row in observation_rows:
                        if issue_row["issue_type"] is None:
                            continue

                        issue = (
                            issue_row["issue_type"],
                            issue_row["issue_message"],
                            issue_row["severity"],
                            issue_row["assessment_action"],
                        )

                        if issue not in seen_issues:
                            seen_issues.add(issue)
                            issues.append(issue)

                    if not issues:
                        lines.append("      Issue: none")
                    else:
                        for issue_type, message, severity, action in issues:
                            lines.extend(
                                [
                                    f"      Issue: {issue_type}",
                                    f"      Reason: {message}",
                                    f"      Severity: {severity}",
                                    f"      Assessment action: {action}",
                                ]
                            )

    return "\n".join(lines)


def main():

    # ---------------------------
    # Authoritative reference data
    # ---------------------------

    obligations_data = load_json("obligations.json")
    methodology = load_json("methodology.json")

    # ---------------------------
    # Evidence sources
    # ---------------------------

    evidence = load_csv("evidence.csv")

    registry, registry_comments = load_registry_tsv(
        "registry_export.tsv"
    )

    servicedesk = load_json("servicedesk_export.json")

    # ---------------------------
    # Supporting documentation
    # ---------------------------

    source_notes = load_source_notes("source_notes.md")

    canonical_evidence = normalize_all_evidence(
        evidence,
        registry,
        servicedesk,
    )

    print("\n========== VERACIS SOURCE PROFILE ==========\n")

    print("OBLIGATIONS")
    print(
        "Obligation set version:",
        obligations_data["obligation_set_version"]
    )
    print(
        "Number of obligations:",
        len(obligations_data["obligations"])
    )

    obligation_dimensions = sorted(
        {
            obligation["dimension"]
            for obligation in obligations_data["obligations"]
        }
    )

    print("Dimensions:", obligation_dimensions)

    print("\nMETHODOLOGY")
    print(
        "Methodology version:",
        methodology["methodology_version"]
    )
    print(
        "As-at date:",
        methodology["evidence_rules"]["as_at_date"]
    )
    print(
        "Staleness threshold:",
        methodology["evidence_rules"]["staleness_threshold_days"],
        "days"
    )

    print("\nEVIDENCE CSV")
    print("Record count:", len(evidence))
    print("Columns:", list(evidence[0].keys()))
    print("Statuses:", unique_values(evidence, "status"))
    print("Missing values:", count_missing(evidence))

    print("\nREGISTRY TSV")
    print("Record count:", len(registry))
    print("Columns:", list(registry[0].keys()))
    print(
        "Statuses:",
        unique_values(registry, "approval_state")
    )
    print("Missing values:", count_missing(registry))
    print("Preserved comments:", registry_comments)

    print("\nSERVICEDESK JSON")

    tickets = servicedesk["tickets"]

    print(
        "Declared record count:",
        servicedesk["export_meta"]["record_count"]
    )
    print(
        "Actual ticket count:",
        len(tickets)
    )
    print(
        "Export generated:",
        servicedesk["export_meta"]["export_generated"]
    )

    print(
        "States:",
        unique_values(tickets, "state")
    )

    print(
        "Tickets with missing closed_at:",
        sum(
            1
            for ticket in tickets
            if ticket.get("closed_at") is None
        )
    )

    print(
    "Categories:",
    unique_values(tickets, "category")
    )

    print(
    "Linked controls:",
    unique_values(tickets, "linked_control")
    )

    print(
    "Artefact kinds:",
    sorted(
        {
            ticket["artefact"]["kind"]
            for ticket in tickets
        }
    )
    )

    print("\nSOURCE NOTES")
    print("Source notes loaded:", bool(source_notes.strip()))

    print("\nCANONICAL EVIDENCE")
    print(
        "Total canonical observations:",
        len(canonical_evidence)
    )

    source_counts = {}

    for record in canonical_evidence:
        source_counts[record.source_dataset] = (
            source_counts.get(
                record.source_dataset,
                0
            ) + 1
        )

    print(
        "Observations by source:",
        source_counts
    )

    unknown_status_count = sum(
        1
        for record in canonical_evidence
        if record.normalized_status == "UNKNOWN"
    )

    print(
        "Unknown normalized statuses:",
        unknown_status_count
    )

    missing_date_records = [
        record
        for record in canonical_evidence
        if record.event_date is None
    ]

    print(
        "Observations with missing event date:",
        len(missing_date_records)
    )

    print("\nRecords with missing event dates:")

    for record in missing_date_records:
        print(
            record.observation_id,
            "|",
            record.source_record_id,
            "|",
            record.source_dataset,
            "| date basis:",
            record.date_basis,
        )


    quality_issues = validate_evidence(
        canonical_evidence,
        obligations_data,
        methodology,
    )

    reconciliation_groups = reconcile_evidence(
        canonical_evidence
    )

    obligation_assessments = assess_obligations(
        canonical_evidence,
        obligations_data,
        methodology,
        quality_issues,
        reconciliation_groups,
    )

    dimension_assessments = score_dimensions(
        obligation_assessments,
        methodology,
    )

    run_id = build_provisional_run_id(
        obligations_data,
        methodology,
    )
    project_root = Path(__file__).resolve().parent.parent
    database_path = load_traceability_database(
        db_path=project_root / "output" / "veracis_traceability.db",
        run_id=run_id,
        obligations_data=obligations_data,
        methodology=methodology,
        canonical_records=canonical_evidence,
        quality_issues=quality_issues,
        reconciliation_groups=reconciliation_groups,
        obligation_assessments=obligation_assessments,
        dimension_assessments=dimension_assessments,
    )

    database_connection = connect_database(database_path)

    try:
        database_counts = get_database_counts(database_connection)
        operational_integrity_rows = (
            run_operational_integrity_query(database_connection)
        )
        model_risk_controls_rows = (
            run_model_risk_controls_query(database_connection)
        )
    finally:
        database_connection.close()

    report_arguments = {
        "obligations_data": obligations_data,
        "methodology": methodology,
        "canonical_records": canonical_evidence,
        "quality_issues": quality_issues,
        "reconciliation_groups": reconciliation_groups,
        "obligation_assessments": obligation_assessments,
        "dimension_assessments": dimension_assessments,
    }
    report_a = build_assessment_report(**report_arguments)
    report_bytes_a = serialize_report(report_a)
    report_bytes_b = serialize_report(
        build_assessment_report(**report_arguments)
    )
    report_hash_a = sha256_bytes(report_bytes_a)
    report_hash_b = sha256_bytes(report_bytes_b)
    reports_are_identical = (
        report_bytes_a == report_bytes_b
        and report_hash_a == report_hash_b
    )

    if not reports_are_identical:
        raise RuntimeError(
            "Repeated assessment serialization was not byte-identical."
        )

    report_output_path = project_root / "output" / "assessment.json"
    write_assessment_report(report_a, report_output_path)

    print("\nDATA QUALITY ISSUES")

    print(
        "Total issues:",
        len(quality_issues)
    )

    issue_type_counts = {}

    for issue in quality_issues:
        issue_type_counts[issue.issue_type] = (
            issue_type_counts.get(
                issue.issue_type,
                0
            ) + 1
        )

    print(
        "Issues by type:",
        issue_type_counts
    )

    assessment_action_counts = {
        "KEEP_FOR_ASSESSMENT": 0,
        "REVIEW_BEFORE_ASSESSMENT": 0,
        "EXCLUDE_FROM_ASSESSMENT": 0,
    }

    for issue in quality_issues:
        assessment_action_counts[issue.assessment_action] = (
            assessment_action_counts[issue.assessment_action] + 1
        )

    print(
        "Assessment actions:",
        assessment_action_counts
    )

    print(
        "Records requiring review:",
        sum(
            1
            for issue in quality_issues
            if issue.review_required is True
        )
    )


    print("\nDefect register:")

    for issue in quality_issues:

        print(
            "\n",
            issue.source_record_id,
            "|",
            issue.issue_type,
            "|",
            issue.severity,
        )

        print(
            " Reason:",
            issue.message
        )

        print(
            " Review required:",
            issue.review_required
        )

        print(
            " Assessment action:",
            issue.assessment_action
        )

    print("\nRECONCILIATION")
   

    print(
        "Repeated-digest groups:",
        len(reconciliation_groups)
    )

    print(
        "Groups requiring review:",
        sum(
            1
            for group in reconciliation_groups
            if group.review_required is True
        )
    )

    group_type_counts = {}

    for group in reconciliation_groups:
        group_type_counts[group.group_type] = (
            group_type_counts.get(group.group_type, 0) + 1
        )

    print(
        "Groups by type:",
        dict(sorted(group_type_counts.items()))
    )

    print("\nReconciliation register:")

    for group in reconciliation_groups:
        print("\nGroup ID:", group.group_id)
        print("Digest:", group.digest)
        print("Group type:", group.group_type)
        print(
            "Sources:",
            ", ".join(group.source_datasets) or "(none)"
        )
        print(
            "Source record IDs:",
            ", ".join(group.source_record_ids) or "(none)"
        )
        print(
            "Obligations:",
            ", ".join(group.obligation_ids) or "(none)"
        )
        print(
            "Evidence types:",
            ", ".join(group.evidence_types) or "(none)"
        )
        print(
            "Statuses:",
            ", ".join(group.normalized_statuses) or "(none)"
        )
        print(
            "Titles:",
            " | ".join(group.titles) or "(none)"
        )
        print(
            "Versions:",
            ", ".join(group.versions) or "(none)"
        )
        print("Review required:", group.review_required)
        print(
            "Assessment handling:",
            group.assessment_handling
        )
        print("Reason:", group.message)

    print("\nOBLIGATION ASSESSMENT")

    print(
        "Total obligations assessed:",
        len(obligation_assessments)
    )

    status_counts = {
        "MET": 0,
        "PARTIAL": 0,
        "NOT_MET": 0,
    }

    for assessment in obligation_assessments:
        status_counts[assessment.status] = (
            status_counts[assessment.status] + 1
        )

    print("Status counts:", status_counts)

    print(
        "Obligations requiring review:",
        sum(
            1
            for assessment in obligation_assessments
            if assessment.review_required is True
        )
    )

    print("\nObligation assessment register:")

    for assessment in obligation_assessments:
        print("\nObligation:", assessment.obligation_id)
        print("Dimension:", assessment.dimension)
        print("Status:", assessment.status)
        print("Review required:", assessment.review_required)
        print("Reason:", assessment.reason)
        print(
            "Evidence units evaluated:",
            len(assessment.evidence_evaluations)
        )

        for evaluation in assessment.evidence_evaluations:
            print("\n  Unit ID:", evaluation.assessment_unit_id)
            print(
                "  Source record IDs:",
                ", ".join(evaluation.source_record_ids)
                or "(none)"
            )
            print(
                "  Sources:",
                ", ".join(evaluation.source_datasets)
                or "(none)"
            )
            print("  Digest:", evaluation.digest or "(none)")
            print(
                "  Evidence types:",
                ", ".join(evaluation.evidence_types)
                or "(none)"
            )
            print(
                "  Statuses:",
                ", ".join(evaluation.normalized_statuses)
                or "(none)"
            )
            print(
                "  Event dates:",
                ", ".join(evaluation.event_dates)
                or "(none)"
            )
            print("  Date state:", evaluation.date_state)
            print("  Type matches:", evaluation.type_matches)
            print(
                "  Reconciliation type:",
                evaluation.reconciliation_type or "(none)"
            )
            print(
                "  Qualifies for MET:",
                evaluation.qualifies_for_met
            )
            print(
                "  Supports PARTIAL:",
                evaluation.supports_partial
            )
            print("  Decision basis:", evaluation.decision_basis)
            print("  Review required:", evaluation.review_required)
            print(
                "  Reasons:",
                " | ".join(evaluation.reasons)
            )

    print("\nDIMENSION ASSESSMENT")

    print(
        "Total dimensions assessed:",
        len(dimension_assessments)
    )

    print(
        "Dimensions requiring review:",
        sum(
            1
            for assessment in dimension_assessments
            if assessment.review_required is True
        )
    )

    dimension_status_counts = {
        "GREEN": 0,
        "AMBER": 0,
        "RED": 0,
    }

    for assessment in dimension_assessments:
        dimension_status_counts[assessment.dimension_status] = (
            dimension_status_counts[assessment.dimension_status] + 1
        )

    print(
        "Dimension status counts:",
        dimension_status_counts
    )

    print("\nDimension assessment register:")

    for assessment in dimension_assessments:
        print("\nDimension:", assessment.dimension_code)
        print("Name:", assessment.dimension_name)
        print("Weight:", assessment.weight)
        print("Score:", assessment.score)
        print("Dimension status:", assessment.dimension_status)
        print("Review required:", assessment.review_required)
        print("Obligations:")

        for contribution in assessment.obligation_contributions:
            print(
                " ",
                contribution.obligation_id,
                contribution.obligation_status,
                "->",
                contribution.contribution,
            )

        print("Calculation:")
        print("  Earned points:", assessment.earned_points)
        print("  Maximum points:", assessment.maximum_points)
        print("  Score:", assessment.score)
        print("Reason:", assessment.reason)

    print("\nSQL TRACEABILITY")
    print("--------------------------------------------")
    print("Database path:", database_path)
    print("Assessment run ID:", run_id)
    print(
        "Assessment runs stored:",
        database_counts["assessment_runs"]
    )
    print(
        "Obligations stored:",
        database_counts["obligations"]
    )
    print(
        "Evidence observations stored:",
        database_counts["evidence_observations"]
    )
    print(
        "Data-quality issues stored:",
        database_counts["data_quality_issues"]
    )
    print(
        "Reconciliation groups stored:",
        database_counts["reconciliation_groups"]
    )
    print(
        "Obligation results stored:",
        database_counts["obligation_results"]
    )
    print(
        "Dimension results stored:",
        database_counts["dimension_results"]
    )
    print(
        "Operational Integrity source-level audit rows:",
        len(operational_integrity_rows)
    )
    print(
        "Model and Tool Risk Controls source-level audit rows:",
        len(model_risk_controls_rows)
    )

    print("\n" + format_dimension_traceability(
        operational_integrity_rows
    ))
    print("\n" + format_dimension_traceability(
        model_risk_controls_rows
    ))

    print("\nDETERMINISTIC OUTPUT")
    print("Output path: output/assessment.json")
    print("Output bytes:", len(report_bytes_a))
    print("SHA-256:", report_hash_a)
    print("Second serialization SHA-256:", report_hash_b)
    print("Byte-identical repeat:", reports_are_identical)



if __name__ == "__main__":
    main()
