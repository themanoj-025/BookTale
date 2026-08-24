# Book-Tale — Session Audit (2026-08-16): Committed Build Sync

## What was done
The repo deliberately commits `app/static/dist/` (hashed build output +
manifest) so a fresh clone serves hashed URLs without running npm first.
That committed build had gone **stale** — sources changed since the last
build, so the manifest referenced files that no longer matched actual
build output.

- Regenerated the bundle from sources (`npm ci && npm run build`).
- Committed the fresh build: **16 new hashed files** added, **17 stale
  files** deleted, `manifest.json` updated.
- Added a CI job (`frontend-build-check` in `.github/workflows/ci.yml`)
  that rebuilds and diffs `app/static/dist/`, failing if the committed
  build drifts from sources again — preserving the fresh-clone-serving
  convention while making the artifact auditable/reproducible.

## Validation
- Rebuild is reproducible; diff against committed dist is now empty.
- Commit: `3653045`.

## Note
The repo's `.gitignore` deliberately un-ignores dist (the project serves
it directly in production without a build step). No gitignore change made —
the convention is respected, the sync guarantee is now enforced by CI.
