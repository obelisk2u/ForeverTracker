# Fixtures

Everything here is **synthetic, development-only data**. It does not describe real players.

| Path | What | Regenerate |
|---|---|---|
| `savedvariables/ForeverTracker.current.lua` | A SavedVariables file written by the current addon code running in a Lua 5.1 VM against the mocked client: two runs (one completed through the dungeon finder after a wipe, with a death; one the player marks completed), a pet and an unknown player in the meter, group, inspect and self snapshots, and a probe report. `POST` it to `/api/v1/ingest/savedvariables` to try the pipeline. | `python tools/make_fixtures.py` (`--check` only compares) |
| `batches/current-batch.json` | The same data as an upload batch (`POST /api/v1/ingest/batches`) | same |
| `savedvariables/ForeverTracker.sample.lua`, `batches/sample-batch.json` | The same kind of file written by **addon 0.1.0**, kept unchanged as the old-payload fixture | not regenerated |
| `generated/` (git-ignored) | Large simulator output, if you export it | `python -m app.cli seed` ingests directly instead |

Larger synthetic worlds come from `tools/simulator` (`python -m app.cli seed --characters 2500 --runs 1200`).
Simulator batches carry `"synthetic": true`, which production refuses.

`backend/tests/test_contract.py` fails when the current fixture is not what the addon writes now, and checks both
fixtures against the models and the generated JSON Schema.

Frontend test fixtures (`frontend/tests/fixtures/e2e/`) are real API responses captured by
`backend/tests/test_e2e_pipeline.py` with `FT_WRITE_FRONTEND_FIXTURES=1`.
