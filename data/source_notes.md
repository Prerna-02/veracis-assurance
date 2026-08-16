# Data pack - source notes

Three evidence sources are supplied. They come from three different systems and they do
not share a schema. Reconciling them into one model is part of the exercise.

| File | Origin | Format |
|---|---|---|
| `evidence.csv` | Compliance evidence log, maintained manually | CSV |
| `servicedesk_export.json` | Meridian ServiceDesk (ticketing) | JSON, nested |
| `registry_export.tsv` | Meridian Asset Registry | Tab-separated, with a trailing comment line |

`obligations.json` and `methodology.json` are reference data and are authoritative.

Field names differ between sources. Date formats differ between sources. Status
vocabularies differ between sources. The same underlying artefact may appear in more
than one source. None of this has been cleaned for you.

The `as_at` date for this exercise is set in `methodology.json`.
