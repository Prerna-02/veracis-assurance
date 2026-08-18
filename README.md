# Veracis Assurance
# VERACIS Assurance Assessment

**GitHub:** [github.com/Prerna-02/veracis-assurance](https://github.com/Prerna-02/veracis-assurance)

## What this project does

This project reads the supplied VERACIS obligations, methodology and evidence files, normalises evidence from three different source systems, flags data-quality problems, reconciles repeated artefacts, assesses each obligation, calculates dimension scores and keeps an SQL audit trail back to the original evidence.

The main output is a deterministic JSON report. The project also stores version information so the same assessment can be identified and reproduced later.

## How to run it

From the project root:

```bash
python -m venv .venv
```

Activate the environment, then install the requirements:

```bash
pip install -r requirements.txt
```

Run the assessment:

```bash
python src/main.py
```

Run the tests:

```bash
python -m pytest -q
```

Main generated files:

- `output/assessment.json` — current assessment report
- `output/veracis_traceability.db` — SQLite audit database
- `output/manifest.json` — run details and input/output hashes
- `output/runs/<run_id>/` — preserved historical assessment and manifest
- `sql/operational_integrity_query.sql` — required SQL traceability query

## How the pipeline works

```text
Input files
    ↓
Normalisation
    ↓
Data-quality checks
    ↓
Reconciliation
    ↓
Obligation assessment
    ↓
Dimension scoring
    ↓
JSON report + SQLite traceability + run manifest
```

The three evidence exports do not share the same schema or status names, so they are first converted into one common evidence structure. Data-quality checks then identify missing, invalid or suspicious fields without deleting the original records.

Reconciliation checks whether observations from different systems appear to represent the same underlying artefact. Obligation assessment then applies the methodology rules, and dimension scoring converts the obligation results into the final dimension score and RAG status.

## Key decisions and why

### 1. Keep every source record visible

I did not silently remove records with missing dates, unknown obligations, duplicate source IDs or other defects. They remain in the output with a reason showing how they were treated.

### 2. Treat repeated records as observations of one artefact

The same underlying artefact can appear in more than one source. When records share the same digest, I treat them as observations of one logical artefact so the evidence is not counted twice. The original source observations are still kept for traceability.

### 3. Do not invent source precedence

If two observations of the same artefact disagree, I do not automatically use rules such as “approved wins” or “latest wins”. The data pack does not state that one source should override another, so conflicts remain visible and can require review.

### 4. Keep retrospective approval separate

`APPROVED_RETROSPECTIVELY` was kept separate from normal `APPROVED`. It shows that approval happened later, but it does not prove that approval existed at the required time. I therefore did not allow retrospective approval by itself to qualify evidence for MET.

### 5. Keep calculation separate from review

An obligation can have a calculated result and still require human review. `review_required` is an audit signal; it does not automatically replace the deterministic assessment result.

### 6. Keep the scoring path deterministic

MET, PARTIAL and NOT_MET are decided using explicit rules from the methodology. Dimension scores and GREEN/AMBER/RED status are also calculated in code. The report uses stable ordering, fixed decimal formatting and no changing timestamps or random IDs, so the same inputs produce byte-identical output.

### 7. Version evidence and methodology separately

Evidence, methodology and obligations are hashed separately. This makes it possible to tell whether a later report changed because the evidence changed or because the methodology changed. The current 365-day methodology remains preserved, while tests show that the same assessment logic can also work with a 180-day staleness threshold.

## Data issues and assumptions

- **Different schemas:** the CSV, ServiceDesk export and Registry export use different fields and status terminology. I normalised them while keeping the source values.
- **Repeated artefacts:** the same artefact may appear in several systems. Matching digests are used as the main reconciliation signal.
- **Retrospective approval:** I treated this as weaker than ordinary approval because it does not prove approval existed at the required time.
- **Contradictory evidence:** Where the same artefact has conflicting status or important metadata and no source-priority rule is supplied, I flag it for review rather than choosing a winner.
- **Date meaning differs by source:** a ServiceDesk closure date is the available event date for that record, but I do not assume it is the original creation date of the artefact.

## What I deliberately did not build

- **No LLM in the assessment or scoring path.** The supplied evidence and methodology are structured, so deterministic rules are more reproducible.
- **No fuzzy title matching.** I used stronger reconciliation signals such as digests rather than introducing an unsupported similarity threshold.
- **No automatic source-precedence rule.** The data pack does not define which source should override another.
- **No overall institution score.** I only calculated the dimension scores defined by the supplied methodology.
- **No official future methodology V2.** The case says two weights will change, but the new values are not supplied. The 180-day behaviour and weight changes are demonstrated only with clearly labelled synthetic test values.

## What I would do with another week

1. Confirm ambiguous methodology rules and source-precedence questions with the institution.
2. Test the pipeline with an officially supplied future methodology version.
3. Add more edge-case tests based on examples reviewed by compliance users.
4. Build a small audit view over SQLite so a reviewer can move from dimension → obligation → evidence without manually running SQL.
5. Add controlled support for unstructured evidence such as policies, audit reports and board minutes, with human review before extracted values enter the deterministic assessment.

## AI use

I used Codex for implementation support. I created the phase-by-phase implementation plan, ran each phase manually in the terminal, reviewed the evidence and outputs, and decided how ambiguous cases should be treated before keeping the final logic. The runtime assessment itself is deterministic; no LLM decides obligation status, dimension score or RAG status.
