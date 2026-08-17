from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciliationGroup:

    group_id: str
    digest: str

    observation_ids: tuple[str, ...]
    source_record_ids: tuple[str, ...]
    source_datasets: tuple[str, ...]

    obligation_ids: tuple[str, ...]
    evidence_types: tuple[str, ...]
    normalized_statuses: tuple[str, ...]
    titles: tuple[str, ...]
    versions: tuple[str, ...]

    group_type: str
    review_required: bool
    assessment_handling: str
    message: str


def normalize_text(value):
    """Normalize text only enough for deterministic metadata comparison."""

    if value is None:
        return ""

    return " ".join(str(value).split()).casefold()


def _sorted_values(records, field_name):
    """Return sorted unique non-empty values for a canonical field."""

    values = set()

    for record in records:
        value = getattr(record, field_name)

        if value is not None and value != "":
            values.add(value)

    return tuple(sorted(values))


def group_records_by_digest(canonical_records):

    grouped_records = {}

    for record in canonical_records:
        if record.digest is None or record.digest.strip() == "":
            continue

        grouped_records.setdefault(
            record.digest,
            [],
        ).append(record)

    return {
        digest: tuple(
            sorted(
                records,
                key=lambda record: record.observation_id,
            )
        )
        for digest, records in sorted(grouped_records.items())
        if len(records) >= 2
    }


def find_metadata_differences(records):

    differing_fields = []

    for field_name in (
        "obligation_id",
        "evidence_type",
        "version",
    ):
        if len(_sorted_values(records, field_name)) > 1:
            differing_fields.append(field_name)

    normalized_titles = set()

    for record in records:
        normalized_title = normalize_text(record.title)

        if normalized_title:
            normalized_titles.add(normalized_title)

    if len(normalized_titles) > 1:
        differing_fields.append("title")

    return tuple(sorted(differing_fields))


def classify_group(records):  

    status_conflict = (
        len(_sorted_values(records, "normalized_status")) > 1
    )
    metadata_differences = find_metadata_differences(records)

    if status_conflict and metadata_differences:
        fields = ", ".join(metadata_differences)
        return (
            "STATUS_AND_METADATA_CONFLICT",
            True,
            "REVIEW_BEFORE_ASSESSMENT",
            (
                "Observations sharing this digest disagree on normalized "
                f"status and metadata fields: {fields}. No observation was "
                "selected as authoritative."
            ),
        )

    if status_conflict:
        return (
            "CONTRADICTORY_STATUS",
            True,
            "REVIEW_BEFORE_ASSESSMENT",
            (
                "Observations sharing this digest disagree on normalized "
                "status. No source precedence or reliable status sequencing "
                "rule is defined."
            ),
        )

    if metadata_differences:
        fields = ", ".join(metadata_differences)
        return (
            "METADATA_INCONSISTENCY",
            True,
            "REVIEW_BEFORE_ASSESSMENT",
            (
                "Observations sharing this digest disagree on metadata "
                f"fields: {fields}. No metadata value was selected as "
                "authoritative."
            ),
        )

    return (
        "CONSISTENT_DUPLICATE",
        False,
        "COUNT_AS_ONE_ARTEFACT",
        (
            "Multiple source observations share this digest and agree on "
            "important assessment metadata. Treat them as one artefact for "
            "assessment without removing their source provenance."
        ),
    )


def reconcile_evidence(canonical_records):
    """Build deterministic reconciliation results for repeated digests."""

    reconciliation_groups = []

    for digest, records in group_records_by_digest(
        canonical_records
    ).items():
        (
            group_type,
            review_required,
            assessment_handling,
            message,
        ) = classify_group(records)

        reconciliation_groups.append(
            ReconciliationGroup(
                group_id=f"digest:{digest}",
                digest=digest,
                observation_ids=_sorted_values(
                    records,
                    "observation_id",
                ),
                source_record_ids=_sorted_values(
                    records,
                    "source_record_id",
                ),
                source_datasets=_sorted_values(
                    records,
                    "source_dataset",
                ),
                obligation_ids=_sorted_values(
                    records,
                    "obligation_id",
                ),
                evidence_types=_sorted_values(
                    records,
                    "evidence_type",
                ),
                normalized_statuses=_sorted_values(
                    records,
                    "normalized_status",
                ),
                titles=_sorted_values(
                    records,
                    "title",
                ),
                versions=_sorted_values(
                    records,
                    "version",
                ),
                group_type=group_type,
                review_required=review_required,
                assessment_handling=assessment_handling,
                message=message,
            )
        )

    reconciliation_groups.sort(
        key=lambda group: group.group_id
    )

    return reconciliation_groups
