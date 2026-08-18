"""Small reproducibility helpers for VERACIS assessment runs."""

import hashlib
import json
from pathlib import Path


ENGINE_VERSION = "1.0.0"
INPUT_FILENAMES = (
    "evidence.csv",
    "methodology.json",
    "obligations.json",
    "registry_export.tsv",
    "servicedesk_export.json",
    "source_notes.md",
)
EVIDENCE_FILENAMES = (
    "evidence.csv",
    "registry_export.tsv",
    "servicedesk_export.json",
)


def sha256_file(path):
    """Hash the exact bytes of one input file."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_evidence_hash(input_files):
    """Combine the three evidence-file hashes into one fingerprint."""

    hashes_by_name = {
        item["name"]: item["sha256"] for item in input_files
    }
    missing = set(EVIDENCE_FILENAMES) - set(hashes_by_name)

    if missing:
        raise ValueError(
            "Missing evidence file hash(es): " + ", ".join(sorted(missing))
        )

    combined = "".join(
        f"{name}:{hashes_by_name[name]}\n"
        for name in sorted(EVIDENCE_FILENAMES)
    )
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def build_run_id(
    obligation_set_version,
    methodology_version,
    as_at_date,
    evidence_sha256,
    methodology_sha256,
    obligations_sha256,
    engine_version=ENGINE_VERSION,
):
    """Create the same readable ID for the same complete run context."""

    identity = {
        "as_at_date": as_at_date,
        "engine_version": engine_version,
        "evidence_sha256": evidence_sha256,
        "methodology_sha256": methodology_sha256,
        "methodology_version": methodology_version,
        "obligation_set_version": obligation_set_version,
        "obligations_sha256": obligations_sha256,
    }
    identity_bytes = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "run_" + hashlib.sha256(identity_bytes).hexdigest()[:16]


def build_manifest(
    input_files,
    obligations_data,
    methodology,
    assessment_sha256,
):
    """Build the deterministic receipt for one assessment run."""

    files = sorted(input_files, key=lambda item: item["name"])
    hashes_by_name = {item["name"]: item["sha256"] for item in files}
    missing = set(INPUT_FILENAMES) - set(hashes_by_name)

    if missing:
        raise ValueError(
            "Missing input file hash(es): " + ", ".join(sorted(missing))
        )

    evidence_sha256 = build_evidence_hash(files)
    methodology_sha256 = hashes_by_name["methodology.json"]
    obligations_sha256 = hashes_by_name["obligations.json"]
    evidence_rules = methodology["evidence_rules"]
    run_id = build_run_id(
        obligations_data["obligation_set_version"],
        methodology["methodology_version"],
        evidence_rules["as_at_date"],
        evidence_sha256,
        methodology_sha256,
        obligations_sha256,
    )

    return {
        "run_id": run_id,
        "engine_version": ENGINE_VERSION,
        "obligation_set_version": obligations_data[
            "obligation_set_version"
        ],
        "methodology_version": methodology["methodology_version"],
        "as_at_date": evidence_rules["as_at_date"],
        "staleness_threshold_days": evidence_rules[
            "staleness_threshold_days"
        ],
        "evidence_sha256": evidence_sha256,
        "methodology_sha256": methodology_sha256,
        "obligations_sha256": obligations_sha256,
        "assessment_sha256": assessment_sha256,
        "input_files": files,
    }


def compare_run_context(old_manifest, new_manifest):
    """Identify which authoritative input category changed."""

    return {
        "evidence_changed": (
            old_manifest["evidence_sha256"]
            != new_manifest["evidence_sha256"]
        ),
        "methodology_changed": (
            old_manifest["methodology_sha256"]
            != new_manifest["methodology_sha256"]
        ),
        "obligations_changed": (
            old_manifest["obligations_sha256"]
            != new_manifest["obligations_sha256"]
        ),
    }


def write_run_snapshot(output_dir, assessment_bytes, manifest):
    """Preserve a run once and refuse conflicting historical content."""

    output_dir = Path(output_dir)
    run_dir = output_dir / "runs" / manifest["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_bytes = (
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    historical_report = run_dir / "assessment.json"
    historical_manifest = run_dir / "manifest.json"

    for path, expected_bytes in (
        (historical_report, assessment_bytes),
        (historical_manifest, manifest_bytes),
    ):
        if path.exists() and path.read_bytes() != expected_bytes:
            raise RuntimeError(
                f"Historical run contains conflicting {path.name}."
            )
        if not path.exists():
            path.write_bytes(expected_bytes)

    current_manifest = output_dir / "manifest.json"
    current_manifest.write_bytes(manifest_bytes)
    return {
        "historical_report": historical_report,
        "historical_manifest": historical_manifest,
        "manifest": current_manifest,
    }
