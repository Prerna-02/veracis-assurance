from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class CanonicalEvidence:
    """
    Common representation for one evidence observation.

    This stores normalized source information only.
    Assessment fields such as staleness, type matching,
    obligation result and dimension status are calculated later.
    """

    # Internal audit identity
    observation_id: str

    # Provenance
    source_dataset: str
    source_position: int
    origin_system: str
    source_record_id: str

    # Evidence business fields
    obligation_id: Optional[str]
    evidence_type: Optional[str]
    title: Optional[str]

    # Date fields
    event_date: Optional[date]
    date_basis: str
    raw_date_value: Optional[str]

    # Status fields
    raw_status: Optional[str]
    normalized_status: str

    # Supporting metadata
    owner: Optional[str]
    version: Optional[str]
    digest: Optional[str]

    # Mainly useful for ServiceDesk
    source_category: Optional[str] = None


NORMALIZED_STATUSES = (
    "APPROVED",
    "DRAFT",
    "SUPERSEDED",
    "AWAITING_SIGNOFF",
    "APPROVED_RETROSPECTIVELY",
    "UNKNOWN",
)


STATUS_MAPS = {
    "evidence_csv": {
        "APPROVED": "APPROVED",
        "DRAFT": "DRAFT",
        "SUPERSEDED": "SUPERSEDED",
    },

    "registry": {
        "Approved": "APPROVED",
        "Draft": "DRAFT",
    },

    "servicedesk": {
        "Closed - Approved": "APPROVED",
        "Open - In Draft": "DRAFT",
        "Open - Awaiting Sign-off": "AWAITING_SIGNOFF",
        "Closed - Approved Retrospectively":
            "APPROVED_RETROSPECTIVELY",
    },
}


SOURCE_FIELD_MAPS = {
    "evidence_csv": {
        "source_record_id": "evidence_id",
        "obligation_id": "obligation_id",
        "evidence_type": "evidence_type",
        "title": "title",
        "event_date": "evidence_date",
        "status": "status",
        "owner": "owner",
        "version": "version",
        "digest": "evidence_hash",
    },

    "registry": {
        "source_record_id": "asset_ref",
        "obligation_id": "control_ref",
        "evidence_type": "doc_class",
        "title": "doc_title",
        "event_date": "captured_on",
        "status": "approval_state",
        "owner": "accountable_person",
        "version": "rev",
        "digest": "digest",
    },

    "servicedesk": {
        "source_record_id": "ticket_ref",
        "obligation_id": "linked_control",
        "evidence_type": "artefact.kind",
        "title": "summary",
        "event_date": "closed_at",
        "status": "state",
        "owner": "raised_by",
        "version": "artefact.revision",
        "digest": "artefact.checksum",
        "category": "category",
    },
}

def clean_optional(value):
    if value is None:
        return None

    value = str(value).strip()

    if value in ("", "-"):
        return None

    return value


def parse_event_date(source_dataset, raw_value):
    """
    Convert source-specific date formats into a Python date.

    The exact original value is preserved separately in
    raw_date_value.
    """
    raw_value = clean_optional(raw_value)

    if raw_value is None:
        return None

    if source_dataset == "evidence_csv":
        return datetime.strptime(
            raw_value,
            "%Y-%m-%d"
        ).date()

    if source_dataset == "registry":
        return datetime.strptime(
            raw_value,
            "%d/%m/%Y"
        ).date()

    if source_dataset == "servicedesk":
        return datetime.strptime(
            raw_value,
            "%Y-%m-%dT%H:%M:%SZ"
        ).date()

    raise ValueError(
        f"Unsupported source dataset: {source_dataset}"
    )


def normalize_status(source_dataset, raw_status):
    raw_status = clean_optional(raw_status)

    if raw_status is None:
        return "UNKNOWN"

    return STATUS_MAPS.get(
        source_dataset, {}
    ).get(
        raw_status,
        "UNKNOWN"
    )



def normalize_evidence_csv(records):
    """Convert evidence.csv records into canonical evidence."""

    canonical_records = []

    for position, record in enumerate(records, start=1):

        raw_date = clean_optional(
            record.get("evidence_date")
        )

        raw_status = clean_optional(
            record.get("status")
        )

        canonical = CanonicalEvidence(
            observation_id=f"evidence_csv:{position:04d}",

            source_dataset="evidence_csv",
            source_position=position,
            origin_system=clean_optional(
                record.get("source_system")
            ) or "UNKNOWN",
            source_record_id=record["evidence_id"],

            obligation_id=clean_optional(
                record.get("obligation_id")
            ),
            evidence_type=clean_optional(
                record.get("evidence_type")
            ),
            title=clean_optional(
                record.get("title")
            ),

            event_date=parse_event_date(
                "evidence_csv",
                raw_date
            ),
            date_basis="evidence_date",
            raw_date_value=raw_date,

            raw_status=raw_status,
            normalized_status=normalize_status(
                "evidence_csv",
                raw_status
            ),

            owner=clean_optional(
                record.get("owner")
            ),
            version=clean_optional(
                record.get("version")
            ),
            digest=clean_optional(
                record.get("evidence_hash")
            ),

            source_category=None,
        )

        canonical_records.append(canonical)

    return canonical_records


def normalize_registry(records):
    """Convert Registry records into canonical evidence."""

    canonical_records = []

    for position, record in enumerate(records, start=1):

        raw_date = clean_optional(
            record.get("captured_on")
        )

        raw_status = clean_optional(
            record.get("approval_state")
        )

        canonical = CanonicalEvidence(
            observation_id=f"registry:{position:04d}",

            source_dataset="registry",
            source_position=position,
            origin_system="Meridian Asset Registry",
            source_record_id=record["asset_ref"],

            obligation_id=clean_optional(
                record.get("control_ref")
            ),
            evidence_type=clean_optional(
                record.get("doc_class")
            ),
            title=clean_optional(
                record.get("doc_title")
            ),

            event_date=parse_event_date(
                "registry",
                raw_date
            ),
            date_basis="captured_on",
            raw_date_value=raw_date,

            raw_status=raw_status,
            normalized_status=normalize_status(
                "registry",
                raw_status
            ),

            owner=clean_optional(
                record.get("accountable_person")
            ),
            version=clean_optional(
                record.get("rev")
            ),
            digest=clean_optional(
                record.get("digest")
            ),

            source_category=None,
        )

        canonical_records.append(canonical)

    return canonical_records


def normalize_servicedesk(servicedesk_data):
    """Convert nested ServiceDesk tickets into canonical evidence."""

    canonical_records = []

    origin_system = servicedesk_data[
        "export_meta"
    ]["system"]

    tickets = servicedesk_data["tickets"]

    for position, ticket in enumerate(tickets, start=1):

        artefact = ticket.get("artefact", {})

        raw_date = clean_optional(
            ticket.get("closed_at")
        )

        raw_status = clean_optional(
            ticket.get("state")
        )

        canonical = CanonicalEvidence(
            observation_id=f"servicedesk:{position:04d}",

            source_dataset="servicedesk",
            source_position=position,
            origin_system=origin_system,
            source_record_id=ticket["ticket_ref"],

            obligation_id=clean_optional(
                ticket.get("linked_control")
            ),
            evidence_type=clean_optional(
                artefact.get("kind")
            ),
            title=clean_optional(
                ticket.get("summary")
            ),

            event_date=parse_event_date(
                "servicedesk",
                raw_date
            ),
            date_basis="closed_at",
            raw_date_value=raw_date,

            raw_status=raw_status,
            normalized_status=normalize_status(
                "servicedesk",
                raw_status
            ),

            owner=clean_optional(
                ticket.get("raised_by")
            ),
            version=clean_optional(
                artefact.get("revision")
            ),
            digest=clean_optional(
                artefact.get("checksum")
            ),

            source_category=clean_optional(
                ticket.get("category")
            ),
        )

        canonical_records.append(canonical)

    return canonical_records

def normalize_all_evidence(
    evidence_records,
    registry_records,
    servicedesk_data,
):
    """
    Normalize all three sources into one canonical collection.
    """

    canonical_records = []

    canonical_records.extend(
        normalize_evidence_csv(evidence_records)
    )

    canonical_records.extend(
        normalize_registry(registry_records)
    )

    canonical_records.extend(
        normalize_servicedesk(servicedesk_data)
    )

    return canonical_records

def describe_schema():
    """Print the Phase 2 canonical design for manual review."""

    print("\n========== CANONICAL EVIDENCE DESIGN ==========\n")

    print("Normalized status vocabulary:")
    for status in NORMALIZED_STATUSES:
        print(f"  - {status}")

    print("\nSource mappings:")

    for source_name in sorted(SOURCE_FIELD_MAPS):
        print(f"\n{source_name}")

        for canonical_field, source_field in (
            SOURCE_FIELD_MAPS[source_name].items()
        ):
            print(
                f"  {canonical_field:<20} <- {source_field}"
            )

    print("\n===============================================\n")


if __name__ == "__main__":
    describe_schema()
