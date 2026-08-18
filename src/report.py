import hashlib
import json
from decimal import Decimal
from pathlib import Path

from database import build_provisional_run_id


REPORT_SCHEMA_VERSION = "1.0.0"


def _sorted_by(items, attribute):

    return sorted(items, key=lambda item: getattr(item, attribute))


def format_decimal(value, decimal_places=None):
    decimal_value = Decimal(str(value))

    if decimal_places is not None:
        decimal_value = decimal_value.quantize(
            Decimal("1").scaleb(-decimal_places)
        )
        return format(decimal_value, f".{decimal_places}f")

    return format(decimal_value, "f")


def canonical_evidence_to_dict(record):

    return {
        "observation_id": record.observation_id,
        "source_dataset": record.source_dataset,
        "source_position": record.source_position,
        "origin_system": record.origin_system,
        "source_record_id": record.source_record_id,
        "obligation_id": record.obligation_id,
        "evidence_type": record.evidence_type,
        "title": record.title,
        "event_date": record.event_date.isoformat()
        if record.event_date is not None
        else None,
        "date_basis": record.date_basis,
        "raw_date_value": record.raw_date_value,
        "raw_status": record.raw_status,
        "normalized_status": record.normalized_status,
        "owner": record.owner,
        "version": record.version,
        "digest": record.digest,
        "source_category": record.source_category,
    }


def quality_issue_to_dict(issue):
    return {
        "issue_id": issue.issue_id,
        "observation_id": issue.observation_id,
        "source_record_id": issue.source_record_id,
        "source_dataset": issue.source_dataset,
        "issue_type": issue.issue_type,
        "severity": issue.severity,
        "field_name": issue.field_name,
        "message": issue.message,
        "review_required": issue.review_required,
        "assessment_action": issue.assessment_action,
    }


def reconciliation_group_to_dict(group):
    """Serialize a repeated-digest group and all source relationships."""

    return {
        "group_id": group.group_id,
        "digest": group.digest,
        "observation_ids": sorted(group.observation_ids),
        "source_record_ids": sorted(group.source_record_ids),
        "source_datasets": sorted(group.source_datasets),
        "obligation_ids": sorted(group.obligation_ids),
        "evidence_types": sorted(group.evidence_types),
        "normalized_statuses": sorted(group.normalized_statuses),
        "titles": sorted(group.titles),
        "versions": sorted(group.versions),
        "group_type": group.group_type,
        "review_required": group.review_required,
        "assessment_handling": group.assessment_handling,
        "message": group.message,
    }


def evidence_evaluation_to_dict(evaluation):
    """Serialize one existing Phase 6 logical evidence decision."""

    return {
        "assessment_unit_id": evaluation.assessment_unit_id,
        "obligation_id": evaluation.obligation_id,
        "observation_ids": sorted(evaluation.observation_ids),
        "source_record_ids": sorted(evaluation.source_record_ids),
        "source_datasets": sorted(evaluation.source_datasets),
        "digest": evaluation.digest,
        "evidence_types": sorted(evaluation.evidence_types),
        "normalized_statuses": sorted(evaluation.normalized_statuses),
        "event_dates": sorted(evaluation.event_dates),
        "reconciliation_type": evaluation.reconciliation_type,
        "type_matches": evaluation.type_matches,
        "date_state": evaluation.date_state,
        "status_state": evaluation.status_state,
        "qualifies_for_met": evaluation.qualifies_for_met,
        "supports_partial": evaluation.supports_partial,
        "review_required": evaluation.review_required,
        "decision_basis": evaluation.decision_basis,
        "reasons": sorted(evaluation.reasons),
    }


def obligation_assessment_to_dict(assessment):
    """Serialize one existing Phase 6 obligation result."""

    evaluations = _sorted_by(
        assessment.evidence_evaluations,
        "assessment_unit_id",
    )

    return {
        "obligation_id": assessment.obligation_id,
        "dimension": assessment.dimension,
        "status": assessment.status,
        "review_required": assessment.review_required,
        "reason": assessment.reason,
        "qualifying_unit_ids": sorted(assessment.qualifying_unit_ids),
        "partial_unit_ids": sorted(assessment.partial_unit_ids),
        "evidence_evaluations": [
            evidence_evaluation_to_dict(evaluation)
            for evaluation in evaluations
        ],
    }


def dimension_assessment_to_dict(assessment):

    contributions = _sorted_by(
        assessment.obligation_contributions,
        "obligation_id",
    )

    return {
        "dimension_code": assessment.dimension_code,
        "dimension_name": assessment.dimension_name,
        "weight": format_decimal(assessment.weight, 2),
        "score": format_decimal(assessment.score, 2),
        "dimension_status": assessment.dimension_status,
        "review_required": assessment.review_required,
        "met_count": assessment.met_count,
        "partial_count": assessment.partial_count,
        "not_met_count": assessment.not_met_count,
        "earned_points": format_decimal(assessment.earned_points),
        "maximum_points": format_decimal(assessment.maximum_points),
        "reason": assessment.reason,
        "obligation_contributions": [
            {
                "obligation_id": contribution.obligation_id,
                "obligation_status": contribution.obligation_status,
                "contribution": format_decimal(contribution.contribution),
                "review_required": contribution.review_required,
            }
            for contribution in contributions
        ],
    }


def build_assessment_report(
    obligations_data,
    methodology,
    canonical_records,
    quality_issues,
    reconciliation_groups,
    obligation_assessments,
    dimension_assessments,
):
    """Build the complete deterministic assessment as plain data."""

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "assessment": {
            "provisional_run_id": build_provisional_run_id(
                obligations_data,
                methodology,
            ),
            "methodology_version": methodology["methodology_version"],
            "obligation_set_version": obligations_data[
                "obligation_set_version"
            ],
            "as_at_date": methodology["evidence_rules"]["as_at_date"],
            "staleness_threshold_days": methodology["evidence_rules"][
                "staleness_threshold_days"
            ],
        },
        "dimensions": [
            dimension_assessment_to_dict(assessment)
            for assessment in _sorted_by(
                dimension_assessments, "dimension_code"
            )
        ],
        "obligations": [
            obligation_assessment_to_dict(assessment)
            for assessment in _sorted_by(
                obligation_assessments, "obligation_id"
            )
        ],
        "reconciliation_groups": [
            reconciliation_group_to_dict(group)
            for group in _sorted_by(reconciliation_groups, "group_id")
        ],
        "data_quality_issues": [
            quality_issue_to_dict(issue)
            for issue in _sorted_by(quality_issues, "issue_id")
        ],
        "evidence_observations": [
            canonical_evidence_to_dict(record)
            for record in _sorted_by(canonical_records, "observation_id")
        ],
    }


def serialize_report(report):
    """Return the canonical UTF-8 JSON byte stream."""

    text = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    return text.encode("utf-8")


def write_assessment_report(report, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(serialize_report(report))
    return output_path


def sha256_bytes(data):
    """Return the SHA-256 digest of canonical report bytes."""

    return hashlib.sha256(data).hexdigest()
