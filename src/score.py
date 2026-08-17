import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class ObligationContribution:
    """Store one obligation's contribution to its dimension."""

    obligation_id: str
    obligation_status: str
    contribution: str
    review_required: bool


@dataclass(frozen=True)
class DimensionAssessment:
    """Store one authoritative dimension score and RAG result."""

    dimension_code: str
    dimension_name: str
    weight: str

    obligation_contributions: tuple[ObligationContribution, ...]

    met_count: int
    partial_count: int
    not_met_count: int

    earned_points: str
    maximum_points: str

    score: str
    dimension_status: str

    review_required: bool
    reason: str


def _decimal_text(value):
    """Format a Decimal without losing meaningful decimal places."""

    text = format(value, "f")

    if "." not in text:
        return f"{text}.0"

    return text


def contribution_for_status(obligation_status, methodology):
    """Return the configured-methodology contribution for a status."""

    definition = methodology.get("dimension_score_definition", "")

    if "partial counting as one half" not in definition.casefold():
        raise ValueError(
            "The methodology does not provide the expected structured or "
            "prose obligation-contribution rule."
        )

    contributions = {
        "MET": Decimal("1.0"),
        "PARTIAL": Decimal("0.5"),
        "NOT_MET": Decimal("0.0"),
    }

    if obligation_status not in contributions:
        raise ValueError(
            "Unexpected obligation status for dimension scoring: "
            f"{obligation_status!r}."
        )

    return contributions[obligation_status]


def _configured_boundaries(band_name, methodology):
    """Extract numeric boundaries from a configured RAG band."""

    bands = methodology.get("dimension_status_bands", {})

    if band_name not in bands:
        raise ValueError(
            f"Methodology is missing the {band_name} dimension band."
        )

    matches = re.findall(
        r"-?\d+(?:\.\d+)?",
        str(bands[band_name]),
    )

    if not matches:
        raise ValueError(
            f"Cannot read a numeric boundary from the {band_name} "
            "dimension band."
        )

    return tuple(
        Decimal(value)
        for value in matches
    )


def determine_dimension_status(score, methodology):
    """Apply authoritative GREEN, AMBER and RED score boundaries."""

    green_boundaries = _configured_boundaries("GREEN", methodology)
    amber_boundaries = _configured_boundaries("AMBER", methodology)
    red_boundaries = _configured_boundaries("RED", methodology)

    green_threshold = min(green_boundaries)
    amber_threshold = min(amber_boundaries)
    amber_upper_boundary = max(amber_boundaries)
    red_upper_boundary = max(red_boundaries)

    if amber_threshold != red_upper_boundary:
        raise ValueError(
            "AMBER and RED methodology boundaries are inconsistent."
        )

    if green_threshold <= amber_threshold:
        raise ValueError(
            "GREEN threshold must be greater than the AMBER threshold."
        )

    if (
        len(amber_boundaries) > 1
        and amber_upper_boundary != green_threshold
    ):
        raise ValueError(
            "AMBER upper boundary and GREEN threshold are inconsistent."
        )

    if score >= green_threshold:
        return "GREEN"

    if score >= amber_threshold:
        return "AMBER"

    return "RED"


def group_obligations_by_dimension(obligation_assessments):
    """Group each unique obligation under its authoritative dimension."""

    grouped_assessments = {}
    seen_obligation_ids = set()

    for assessment in sorted(
        obligation_assessments,
        key=lambda item: item.obligation_id,
    ):
        if not assessment.dimension:
            raise ValueError(
                f"Obligation {assessment.obligation_id} has no dimension."
            )

        if assessment.obligation_id in seen_obligation_ids:
            raise ValueError(
                "Obligation assessment appears more than once: "
                f"{assessment.obligation_id}."
            )

        seen_obligation_ids.add(assessment.obligation_id)
        grouped_assessments.setdefault(
            assessment.dimension,
            [],
        ).append(assessment)

    return {
        dimension_code: tuple(assessments)
        for dimension_code, assessments in sorted(
            grouped_assessments.items()
        )
    }


def calculate_dimension(
    dimension_code,
    dimension_config,
    obligation_assessments,
    methodology,
):

    if not obligation_assessments:
        raise ValueError(
            f"Dimension {dimension_code} has no obligation assessments."
        )

    if "name" not in dimension_config:
        raise ValueError(
            f"Dimension {dimension_code} has no configured name."
        )

    if "weight" not in dimension_config:
        raise ValueError(
            f"Dimension {dimension_code} has no configured weight."
        )

    contributions = []
    contribution_values = []
    status_counts = {
        "MET": 0,
        "PARTIAL": 0,
        "NOT_MET": 0,
    }

    for assessment in sorted(
        obligation_assessments,
        key=lambda item: item.obligation_id,
    ):
        contribution_value = contribution_for_status(
            assessment.status,
            methodology,
        )
        contribution_values.append(contribution_value)
        status_counts[assessment.status] += 1

        contributions.append(
            ObligationContribution(
                obligation_id=assessment.obligation_id,
                obligation_status=assessment.status,
                contribution=_decimal_text(contribution_value),
                review_required=assessment.review_required,
            )
        )

    earned_points = sum(
        contribution_values,
        Decimal("0.0"),
    )
    maximum_points = Decimal(len(contributions))
    exact_score = (
        earned_points
        / maximum_points
        * Decimal("100")
    )

    # The methodology does not specify presentation rounding. Two-decimal
    # ROUND_HALF_UP is an explicit deterministic output policy; RAG uses the
    # exact unrounded score.
    display_score = exact_score.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    dimension_status = determine_dimension_status(
        exact_score,
        methodology,
    )
    review_required = any(
        contribution.review_required
        for contribution in contributions
    )

    reason = (
        f"{_decimal_text(earned_points)} earned points divided by "
        f"{_decimal_text(maximum_points)} maximum points gives "
        f"{format(display_score, '.2f')}; the methodology bands classify "
        f"the dimension as {dimension_status}."
    )

    return DimensionAssessment(
        dimension_code=dimension_code,
        dimension_name=str(dimension_config["name"]),
        weight=_decimal_text(
            Decimal(str(dimension_config["weight"]))
        ),
        obligation_contributions=tuple(contributions),
        met_count=status_counts["MET"],
        partial_count=status_counts["PARTIAL"],
        not_met_count=status_counts["NOT_MET"],
        earned_points=_decimal_text(earned_points),
        maximum_points=_decimal_text(maximum_points),
        score=format(display_score, ".2f"),
        dimension_status=dimension_status,
        review_required=review_required,
        reason=reason,
    )


def score_dimensions(obligation_assessments, methodology):
    """Validate and score every configured dimension deterministically."""

    dimensions = methodology.get("dimensions")

    if not isinstance(dimensions, dict) or not dimensions:
        raise ValueError(
            "Methodology must define at least one authoritative dimension."
        )

    grouped_assessments = group_obligations_by_dimension(
        obligation_assessments
    )

    unknown_dimensions = sorted(
        set(grouped_assessments) - set(dimensions)
    )

    if unknown_dimensions:
        raise ValueError(
            "Obligation assessments reference unknown dimensions: "
            f"{', '.join(unknown_dimensions)}."
        )

    missing_dimensions = sorted(
        set(dimensions) - set(grouped_assessments)
    )

    if missing_dimensions:
        raise ValueError(
            "Configured dimensions have no obligation assessments: "
            f"{', '.join(missing_dimensions)}."
        )

    dimension_assessments = [
        calculate_dimension(
            dimension_code,
            dimensions[dimension_code],
            grouped_assessments[dimension_code],
            methodology,
        )
        for dimension_code in sorted(dimensions)
    ]
    return dimension_assessments
