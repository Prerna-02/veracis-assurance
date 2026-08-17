from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class EvidenceEvaluation:
    """Record how one logical artefact was evaluated for an obligation."""

    assessment_unit_id: str
    obligation_id: str

    observation_ids: tuple[str, ...]
    source_record_ids: tuple[str, ...]
    source_datasets: tuple[str, ...]

    digest: Optional[str]

    evidence_types: tuple[str, ...]
    normalized_statuses: tuple[str, ...]
    event_dates: tuple[str, ...]

    reconciliation_type: Optional[str]

    type_matches: bool
    date_state: str
    status_state: str

    qualifies_for_met: bool
    supports_partial: bool

    review_required: bool
    decision_basis: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ObligationAssessment:
    """Store one deterministic result for an authoritative obligation."""

    obligation_id: str
    dimension: str
    status: str

    review_required: bool

    evidence_evaluations: tuple[EvidenceEvaluation, ...]
    qualifying_unit_ids: tuple[str, ...]
    partial_unit_ids: tuple[str, ...]

    reason: str


def _sorted_values(records, field_name):
    """Return deterministic unique non-empty values from observations."""

    values = set()

    for record in records:
        value = getattr(record, field_name)

        if value is not None and value != "":
            values.add(value)

    return tuple(sorted(values))


def evaluate_date_state(
    records,
    as_at_date,
    staleness_threshold_days,
):
    """Classify artefact dates using the fixed methodology date."""

    event_dates = [record.event_date for record in records]

    if not event_dates or any(
        event_date is None
        for event_date in event_dates
    ):
        return "MISSING_DATE"

    date_states = set()

    for event_date in event_dates:
        if event_date > as_at_date:
            date_states.add("FUTURE_DATE")
        elif (
            as_at_date - event_date
        ).days > staleness_threshold_days:
            date_states.add("STALE")
        else:
            date_states.add("CURRENT")

    if len(date_states) > 1:
        return "DATE_CONFLICT"

    return next(iter(date_states))


def evaluate_status_state(records):
    """Return the agreed normalized status or surface a conflict."""

    statuses = _sorted_values(records, "normalized_status")

    if not statuses:
        return "UNKNOWN"

    if len(statuses) > 1:
        return "CONFLICT"

    return statuses[0]


def build_assessment_units(
    canonical_records,
    reconciliation_groups,
):
    """Build one unit per repeated digest or singleton observation."""

    records_by_id = {
        record.observation_id: record
        for record in canonical_records
    }
    grouped_observation_ids = set()
    assessment_units = []

    for group in sorted(
        reconciliation_groups,
        key=lambda item: item.group_id,
    ):
        records = tuple(
            records_by_id[observation_id]
            for observation_id in group.observation_ids
            if observation_id in records_by_id
        )

        if not records:
            continue

        grouped_observation_ids.update(
            record.observation_id
            for record in records
        )

        assessment_units.append(
            {
                "assessment_unit_id": f"artefact:{group.digest}",
                "digest": group.digest,
                "records": records,
                "reconciliation_group": group,
            }
        )

    for record in sorted(
        canonical_records,
        key=lambda item: item.observation_id,
    ):
        if record.observation_id in grouped_observation_ids:
            continue

        assessment_units.append(
            {
                "assessment_unit_id": (
                    f"observation:{record.observation_id}"
                ),
                "digest": record.digest,
                "records": (record,),
                "reconciliation_group": None,
            }
        )

    assessment_units.sort(
        key=lambda unit: unit["assessment_unit_id"]
    )

    return tuple(assessment_units)


def _issues_for_records(records, issues_by_observation_id):
    """Collect Phase 4 issues attached to an assessment unit."""

    issues_by_id = {}

    for record in records:
        for issue in issues_by_observation_id.get(
            record.observation_id,
            (),
        ):
            issues_by_id[issue.issue_id] = issue

    return tuple(
        issues_by_id[issue_id]
        for issue_id in sorted(issues_by_id)
    )


def evaluate_evidence_unit(
    unit,
    obligation,
    methodology,
    issues_by_observation_id,
):
    """Apply methodology and documented policies to one logical artefact."""

    records = unit["records"]
    reconciliation_group = unit["reconciliation_group"]
    obligation_id = obligation["obligation_id"]
    required_types = tuple(
        sorted(obligation["required_evidence_types"])
    )

    evidence_rules = methodology["evidence_rules"]
    as_at_date = date.fromisoformat(
        evidence_rules["as_at_date"]
    )
    staleness_threshold_days = evidence_rules[
        "staleness_threshold_days"
    ]
    evidence_must_match_type = evidence_rules[
        "evidence_must_match_required_type"
    ]

    observation_ids = _sorted_values(records, "observation_id")
    source_record_ids = _sorted_values(
        records,
        "source_record_id",
    )
    source_datasets = _sorted_values(records, "source_dataset")
    evidence_types = _sorted_values(records, "evidence_type")
    normalized_statuses = _sorted_values(
        records,
        "normalized_status",
    )
    event_dates = tuple(
        sorted(
            {
                record.event_date.isoformat()
                for record in records
                if record.event_date is not None
            }
        )
    )

    date_state = evaluate_date_state(
        records,
        as_at_date,
        staleness_threshold_days,
    )
    status_state = evaluate_status_state(records)

    missing_evidence_type = any(
        record.evidence_type is None
        for record in records
    )
    supplied_types_match = (
        bool(evidence_types)
        and all(
            evidence_type in required_types
            for evidence_type in evidence_types
        )
    )
    type_matches = (
        supplied_types_match
        and not missing_evidence_type
    )
    type_requirement_satisfied = (
        type_matches
        or not evidence_must_match_type
    )
    methodology_type_mismatch = (
        evidence_must_match_type
        and bool(evidence_types)
        and not supplied_types_match
    )

    linked_obligation_ids = _sorted_values(
        records,
        "obligation_id",
    )
    missing_obligation_id = any(
        record.obligation_id is None
        for record in records
    )
    obligation_link_matches = (
        linked_obligation_ids == (obligation_id,)
        and not missing_obligation_id
    )
    core_metadata_conflict = (
        not obligation_link_matches
        or len(evidence_types) > 1
        or missing_evidence_type
    )

    quality_issues = _issues_for_records(
        records,
        issues_by_observation_id,
    )
    excluded_observation_ids = {
        issue.observation_id
        for issue in quality_issues
        if issue.assessment_action
        == "EXCLUDE_FROM_ASSESSMENT"
    }
    excluded_by_quality = all(
        observation_id in excluded_observation_ids
        for observation_id in observation_ids
    )

    reconciliation_type = (
        reconciliation_group.group_type
        if reconciliation_group is not None
        else None
    )
    status_conflict = (
        status_state == "CONFLICT"
        or reconciliation_type in {
            "CONTRADICTORY_STATUS",
            "STATUS_AND_METADATA_CONFLICT",
        }
    )

    status_qualifies_for_met = status_state == "APPROVED"

    qualifies_for_met = all(
        (
            obligation_link_matches,
            type_requirement_satisfied,
            status_qualifies_for_met,
            date_state == "CURRENT",
            not status_conflict,
            not core_metadata_conflict,
            not excluded_by_quality,
        )
    )

    methodology_partial = (
        date_state == "STALE"
        or status_state == "DRAFT"
        or methodology_type_mismatch
    )
    engineering_status_states = {
        "AWAITING_SIGNOFF",
        "APPROVED_RETROSPECTIVELY",
        "SUPERSEDED",
        "UNKNOWN",
        "CONFLICT",
    }
    engineering_date_states = {
        "MISSING_DATE",
        "FUTURE_DATE",
        "DATE_CONFLICT",
    }
    engineering_partial = (
        date_state in engineering_date_states
        or status_state in engineering_status_states
        or core_metadata_conflict
        or missing_evidence_type
    )

    supports_partial = (
        not qualifies_for_met
        and not excluded_by_quality
        and (methodology_partial or engineering_partial)
    )
    decision_basis = (
        "ENGINEERING_POLICY"
        if excluded_by_quality or engineering_partial
        else "METHODOLOGY"
    )

    review_required = (
        any(issue.review_required for issue in quality_issues)
        or (
            reconciliation_group is not None
            and reconciliation_group.review_required
        )
        or engineering_partial
        or methodology_type_mismatch
    )

    reasons = set()

    for issue in quality_issues:
        reasons.add(
            f"Data quality {issue.issue_type}: {issue.message}"
        )

    if reconciliation_group is not None:
        reasons.add(
            f"Reconciliation {reconciliation_type}: "
            f"{reconciliation_group.message}"
        )

    if type_matches:
        reasons.add(
            "Evidence type matches the obligation's required type."
        )
    elif missing_evidence_type:
        reasons.add(
            "At least one observation has no evidence type; the type "
            "requirement cannot be established."
        )
    else:
        reasons.add(
            "Evidence type does not match the obligation's required type."
        )

    if not obligation_link_matches:
        reasons.add(
            "The unit does not link exclusively to this authoritative "
            "obligation."
        )

    date_reasons = {
        "CURRENT": (
            "All supplied event dates are current under the methodology."
        ),
        "STALE": (
            "All supplied event dates exceed the methodology staleness "
            "threshold."
        ),
        "MISSING_DATE": (
            "At least one event date is missing, so currency cannot be "
            "established."
        ),
        "FUTURE_DATE": (
            "The event date is after the methodology as-at date and cannot "
            "establish the position at that date."
        ),
        "DATE_CONFLICT": (
            "The observations produce conflicting freshness states; no "
            "date was selected as authoritative."
        ),
    }
    reasons.add(date_reasons[date_state])

    if status_state == "CONFLICT":
        reasons.add(
            "Normalized statuses conflict; no status was selected as "
            "authoritative."
        )
    elif status_state == "APPROVED_RETROSPECTIVELY":
        reasons.add(
            "Retrospective approval is not equivalent to ordinary approval; "
            "release timing requires institutional confirmation."
        )
    elif status_state == "SUPERSEDED":
        reasons.add(
            "Superseded evidence cannot prove a current approved state; its "
            "methodology treatment requires institutional confirmation."
        )
    else:
        reasons.add(
            f"Effective normalized status is {status_state}."
        )

    if excluded_by_quality:
        reasons.add(
            "All observations in this unit are excluded from assessment by "
            "Phase 4 data-quality policy."
        )
    elif qualifies_for_met:
        reasons.add(
            "The unit is approved, current, type-matching, and free of core "
            "status or metadata conflicts."
        )
    elif supports_partial and decision_basis == "ENGINEERING_POLICY":
        reasons.add(
            "The unit supports PARTIAL under a conservative engineering "
            "policy for a condition not explicitly resolved by the "
            "methodology."
        )
    elif supports_partial:
        reasons.add(
            "The unit supports PARTIAL under the supplied methodology."
        )

    return EvidenceEvaluation(
        assessment_unit_id=unit["assessment_unit_id"],
        obligation_id=obligation_id,
        observation_ids=observation_ids,
        source_record_ids=source_record_ids,
        source_datasets=source_datasets,
        digest=unit["digest"],
        evidence_types=evidence_types,
        normalized_statuses=normalized_statuses,
        event_dates=event_dates,
        reconciliation_type=reconciliation_type,
        type_matches=type_matches,
        date_state=date_state,
        status_state=status_state,
        qualifies_for_met=qualifies_for_met,
        supports_partial=supports_partial,
        review_required=review_required,
        decision_basis=decision_basis,
        reasons=tuple(sorted(reasons)),
    )


def assess_single_obligation(
    obligation,
    assessment_units,
    methodology,
    issues_by_observation_id,
):
    """Assess one obligation using the required MET-first priority."""

    obligation_id = obligation["obligation_id"]
    evidence_evaluations = []

    for unit in assessment_units:
        if not any(
            record.obligation_id == obligation_id
            for record in unit["records"]
        ):
            continue

        evidence_evaluations.append(
            evaluate_evidence_unit(
                unit,
                obligation,
                methodology,
                issues_by_observation_id,
            )
        )

    evidence_evaluations.sort(
        key=lambda evaluation: evaluation.assessment_unit_id
    )
    evidence_evaluations = tuple(evidence_evaluations)

    qualifying_unit_ids = tuple(
        evaluation.assessment_unit_id
        for evaluation in evidence_evaluations
        if evaluation.qualifies_for_met
    )
    partial_unit_ids = tuple(
        evaluation.assessment_unit_id
        for evaluation in evidence_evaluations
        if evaluation.supports_partial
    )

    if qualifying_unit_ids:
        status = "MET"
        reason = (
            "At least one logical evidence unit is approved, current, "
            "type-matching, and eligible for MET: "
            f"{', '.join(qualifying_unit_ids)}."
        )
    elif partial_unit_ids:
        status = "PARTIAL"
        reason = (
            "No evidence unit qualifies for MET; the following units "
            "support PARTIAL: "
            f"{', '.join(partial_unit_ids)}."
        )
    else:
        status = "NOT_MET"
        reason = (
            "No usable logical evidence unit qualifies for MET or supports "
            "PARTIAL."
        )

    return ObligationAssessment(
        obligation_id=obligation_id,
        dimension=obligation["dimension"],
        status=status,
        review_required=any(
            evaluation.review_required
            for evaluation in evidence_evaluations
        ),
        evidence_evaluations=evidence_evaluations,
        qualifying_unit_ids=qualifying_unit_ids,
        partial_unit_ids=partial_unit_ids,
        reason=reason,
    )


def assess_obligations(
    canonical_records,
    obligations_data,
    methodology,
    quality_issues,
    reconciliation_groups,
):
    """Assess every authoritative obligation in deterministic order."""

    obligations = {
        obligation["obligation_id"]: obligation
        for obligation in obligations_data["obligations"]
    }
    assessment_units = build_assessment_units(
        canonical_records,
        reconciliation_groups,
    )

    issues_by_observation_id = {}

    for issue in quality_issues:
        issues_by_observation_id.setdefault(
            issue.observation_id,
            [],
        ).append(issue)

    assessments = [
        assess_single_obligation(
            obligations[obligation_id],
            assessment_units,
            methodology,
            issues_by_observation_id,
        )
        for obligation_id in sorted(obligations)
    ]

    return assessments
