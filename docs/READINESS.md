# Readiness assessment (pre-launch, 2026-10-26)

**Summary:** the backend, database, reconciliation, analytics, website, uploader and deployment configuration are
implemented and tested end to end with simulated data. **The addon has never run in a live World of Warcraft:
Forever client** (the beta is offline). Its correctness on the real client is unverified until
[`FOREVER_LAUNCH_VALIDATION.md`](FOREVER_LAUNCH_VALIDATION.md) has been executed.

## Definition of done

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Backend runs locally | Done | `docker compose up`; `/health/ready` reports migration `0001` |
| 2 | PostgreSQL stores persistent histories | Done | Alembic migration with 21 tables; data survives restarts (named volume) |
| 3 | Website searches fictional characters | Done | `/search`, partial and exact, namespace and class filters, duplicate-name warning |
| 4 | Character pages show dungeon history | Done | `/character/{namespace}/{id}` with paginated, filterable history |
| 5 | Run pages show party-wide performance | Done | `/runs/{id}`: participants, metrics with provenance, encounters, deaths, wipes, sources |
| 6 | One synthetic upload contributes five players | Done | `test_e2e_pipeline.py` (real addon code → file → upload endpoint) |
| 7 | Multiple uploads of one run reconcile | Done | Same test; `test_simulation_accuracy.py`: 0 false merges, 0 splits against ground truth |
| 8 | Incomplete and contradictory data handled safely | Done | Unavailable ≠ 0, partial coverage excluded from averages, conflicts preserved, quarantine |
| 9 | Statistics computed correctly | Done (to definition) | `test_analytics.py`; definitions in `ANALYTICS_DEFINITIONS.md` |
| 10 | Provenance and freshness visible | Done | Metric marks and tooltips, candidate tables, "last observed", "statistics computed" |
| 11 | Addon built on the best verified API information | Done, **unverified in-client** | `RESEARCH_FOREVER_API.md`; 53 Lua tests against a mock |
| 12 | Upload pipeline works end to end with simulated data | Done | Website upload, `/ft export` paste, desktop uploader (`test_uploader_integration.py`) |
| 13 | Automated tests pass | Done | See test inventory below |
| 14 | Deployment configuration prepared | Done, not deployed | `docker-compose.prod.yml`, Caddyfile (validated with `caddy validate`), CI workflow, backup script |
| 15 | Launch-day validation checklist | Done | `FOREVER_LAUNCH_VALIDATION.md` |

## Test inventory (all passing at the time of writing)

| Suite | Count | Runs |
|---|---|---|
| SavedVariables parser and extractor | 24 | `pytest packages/savedvariables/tests` |
| Addon (Lua 5.1 VM, mocked Forever client) | 53 tests in 5 files | `pytest addon/tests` or `python addon/tests/harness.py` |
| Backend: ingestion, reconciliation, API, analytics, e2e, simulation accuracy, uploader integration | 47 | `pytest backend/tests` (needs PostgreSQL) |
| Desktop uploader (incl. background mode, autostart, single-instance lock) | 16 | `pytest uploader/tests` |
| Frontend components | 18 | `cd frontend && npm test` |

Also checked by hand: the production Next.js build; Docker images for the backend and frontend; the full compose stack
seeded with 1,200 synthetic runs; screenshots of every page at desktop and phone widths (no horizontal overflow
after fixes; no console errors).

## What is not verified, and the risk if it fails

| Area | Risk if live behaviour differs | Mitigation already built |
|---|---|---|
| Damage-meter values readable after combat in dungeons | No DPS/HPS/interrupt data | Shown as "—"; deaths, rosters and encounters still work; flag `meter` |
| Party identity readable in dungeons | Runs harder to match; name-only identities | Name-only path; unidentified entries never guessed |
| `UnitIsDeadOrGhost` for distant party members | Missed deaths | Coverage marked partial; meter deaths preferred |
| Completion events for Forever dungeons | Few `completed/verified` runs | Curated final-boss IDs give `probable` completions |
| Party GUID shared across members | Matching relies on presence overlap (already the primary signal) | Veto can be disabled |
| SavedVariables load bug (beta 69893) | Each session overwrites the last | Uploader archives every version; `/ft export` |
| Deaths meter semantics | Wrong meter death counts | `METER_DEATH_INTERPRETATION` + `rebuild` (no re-upload needed) |
| Forever's dungeon map IDs and boss IDs | Cosmetic and docs | Catalog is learned from observations |

## Known limitations and follow-ups

* **No live-client testing** (the main blocker for a public addon release).
* **Blizzard terms review not done** (see `PRIVACY.md`). Do this before distributing the addon or launching the site.
* **No profile claim flow**: intentionally deferred until a verifiable mechanism exists.
* **Crash data loss**: anything recorded after the last logout or `/reload` is lost if the client crashes (WoW only
  writes SavedVariables on logout or reload). Unit-state deaths still present at re-login are re-detected.
* **Corroboration vs collusion**: independent installations are cheap to create; all data is labelled self-reported.
* **Single-process rate limiter**: fine for one API container; needs Redis for several.
* **Retention job** for old upload-batch metadata is documented but not automated.
* **Performance**: measured only on the development machine (about 12 batches/s ingestion inside compose). No
  production benchmarks exist.
* **Accessibility**: semantic HTML, labels and focus styles are in place; no formal audit has been done.

## Recommended next steps

1. Review Blizzard's terms (`PRIVACY.md`).
2. When the client is available, run `FOREVER_LAUNCH_VALIDATION.md` with two testers, flip flags, release addon 0.2.0.
3. Deploy staging with synthetic data; then production with real data only.
4. Curate the dungeon catalog (map IDs, final encounter IDs) from the first real uploads.
