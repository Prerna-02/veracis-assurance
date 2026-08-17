"""Veracis Assurance application entry point."""
from ingest import (
    load_json,
    load_csv,
    load_registry_tsv,
    load_source_notes,
)

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


if __name__ == "__main__":
    main()
