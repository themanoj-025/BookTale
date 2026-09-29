# ML Artifacts — Intentional `.gitignore` Exception

This document records why some files under `app/services/recommendations/`
are intentionally **not** gitignored, and where they live after the
Phase-8 relocation.

## Why these files are tracked

The ML payloads below are **source data used by the bundled
`recommendations` CLI** — the seed dataset (`books.csv`) and the model
reference images. They are committed so that a fresh clone of the
repository can run the CLI out of the box, without downloading a remote
dataset or triggering an offline/caching path.

- `app/services/recommendations/ml_datasets/books.csv` — 300-row synthetic
  book seed dataset consumed by `ml_models/ml_pkg.data_loading`.
- `app/services/recommendations/ml_images/*.jpg` — model reference
  thumbnails referenced by the CLI report generator.

They are *data*, not trained artifacts: no `.pkl`, `.joblib`, `.h5`,
`.onnx` or other serialized weights live in `app/services/recommendations/`.

## What is intentionally gitignored instead

- `app/services/recommendations/ml/` — the legacy, nested ML source tree
  (moved off `app/` in Phase 8).
- `data/` — user-generated data (books.json, users.json, booktale.db,
  transactions.json, …). Not source data.
- `data/generated/` — generated benchmark outputs (`comparison_output/`).
- `logs/` — writable log output (see `app/core/logger.py` for rotation + retention).

## The exception in `.gitignore`

`.gitignore` therefore contains a documented exception so that nothing
accidentally re-adds the legacy tree:

* ML artifacts (raw scripts + dataset + images) — gitignored, see
  **MODERNIZATION_AUDIT.md**. *(added 2026-09-29)*

The `ml Datasets/` and `ml Images/` directories below are the only
`app/services/recommendations/` files committed today; everything else in
`app/services/recommendations/` is source Python + the structured log/
backup directories, which are all gitignored per the standard rules.

## Notes

- `books.csv` is a **synthetic seed** (300 rows) generated for this
  repository; it is not a redistribution of a third-party Kaggle dataset.
  The schema and the first few rows are all that is shipped.
- Trained model weights are **never** checked in. They are generated at
  runtime in `data/generated/` (gitignored) by the training workflow.
