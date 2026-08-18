"""Focused tests for deterministic obligation assessment rules."""

from datetime import date
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from assess import evaluate_evidence_unit, assess_single_obligation
from normalize import CanonicalEvidence
from reconcile import reconcile_evidence


METHODOLOGY = {
    "evidence_rules": {
        "as_at_date": "2026-08-01",
        "staleness_threshold_days": 365,
        "evidence_must_match_required_type": True,
    }
}
OBLIGATION = {
    "obligation_id": "OBL-TEST",
    "dimension": "TST",
    "required_evidence_types": ["policy"],
}


def make_record(
    observation_number=1,
    normalized_status="APPROVED",
    event_date=date(2026, 7, 1),
    evidence_type="policy",
    digest="digest-test",
):
    return CanonicalEvidence(
        observation_id=f"synthetic:{observation_number:04d}",
        source_dataset="synthetic",
        source_position=observation_number,
        origin_system="Synthetic System",
        source_record_id=f"SYN-{observation_number:04d}",
        obligation_id="OBL-TEST",
        evidence_type=evidence_type,
        title="Synthetic evidence",
        event_date=event_date,
        date_basis="event_date",
        raw_date_value=event_date.isoformat() if event_date else None,
        raw_status=normalized_status,
        normalized_status=normalized_status,
        owner="Owner",
        version="1.0",
        digest=digest,
    )


def evaluate_single(record):
    unit = {
        "assessment_unit_id": f"observation:{record.observation_id}",
        "digest": record.digest,
        "records": (record,),
        "reconciliation_group": None,
    }
    return evaluate_evidence_unit(unit, OBLIGATION, METHODOLOGY, {})


def test_current_approved_type_matching_evidence_qualifies_for_met():
    evaluation = evaluate_single(make_record())

    assert evaluation.type_matches is True
    assert evaluation.date_state == "CURRENT"
    assert evaluation.status_state == "APPROVED"
    assert evaluation.qualifies_for_met is True
    assert evaluation.supports_partial is False


@pytest.mark.parametrize(
    "status,event_date_value,evidence_type,date_state,status_state",
    (
        ("DRAFT", date(2026, 7, 1), "policy", "CURRENT", "DRAFT"),
        ("APPROVED", date(2025, 1, 1), "policy", "STALE", "APPROVED"),
        ("APPROVED", date(2026, 7, 1), "wrong_type", "CURRENT", "APPROVED"),
        ("APPROVED", None, "policy", "MISSING_DATE", "APPROVED"),
        ("APPROVED", date(2026, 8, 2), "policy", "FUTURE_DATE", "APPROVED"),
        ("APPROVED_RETROSPECTIVELY", date(2026, 7, 1), "policy",
         "CURRENT", "APPROVED_RETROSPECTIVELY"),
    ),
)
def test_nonqualifying_evidence_supports_partial_conservatively(
    status, event_date_value, evidence_type, date_state, status_state
):
    evaluation = evaluate_single(
        make_record(
            normalized_status=status,
            event_date=event_date_value,
            evidence_type=evidence_type,
        )
    )

    assert evaluation.date_state == date_state
    assert evaluation.status_state == status_state
    assert evaluation.qualifies_for_met is False
    assert evaluation.supports_partial is True


def test_no_evidence_produces_not_met():
    assessment = assess_single_obligation(OBLIGATION, (), METHODOLOGY, {})

    assert assessment.status == "NOT_MET"
    assert assessment.evidence_evaluations == ()


def test_contradictory_status_cannot_qualify_and_requires_review():
    approved = make_record(
        observation_number=1,
        normalized_status="APPROVED",
        digest="shared-digest",
    )
    draft = make_record(
        observation_number=2,
        normalized_status="DRAFT",
        digest="shared-digest",
    )
    reconciliation_group = reconcile_evidence([approved, draft])[0]
    unit = {
        "assessment_unit_id": "artefact:shared-digest",
        "digest": "shared-digest",
        "records": (approved, draft),
        "reconciliation_group": reconciliation_group,
    }

    evaluation = evaluate_evidence_unit(unit, OBLIGATION, METHODOLOGY, {})

    assert reconciliation_group.group_type == "CONTRADICTORY_STATUS"
    assert evaluation.status_state == "CONFLICT"
    assert evaluation.qualifies_for_met is False
    assert evaluation.supports_partial is True
    assert evaluation.review_required is True
