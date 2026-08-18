"""Integration proof for byte-identical assessment output."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from assess import assess_obligations
from ingest import (
    load_csv,
    load_json,
    load_registry_tsv,
    load_source_notes,
)
from normalize import normalize_all_evidence
from reconcile import reconcile_evidence
from report import (
    build_assessment_report,
    serialize_report,
    sha256_bytes,
)
from score import score_dimensions
from validate import validate_evidence


def run_pipeline_to_report_bytes():
    obligations_data = load_json("obligations.json")
    methodology = load_json("methodology.json")
    evidence = load_csv("evidence.csv")
    registry, _ = load_registry_tsv("registry_export.tsv")
    servicedesk = load_json("servicedesk_export.json")
    load_source_notes("source_notes.md")

    canonical_records = normalize_all_evidence(
        evidence,
        registry,
        servicedesk,
    )
    quality_issues = validate_evidence(
        canonical_records,
        obligations_data,
        methodology,
    )
    reconciliation_groups = reconcile_evidence(canonical_records)
    obligation_assessments = assess_obligations(
        canonical_records,
        obligations_data,
        methodology,
        quality_issues,
        reconciliation_groups,
    )
    dimension_assessments = score_dimensions(
        obligation_assessments,
        methodology,
    )
    report = build_assessment_report(
        obligations_data,
        methodology,
        canonical_records,
        quality_issues,
        reconciliation_groups,
        obligation_assessments,
        dimension_assessments,
    )

    return report, serialize_report(report)


def test_complete_pipeline_is_byte_identical():
    run_a = run_pipeline_to_report_bytes()
    run_b = run_pipeline_to_report_bytes()
    report_a, bytes_a = run_a
    report_b, bytes_b = run_b

    assert bytes_a == bytes_b
    assert sha256_bytes(bytes_a) == sha256_bytes(bytes_b)


def test_report_preserves_complete_current_assessment():
    report, report_bytes = run_pipeline_to_report_bytes()

    assert len(report["evidence_observations"]) == 42
    assert len(report["data_quality_issues"]) == 10
    assert len(report["reconciliation_groups"]) == 13
    assert len(report["obligations"]) == 12
    assert len(report["dimensions"]) == 5
    assert [item["weight"] for item in report["dimensions"]] == [
        "0.10",
        "0.25",
        "0.25",
        "0.20",
        "0.20",
    ]

    statuses = [item["status"] for item in report["obligations"]]
    assert statuses.count("MET") == 7
    assert statuses.count("PARTIAL") == 5
    assert statuses.count("NOT_MET") == 0

    rag_statuses = [
        item["dimension_status"] for item in report["dimensions"]
    ]
    assert rag_statuses.count("GREEN") == 3
    assert rag_statuses.count("AMBER") == 2
    assert rag_statuses.count("RED") == 0

    report_text = report_bytes.decode("utf-8")
    assert str(PROJECT_ROOT) not in report_text
    assert "veracis_traceability.db" not in report_text
    assert "generated_at" not in report_text
