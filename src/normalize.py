from dataclasses import dataclass
from datetime import date
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
    evidence_date: Optional[date]
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
