# ForeverTracker

Searchable, observed dungeon histories for **World of Warcraft: Forever** characters.

Players who run the ForeverTracker addon record the dungeon runs they join: the party roster, boss encounters,
deaths, totals from Blizzard's built-in damage meter, and equipment. Uploads from many players are reconciled into one
history per run and per character. Anyone can look up a character they grouped with, even if that character never
installed the addon.

> **Status: pre-launch.** Everything except the live game integration is implemented and tested with simulated data.
> The addon has not yet run in a live Forever client; see [`docs/READINESS.md`](docs/READINESS.md) and
> [`docs/FOREVER_LAUNCH_VALIDATION.md`](docs/FOREVER_LAUNCH_VALIDATION.md).

## Quick start (development)

Requirements: Docker, Python 3.12, Node 20+.

```sh
docker compose up -d --build                                  # PostgreSQL :5433, API :8000, website :3000
docker compose exec backend python -m app.cli seed            # ~1,200 synthetic runs, 2,500 characters (~4 min)
```

Open http://localhost:3000, and http://localhost:8000/api/docs for the API.
To try the upload path, send the sample SavedVariables file to the API:
`curl --data-binary @fixtures/savedvariables/ForeverTracker.sample.lua http://localhost:8000/api/v1/ingest/savedvariables`.

## Tests

```sh
python -m venv .venv && . .venv/Scripts/activate   # (bin/activate on Linux/macOS)
pip install -e packages/savedvariables -e "backend[dev]" -e tools/simulator -e "uploader[dev]" lupa
docker compose up -d db                             # tests use the forevertracker_test database on :5433
pytest packages/savedvariables/tests addon/tests uploader/tests backend/tests
cd frontend && npm ci && npm test && npm run build
```

The addon tests run the real addon Lua in a Lua 5.1 VM (`lupa`) against a mock of the Forever client.
`backend/tests/test_e2e_pipeline.py` drives the addon through a dungeon from two players' clients, uploads both
SavedVariables files, and checks reconciliation, conflicts and statistics through the public API.

## Repository

| Path | Contents |
|---|---|
| `addon/ForeverTracker` | The WoW addon (interface 16001). `/ft help` in game. |
| `backend` | FastAPI + SQLAlchemy + Alembic: ingestion, identity, reconciliation, analytics, public and admin API |
| `frontend` | Next.js website |
| `uploader` | Desktop uploader (`forevertracker-uploader`); `background` mode starts with Windows and uploads automatically |
| `packaging` | One-download Windows installer (addon + uploader exe); see [`packaging/README.md`](packaging/README.md) |
| `packages/savedvariables` | Data-only SavedVariables parser shared by the backend and the uploader |
| `tools/simulator` | Synthetic data generator (development only) |
| `schema` | JSON Schema of the upload contract (generated) |
| `deploy`, `docker-compose*.yml` | Deployment |
| `docs` | Research and design documents |

## Documentation

* [Forever addon API research](docs/RESEARCH_FOREVER_API.md): what the client offers, classified by evidence
* [Architecture](docs/ARCHITECTURE.md), [observation schema](docs/OBSERVATION_SCHEMA.md),
  [identity and reconciliation](docs/IDENTITY_AND_RECONCILIATION.md), [statistic definitions](docs/ANALYTICS_DEFINITIONS.md)
* [Data integrity](docs/DATA_INTEGRITY.md), [privacy](docs/PRIVACY.md), [operations](docs/OPERATIONS.md),
  [deployment](docs/DEPLOYMENT.md)
* [Launch-day validation](docs/FOREVER_LAUNCH_VALIDATION.md), [readiness](docs/READINESS.md)

## Code signing policy

The Windows desktop app (`ForeverTrackerUploader.exe`) and its installer are signed with
[Azure Artifact Signing](https://azure.microsoft.com/products/artifact-signing); Windows shows the publisher as
Jordan Stout. Both are built from this repository by GitHub Actions
([`windows-app.yml`](.github/workflows/windows-app.yml)) and signed in the same run, only on the `main` branch, with a
certificate Microsoft holds (no key ever leaves Azure). Releases are published by the maintainer, Jordan Stout. The
addon is plain Lua source and is not signed.

| Role | Members |
|---|---|
| Authors (change the source code without further review) | Jordan Stout ([obelisk2u](https://github.com/obelisk2u)) |
| Reviewers (review every change from outside contributors) | Jordan Stout |
| Approvers (approve each signing request) | Jordan Stout |

**Privacy:** the desktop app uploads the dungeon runs recorded by the addon to the ForeverTracker server, and checks
once a day for a newer version. [`packaging/privacy.txt`](packaging/privacy.txt) lists exactly what it sends and how
to turn it off; the installer shows it before installing anything.

ForeverTracker is not affiliated with or endorsed by Blizzard Entertainment. World of Warcraft is a trademark of
Blizzard Entertainment, Inc.
