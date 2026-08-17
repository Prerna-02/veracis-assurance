from assess import assess_obligations
from ingest import (
    load_json,
    load_csv,
    load_registry_tsv,
    load_source_notes,
)
from reconcile import reconcile_evidence
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
    print("--------------------------------------------")
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
    print("--------------------------------------------")
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
    print("--------------------------------------------")
    print("Record count:", len(evidence))
    print("Columns:", list(evidence[0].keys()))
    print("Statuses:", unique_values(evidence, "status"))
    print("Missing values:", count_missing(evidence))

    print("\nREGISTRY TSV")
    print("--------------------------------------------")
    print("Record count:", len(registry))
    print("Columns:", list(registry[0].keys()))
    print(
        "Statuses:",
        unique_values(registry, "approval_state")
    )
    print("Missing values:", count_missing(registry))
    print("Preserved comments:", registry_comments)

    print("\nSERVICEDESK JSON")
    print("--------------------------------------------")

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
    print("--------------------------------------------")
    print("Source notes loaded:", bool(source_notes.strip()))

    print("\nCANONICAL EVIDENCE")
    print("--------------------------------------------")

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

    print("\nDATA QUALITY ISSUES")
    print("--------------------------------------------")

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
    print("--------------------------------------------")

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
    print("--------------------------------------------")

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


if __name__ == "__main__":
    main()
