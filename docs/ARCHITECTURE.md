# ForeverTracker architecture

ForeverTracker is a **historical player database**. Addon users record what their game client shows about the
groups they play in. Uploads from many users are reconciled into one canonical history per dungeon run and per
character, so that any character can be looked up even if they never installed the addon.

## Components

```text
 WoW: Forever client
   └─ ForeverTracker addon (Lua, no network)          addon/ForeverTracker
        writes SavedVariables on logout / exit / /reload
                │
                ▼
 desktop uploader                                                   uploader/
   archives every file version, uploads new batches over HTTPS
                │
                ▼
 FastAPI backend                                                    backend/app
   ingestion  ─ schema validation (app/schemas/observations.py)
              ─ plausibility checks → accept / quarantine / reject (app/integrity)
              ─ raw observation store (system of record)
   identity   ─ evidence-based character resolution (app/identity)
   reconciliation ─ run matching, consolidation, metric resolution (app/reconciliation)
   analytics  ─ character aggregates, wipes (app/analytics, app/services)
   public API ─ /api/v1/... (OpenAPI: docs/openapi.json)
                             ▼
 PostgreSQL 16 (Alembic migrations, backend/migrations)
                             ▼
 Next.js website (server components → API)                         frontend/
```

Shared code: `packages/savedvariables` (a data-only SavedVariables parser and export extractor) is used by the backend
and the uploader. `tools/simulator` generates synthetic, development-only data.

Each component works on its own. The addon has no dependency on the website. The website and API need no game
client. The API accepts three upload channels with the same contract, so a collection mechanism can change after
launch without touching the backend.

## Contracts between components

| Interface | Definition | Versioning |
|---|---|---|
| Addon → files | `ForeverTrackerDB` SavedVariable (`format = "forevertracker.savedvariables"`, `schema_version = 1`). Observations are stored already in the upload shape. | `schema_version`; the backend rejects unknown versions. |
| Files → API | Observation batch, `schema/observation-batch.v1.schema.json` (generated from `app/schemas/observations.py`). See [`OBSERVATION_SCHEMA.md`](OBSERVATION_SCHEMA.md). | `schema_version: 1`; unknown fields are rejected. |
| API → website | OpenAPI document `docs/openapi.json`; TypeScript types generated into `frontend/lib/api-schema.d.ts`. | CI fails if either is stale. |

## Data model (PostgreSQL)

Raw observations are the **system of record**. Every derived table can be rebuilt from accepted raw observations
(`python -m app.cli rebuild`).

| Layer | Tables |
|---|---|
| Ingestion | `contributors` (HMAC of the installation ID only), `upload_batches`, `raw_observations` (validated payload, revision, status, quarantine reasons) |
| Identity | `namespaces` (game, region, ruleset), `characters`, `character_identity_evidence` (GUID and name evidence; one GUID per namespace) |
| Runs | `dungeons` (learned catalog, optionally curated), `dungeon_runs` (canonical), `run_observations` (raw → canonical links and match evidence), `run_match_candidates` (ambiguous matches kept for review) |
| Run contents | `run_participants` (many-to-many with presence, role, completeness), `run_encounters`, `run_deaths` (deduplicated), `metric_observations` (every candidate value with provenance), `participant_metrics` (resolved value, resolution, confidence) |
| Progression | `equipment_snapshots`, `level_observations` |
| Aggregates | `character_stats` (materialised; definition version recorded) |
| Moderation | `data_reports`, `audit_log` |

Key indexes: trigram GIN on `characters.full_name_normalized` (partial search); `(namespace_id, full_name_normalized)`
(exact search); `(namespace_id, dungeon_id, started_at)` (run matching window); `(character_id, run_id)` on
participants (history); partial unique index on GUID evidence.

## Dungeon-run state machine

Implemented in `addon/ForeverTracker/Sessions/RunTracker.lua`; tested in `addon/tests/test_runs.lua`.

```text
                enter 5-player dungeon                          leave instance
    (none) ──────────────────────────► ACTIVE ─────────────────────────────────► SUSPENDED
                                        ▲  │  PLAYER_LOGOUT (logout, exit, /reload)    │ │
                                        │  └────────────────────────────────────────►│ │
                                        │                                            │ │
                                        └── same dungeon again within 15 min ────────┘ │
                                            (corpse run, /reload, relog)               │
                                                                                       ▼
                       grace expired / entered another dungeon ───────────────► FINISHED
```

Final states: `completed` (only with a completion event: `LFG_COMPLETION_REWARD`, `SCENARIO_COMPLETED`,
`CHALLENGE_MODE_COMPLETED`), `abandoned` (instance-abandon vote passed), `left` (left and did not return),
`disconnected` (the session ended inside the dungeon and the player did not return), `unknown`. Leaving an instance
is never a completion. Boss kills are encounters, not completion evidence.

Each save bumps the record's `revision`. The backend applies the newest revision and keeps older ones as
`superseded`, so a run first uploaded "in progress" (after a `/reload`) is later replaced by its final version in the
same canonical run.

## Reconciliation in one paragraph

An incoming run observation is matched against canonical runs in the same namespace and dungeon whose time window
overlaps. A match needs no veto (different party GUID, different difficulty, the same boss killed at incompatible
times) and at least two characters present in both records at overlapping times, or a shared party GUID plus one such
character. Ambiguous cases become separate runs marked `unresolved`, with the candidates stored. Consolidation
rebuilds the run from all linked observations: union of presence, clustered boss pulls, deduplicated deaths
(3-second window), metric candidates and resolution. Details: [`IDENTITY_AND_RECONCILIATION.md`](IDENTITY_AND_RECONCILIATION.md).

## Concurrency and scaling

* Ingestion runs under one transaction-scoped PostgreSQL advisory lock, so batches apply serially. This makes
  matching race-free. Measured inside the development compose network: about 12 batches/s (about 24 observations/s)
  while seeding a full synthetic dataset, including matching, full run rebuilds and aggregate recomputation. That is
  ample for launch, since each user uploads a few batches per play session.
* **Scaling path**, in order: (1) more API replicas for reads (stateless; move the in-memory rate limiter to Redis);
  (2) partition the ingestion lock by `(namespace, dungeon)` instead of one global key; (3) move ingestion to a
  worker that drains a queue table (`upload_batches.status = 'received'`), keeping the API's synchronous response
  optional; (4) PostgreSQL read replica for the public API; (5) partition `metric_observations` and
  `raw_observations` by month.
* Each public GET sets `Cache-Control: public, max-age=30..300`; a CDN in front of Caddy can serve most traffic.

## Repository layout

```text
addon/ForeverTracker/        the addon (Core, Collectors, Sessions, Export, Diagnostics)
addon/tests/                 Lua 5.1 tests against a mocked Forever client (run via lupa)
backend/app/                 api, schemas, models, ingestion, identity, reconciliation, analytics, integrity, services
backend/migrations/          Alembic
backend/tests/               unit, API, end-to-end, simulation-accuracy tests
frontend/                    Next.js app (app/, components/, lib/, tests/)
uploader/                    optional desktop uploader (CLI + tkinter window)
packages/savedvariables/     shared, data-only SavedVariables parser
tools/simulator/             synthetic data generator (development only)
schema/                      generated JSON Schema of the upload contract
deploy/                      Caddyfile, backup script, environment template, Postgres init
docs/                        research, design and operations documents
```
