"""Focused tests for Phase 10 run reproducibility."""

from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from assess import evaluate_date_state
from ingest import load_json
from report import sha256_bytes
from versioning import (
    ENGINE_VERSION,
    INPUT_FILENAMES,
    build_manifest,
    build_run_id,
    compare_run_context,
    sha256_file,
    write_run_snapshot,
)


DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"


def current_input_files():
    return [
        {"name": name, "sha256": sha256_file(DATA_DIR / name)}
        for name in INPUT_FILENAMES
    ]


def future_methodology():
    methodology = deepcopy(load_json("methodology.json"))
    methodology["methodology_version"] = "TEST-FUTURE"
    methodology["evidence_rules"]["staleness_threshold_days"] = 180

    # Synthetic values used only to demonstrate methodology versioning.
    # These are not official future VERACIS weights.
    methodology["dimensions"]["GOV"]["weight"] = 0.20
    methodology["dimensions"]["MRC"]["weight"] = 0.30
    return methodology


def manifest_for(methodology, methodology_sha256=None):
    input_files = current_input_files()

    if methodology_sha256 is not None:
        for item in input_files:
            if item["name"] == "methodology.json":
                item["sha256"] = methodology_sha256

    return build_manifest(
        input_files,
        load_json("obligations.json"),
        methodology,
        "a" * 64,
    )


def test_same_file_bytes_have_same_sha256():
    with TemporaryDirectory(dir=OUTPUT_DIR) as temp_dir:
        path = Path(temp_dir) / "input.txt"
        path.write_bytes(b"same bytes\n")
        assert sha256_file(path) == sha256_file(path)


def test_changed_file_bytes_have_different_sha256():
    with TemporaryDirectory(dir=OUTPUT_DIR) as temp_dir:
        path = Path(temp_dir) / "input.txt"
        path.write_bytes(b"version one\n")
        first_hash = sha256_file(path)
        path.write_bytes(b"version two\n")
        assert sha256_file(path) != first_hash


def test_same_context_has_same_run_id():
    values = (
        "2026.2",
        "1.0.0",
        "2026-08-01",
        "e" * 64,
        "m" * 64,
        "o" * 64,
        ENGINE_VERSION,
    )
    assert build_run_id(*values) == build_run_id(*values)


def test_changed_methodology_has_different_run_id():
    current = manifest_for(load_json("methodology.json"))

    with TemporaryDirectory(dir=OUTPUT_DIR) as temp_dir:
        future_path = Path(temp_dir) / "methodology.json"
        future_path.write_text(
            json.dumps(future_methodology(), sort_keys=True),
            encoding="utf-8",
        )
        future = manifest_for(
            future_methodology(),
            sha256_file(future_path),
        )

    assert future["run_id"] != current["run_id"]


def test_context_comparison_identifies_only_methodology_change():
    current_methodology = load_json("methodology.json")
    changed_methodology = future_methodology()
    current = manifest_for(current_methodology)

    with TemporaryDirectory(dir=OUTPUT_DIR) as temp_dir:
        future_path = Path(temp_dir) / "methodology.json"
        future_path.write_text(
            json.dumps(changed_methodology, sort_keys=True),
            encoding="utf-8",
        )
        future = manifest_for(
            changed_methodology,
            sha256_file(future_path),
        )

    assert compare_run_context(current, future) == {
        "evidence_changed": False,
        "methodology_changed": True,
        "obligations_changed": False,
    }
    assert current_methodology["dimensions"]["GOV"]["weight"] == 0.25
    assert current_methodology["dimensions"]["MRC"]["weight"] == 0.25
    assert changed_methodology["dimensions"]["GOV"]["weight"] == 0.20
    assert changed_methodology["dimensions"]["MRC"]["weight"] == 0.30


def test_200_day_old_evidence_changes_from_current_to_stale():
    current = load_json("methodology.json")
    future = future_methodology()
    as_at_date = date.fromisoformat(
        current["evidence_rules"]["as_at_date"]
    )
    record = SimpleNamespace(
        event_date=as_at_date - timedelta(days=200)
    )

    current_state = evaluate_date_state(
        (record,),
        as_at_date,
        current["evidence_rules"]["staleness_threshold_days"],
    )
    future_state = evaluate_date_state(
        (record,),
        as_at_date,
        future["evidence_rules"]["staleness_threshold_days"],
    )

    assert current_state == "CURRENT"
    assert future_state == "STALE"
    assert load_json("methodology.json")["evidence_rules"][
        "staleness_threshold_days"
    ] == 365


def test_rerunning_v1_reuses_identical_snapshot():
    assessment_bytes = (OUTPUT_DIR / "assessment.json").read_bytes()
    assessment_sha256 = sha256_bytes(assessment_bytes)
    manifest = build_manifest(
        current_input_files(),
        load_json("obligations.json"),
        load_json("methodology.json"),
        assessment_sha256,
    )

    with TemporaryDirectory(dir=OUTPUT_DIR) as temp_dir:
        first = write_run_snapshot(temp_dir, assessment_bytes, manifest)
        second = write_run_snapshot(temp_dir, assessment_bytes, manifest)

        assert first == second
        assert first["historical_report"].read_bytes() == assessment_bytes
        assert len(list((Path(temp_dir) / "runs").iterdir())) == 1
        assert manifest["run_id"] == second["historical_report"].parent.name
        assert manifest["assessment_sha256"] == assessment_sha256
