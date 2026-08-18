"""Independent tests for Phase 7 dimension scoring."""

from decimal import Decimal
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from assess import ObligationAssessment
from score import (
    calculate_dimension,
    contribution_for_status,
    determine_dimension_status,
)


METHODOLOGY = {
    "dimension_score_definition": (
        "Percentage of obligations in the dimension that are MET, "
        "with PARTIAL counting as one half."
    ),
    "dimension_status_bands": {
        "GREEN": "80.0 and above",
        "AMBER": "50.0 up to but not including 80.0",
        "RED": "below 50.0",
    },
}


def make_assessment(index, status):
    return ObligationAssessment(
        obligation_id=f"OBL-{index:03d}",
        dimension="TST",
        status=status,
        review_required=False,
        evidence_evaluations=(),
        qualifying_unit_ids=(),
        partial_unit_ids=(),
        reason="Synthetic scoring fixture.",
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        ("MET", Decimal("1.0")),
        ("PARTIAL", Decimal("0.5")),
        ("NOT_MET", Decimal("0.0")),
    ),
)
def test_obligation_status_contributions(status, expected):
    assert contribution_for_status(status, METHODOLOGY) == expected


@pytest.mark.parametrize(
    ("statuses", "expected_score"),
    (
        (("MET", "PARTIAL", "PARTIAL"), "66.67"),
        (("MET", "PARTIAL", "MET"), "83.33"),
        (("MET", "PARTIAL"), "75.00"),
        (("MET",), "100.00"),
    ),
)
def test_dimension_score_examples(statuses, expected_score):
    assessments = tuple(
        make_assessment(index, status)
        for index, status in enumerate(statuses, 1)
    )

    result = calculate_dimension(
        "TST",
        {"name": "Test Dimension", "weight": 0.20},
        assessments,
        METHODOLOGY,
    )

    assert result.score == expected_score


@pytest.mark.parametrize(
    ("score", "expected_status"),
    (
        (Decimal("80.00"), "GREEN"),
        (Decimal("50.00"), "AMBER"),
        (Decimal("49.99"), "RED"),
    ),
)
def test_exact_rag_boundaries(score, expected_status):
    assert determine_dimension_status(score, METHODOLOGY) == expected_status
