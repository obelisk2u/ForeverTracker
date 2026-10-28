# Fixtures

Everything here is **synthetic, development-only data**. It does not describe real players.

| Path | What | Regenerate |
|---|---|---|
| `savedvariables/ForeverTracker.sample.lua` | A SavedVariables file written by the real addon code running in a Lua 5.1 VM against the mocked client: one completed dungeon, a death, a boss kill, inspections and a probe report. `POST` it to `/api/v1/ingest/savedvariables` to try the pipeline. | `python tools/make_fixtures.py` |
| `batches/sample-batch.json` | The same data as an upload batch (`POST /api/v1/ingest/batches`) | same |
| `generated/` (git-ignored) | Large simulator output, if you export it | `python -m app.cli seed` ingests directly instead |

Larger synthetic worlds come from `tools/simulator` (`python -m app.cli seed --characters 2500 --runs 1200`).
Simulator batches carry `"synthetic": true`, which production refuses.

Frontend test fixtures (`frontend/tests/fixtures/e2e/`) are real API responses captured by
`backend/tests/test_e2e_pipeline.py` with `FT_WRITE_FRONTEND_FIXTURES=1`.
