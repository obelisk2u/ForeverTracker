# Readiness assessment (updated 2026-11-18)

**Summary:** the backend, database, reconciliation, analytics, website, uploader and deployment configuration are
implemented and tested end to end with simulated data and with the real addon code in a Lua 5.1 harness. The addon
has been used on live World of Warcraft: Forever builds since 2026-11-09 (70862-70938); forevertracker.org showed 11
runs from 2 contributors on 2026-11-17. The launch-day checks in
[`FOREVER_LAUNCH_VALIDATION.md`](FOREVER_LAUNCH_VALIDATION.md) have **not** been run and recorded systematically, so
collectors marked *needs validation* remain unverified beyond what that live use showed.

## Definition of done

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Backend runs locally | Done | `docker compose up`; `/health/ready` reports migration `0005` |
| 2 | PostgreSQL stores persistent histories | Done | Alembic migrations 0001-0005 (20 tables plus `identity_claims`); data survives restarts (named volume) |
| 3 | Website searches characters | Done | `/search`, partial and exact, namespace and class filters |
| 4 | Character pages show dungeon history | Done | `/character/{namespace}/{id}` with paginated, filterable history |
| 5 | Every counted run can be reached | Done | `/runs` (and `GET /api/v1/runs`) lists every run the home page counts; dungeon cards link to it |
| 6 | Run pages show party-wide performance | Done | `/runs/{id}`: participants, metrics, encounters with per-fight meters, deaths, wipes, gear |
| 7 | One upload contributes five players | Done | `test_e2e_pipeline.py` (real addon code → file → upload endpoint) |
| 8 | Multiple uploads of one run reconcile, in any order | Done | `test_reconciliation_convergence.py`; `test_simulation_accuracy.py`: 0 false merges, 0 splits against ground truth |
| 9 | Incomplete and contradictory data handled safely | Done | Unavailable ≠ 0, unattributed or partially read meters are not complete, conflicts preserved, identity contradictions held as claims |
| 10 | Statistics computed correctly | Done (to definition) | `test_analytics.py`; definitions in `ANALYTICS_DEFINITIONS.md` |
| 11 | Upload contract consistent across layers | Done | `test_contract.py`: real addon output against Pydantic and the generated JSON Schema; CI regenerates schema, OpenAPI and TS types |
| 12 | Upload pipeline works end to end | Done | Desktop uploader (`test_uploader_integration.py`); `/ft export` and SavedVariables endpoints (no website page for either) |
| 13 | Automated tests pass | Done | See test inventory below |
| 14 | Deployment configuration prepared | Done; production running | `docker-compose.prod.yml`, Caddyfile, CI workflow, backup script |
| 15 | Launch-day validation | **Open** | Checklist exists; results table empty |

## Test inventory (2026-11-18, all passing)

| Suite | Count | Runs |
|---|---|---|
| SavedVariables parser, shapes and extractor | 44 | `pytest packages/savedvariables/tests` |
| Addon (Lua 5.1 VM, mocked Forever client) | 116 Lua cases in 7 files (8 pytest wrappers) | `pytest addon/tests` or `python addon/tests/harness.py` |
| Backend: ingestion, reconciliation, convergence, rematch, contributors and claims, contract, limits, API, analytics, e2e, simulation accuracy, uploader integration | 123 | `pytest backend/tests` (needs PostgreSQL; truncates every table in `TEST_DATABASE_URL`'s database) |
| Desktop uploader | 36 (+3 Windows-only, skipped elsewhere) | `pytest uploader/tests` |
| Frontend components and pages | 42 | `cd frontend && npm test` |

## What is not verified, and the risk if it fails

| Area | Risk if live behaviour differs | Mitigation already built |
|---|---|---|
| Damage-meter attribution when GUIDs are unreadable | Numbers unattributed | Exact full-name or unique first-name matching only; `unmatched_sources` makes totals incomplete instead of wrong |
| Party identity readable in dungeons | Runs harder to match; name-only identities | Name-only path; unidentified entries never guessed |
| `UnitIsDeadOrGhost` for distant party members | Missed deaths | Coverage marked partial; meter deaths preferred |
| Party GUID shared across members | Runs split across observers | `MATCH_PARTY_GUID_VETO=false`, then `python -m app.cli rematch` for stored runs |
| SavedVariables load bug (beta 69893) | Each session overwrites the last | Uploader archives every version; `/ft export` |
| Deaths meter semantics | Wrong meter death counts | `METER_DEATH_INTERPRETATION` + `rebuild` (no re-upload needed) |
| Final bosses of 18 of 23 listed dungeons (unverified in game), and 5 of Forever's 9 new dungeons not listed | Unlisted: full clears by premade groups end `left` and read "Left early" (kills kept). Listed but wrong: a run ends early and loses later kills | Players can `/ft complete`; the pending five and the evidence each needs are in `final_encounters.json` and `FOREVER_LAUNCH_VALIDATION.md` section 2; after adding one, `python -m app.cli recover-outcomes` |
| Character level cap (`MAX_CHARACTER_LEVEL=60`) | Max-level runs quarantined | Restore and release in the admin API; quarantines of this kind count toward flagging |

## Known limitations and follow-ups

* **Launch-day validation not recorded** (see above).
* **Blizzard terms review not done** (see `PRIVACY.md`).
* **No profile claim flow**: intentionally deferred until a verifiable mechanism exists.
* **No website page for `/ft export` or SavedVariables uploads**, although the addon tells players to paste the export
  string on the website.
* **The installer never updates an addon it installed**; players without CurseForge keep that version.
* **Crash data loss**: anything recorded after the last logout or `/reload` is lost if the client crashes.
* **Corroboration vs collusion**: independent installations are cheap to create; all data is labelled self-reported.
* **Per-process rate limiter and ingestion gate**: with `WEB_CONCURRENCY=2` the effective limits double; move to a
  shared store before running more API processes.
* **Uploader archive retention**: every file version is kept indefinitely.
* **Retention job** for old upload-batch metadata is documented but not automated.
* **Unresolved matches and character merges** can be reviewed but not resolved through the admin API.
* **Accessibility**: semantic HTML, labels and focus styles are in place; no formal audit has been done.

## Recommended next steps

1. Run `FOREVER_LAUNCH_VALIDATION.md` with two testers on the current build and fill in its results table.
2. Review Blizzard's terms (`PRIVACY.md`).
3. Preview `python -m app.cli rematch` on a restored copy of production and decide whether to apply it.
4. Curate the remaining final bosses from real runs.
