"""Focused tests for source normalization behavior."""

from datetime import date
from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ingest import load_csv, load_json, load_registry_tsv
from normalize import (
    clean_optional,
    normalize_all_evidence,
    normalize_evidence_csv,
    normalize_status,
    parse_event_date,
)


@pytest.mark.parametrize(
    ("source_dataset", "raw_status", "expected"),
    (
        ("evidence_csv", "APPROVED", "APPROVED"),
        ("registry", "Approved", "APPROVED"),
        ("servicedesk", "Closed - Approved", "APPROVED"),
        ("evidence_csv", "DRAFT", "DRAFT"),
        ("registry", "Draft", "DRAFT"),
        ("servicedesk", "Open - In Draft", "DRAFT"),
        ("servicedesk", "Closed - Approved Retrospectively",
         "APPROVED_RETROSPECTIVELY"),
        ("servicedesk", "Unmapped source state", "UNKNOWN"),
        ("registry", "-", "UNKNOWN"),
    ),
)
def test_status_vocabularies_normalize_deterministically(
    source_dataset, raw_status, expected
):
    assert normalize_status(source_dataset, raw_status) == expected


@pytest.mark.parametrize("raw_value", (None, "", "-", "  -  "))
def test_blank_optional_values_become_none(raw_value):
    assert clean_optional(raw_value) is None


@pytest.mark.parametrize(
    ("source_dataset", "raw_value", "expected"),
    (
        ("evidence_csv", "2026-07-15", date(2026, 7, 15)),
        ("registry", "15/07/2026", date(2026, 7, 15)),
        ("servicedesk", "2026-07-15T18:30:00Z", date(2026, 7, 15)),
    ),
)
def test_source_dates_become_python_dates(
    source_dataset, raw_value, expected
):
    assert parse_event_date(source_dataset, raw_value) == expected


def test_observation_ids_depend_on_stable_source_position():
    records = [
        {
            "evidence_id": "EV-A",
            "source_system": "Synthetic",
            "obligation_id": "OBL-A",
            "evidence_type": "policy",
            "title": "First",
            "evidence_date": "2026-07-01",
            "status": "APPROVED",
            "owner": "Owner",
            "version": "1.0",
            "evidence_hash": "hash-a",
        },
        {
            "evidence_id": "EV-B",
            "source_system": "Synthetic",
            "obligation_id": "OBL-B",
            "evidence_type": "register",
            "title": "Second",
            "evidence_date": "-",
            "status": "DRAFT",
            "owner": "-",
            "version": "-",
            "evidence_hash": "-",
        },
    ]

    first_run = normalize_evidence_csv(records)
    second_run = normalize_evidence_csv(records)

    assert [item.observation_id for item in first_run] == [
        "evidence_csv:0001",
        "evidence_csv:0002",
    ]
    assert first_run == second_run
    assert first_run[1].event_date is None
    assert first_run[1].owner is None


def test_supplied_source_pack_normalizes_to_42_observations():
    evidence = load_csv("evidence.csv")
    registry, _ = load_registry_tsv("registry_export.tsv")
    servicedesk = load_json("servicedesk_export.json")

    records = normalize_all_evidence(evidence, registry, servicedesk)

    assert len(records) == 42
