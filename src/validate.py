from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Optional

from normalize import CanonicalEvidence


@dataclass(frozen=True)
class DataQualityIssue:
    issue_id: str
    observation_id: str
    source_record_id: str
    source_dataset: str

    issue_type: str
    severity: str
    field_name: Optional[str]

    message: str
    suggested_treatment: str


def create_issue(
    record,
    issue_type,
    severity,
    field_name,
    message,
    suggested_treatment,
):
    """Create a deterministic data-quality issue."""

    field_key = field_name or "record"

    return DataQualityIssue(
        issue_id=(
            f"{record.observation_id}:"
            f"{issue_type}:"
            f"{field_key}"
        ),
        observation_id=record.observation_id,
        source_record_id=record.source_record_id,
        source_dataset=record.source_dataset,
        issue_type=issue_type,
        severity=severity,
        field_name=field_name,
        message=message,
        suggested_treatment=suggested_treatment,
    )


def validate_evidence(
    canonical_records,
    obligations_data,
    methodology,
):

    issues = []

    obligations = {
        obligation["obligation_id"]: obligation
        for obligation in obligations_data["obligations"]
    }

    as_at_date = date.fromisoformat(
        methodology["evidence_rules"]["as_at_date"]
    )


    field_rules = (
        (
            "source_record_id",
            "ERROR",
            "EXCLUDE_FROM_SCORING",
        ),
        (
            "obligation_id",
            "ERROR",
            "EXCLUDE_FROM_SCORING",
        ),
        (
            "evidence_type",
            "ERROR",
            "EXCLUDE_FROM_SCORING",
        ),
        (
            "title",
            "WARNING",
            "REVIEW",
        ),
        (
            "event_date",
            "WARNING",
            "SUSPECT",
        ),
        (
            "raw_status",
            "ERROR",
            "REVIEW",
        ),
        (
            "owner",
            "WARNING",
            "REVIEW",
        ),
        (
            "version",
            "WARNING",
            "REVIEW",
        ),
        (
            "digest",
            "WARNING",
            "REVIEW",
        ),
    )

    for record in canonical_records:

        # ---------------------------------------------
        # Missing fields
        # ---------------------------------------------

        for field_name, severity, treatment in field_rules:

            value = getattr(record, field_name)

            if value is None or value == "":

                issues.append(
                    create_issue(
                        record=record,
                        issue_type="MISSING_FIELD",
                        severity=severity,
                        field_name=field_name,
                        message=(
                            f"Required or important field "
                            f"'{field_name}' is missing."
                        ),
                        suggested_treatment=treatment,
                    )
                )

        # ---------------------------------------------
        # Obligation reference exists?
        # ---------------------------------------------

        if (
            record.obligation_id is not None
            and record.obligation_id not in obligations
        ):
            issues.append(
                create_issue(
                    record=record,
                    issue_type="UNKNOWN_OBLIGATION",
                    severity="ERROR",
                    field_name="obligation_id",
                    message=(
                        f"Evidence references "
                        f"'{record.obligation_id}', but that "
                        f"obligation does not exist in the "
                        f"authoritative obligation set."
                    ),
                    suggested_treatment="EXCLUDE_FROM_SCORING",
                )
            )

        # ---------------------------------------------
        # Evidence type matches obligation?
        # ---------------------------------------------

        if (
            record.obligation_id in obligations
            and record.evidence_type is not None
        ):

            required_types = obligations[
                record.obligation_id
            ]["required_evidence_types"]

            if record.evidence_type not in required_types:

                issues.append(
                    create_issue(
                        record=record,
                        issue_type="EVIDENCE_TYPE_MISMATCH",
                        severity="WARNING",
                        field_name="evidence_type",
                        message=(
                            f"Evidence type "
                            f"'{record.evidence_type}' does not "
                            f"match the required evidence type(s) "
                            f"for {record.obligation_id}: "
                            f"{required_types}."
                        ),
                        suggested_treatment="REVIEW",
                    )
                )

        # ---------------------------------------------
        # Unknown status
        # ---------------------------------------------

        if (
            record.raw_status is not None
            and record.normalized_status == "UNKNOWN"
        ):
            issues.append(
                create_issue(
                    record=record,
                    issue_type="UNKNOWN_STATUS",
                    severity="ERROR",
                    field_name="raw_status",
                    message=(
                        f"Source status '{record.raw_status}' "
                        f"has no defined normalization mapping."
                    ),
                    suggested_treatment="REVIEW",
                )
            )

        # ---------------------------------------------
        # Future-dated evidence
        # ---------------------------------------------

        if (
            record.event_date is not None
            and record.event_date > as_at_date
        ):
            issues.append(
                create_issue(
                    record=record,
                    issue_type="FUTURE_DATE",
                    severity="WARNING",
                    field_name="event_date",
                    message=(
                        f"Event date {record.event_date.isoformat()} "
                        f"is after the assessment as-at date "
                        f"{as_at_date.isoformat()}."
                    ),
                    suggested_treatment="SUSPECT",
                )
            )

    # -------------------------------------------------
    # Reused source record IDs
    # -------------------------------------------------

    source_id_counts = Counter(
        (
            record.source_dataset,
            record.source_record_id,
        )
        for record in canonical_records
        if record.source_record_id
    )

    duplicate_source_ids = {
        key
        for key, count in source_id_counts.items()
        if count > 1
    }

    for record in canonical_records:

        key = (
            record.source_dataset,
            record.source_record_id,
        )

        if key in duplicate_source_ids:

            issues.append(
                create_issue(
                    record=record,
                    issue_type="DUPLICATE_SOURCE_RECORD_ID",
                    severity="WARNING",
                    field_name="source_record_id",
                    message=(
                        f"Source record ID "
                        f"'{record.source_record_id}' occurs "
                        f"more than once in "
                        f"{record.source_dataset}."
                    ),
                    suggested_treatment="REVIEW",
                )
            )


    issues.sort(
        key=lambda issue: (
            issue.source_dataset,
            issue.observation_id,
            issue.issue_type,
            issue.field_name or "",
        )
    )

    return issues
