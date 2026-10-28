# Operations

All admin endpoints need `Authorization: Bearer $ADMIN_TOKEN`. They are not in the public OpenAPI document, and Caddy
blocks `/api/v1/admin/*` from the internet. Call them from the host, for example
`docker compose -f docker-compose.prod.yml exec backend sh` followed by `curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/...`.

## Daily review

| Endpoint | Shows |
|---|---|
| `GET /api/v1/admin/summary` | Raw observations by status |
| `GET /api/v1/admin/quarantine` | Quarantined records with reasons |
| `GET /api/v1/admin/unresolved-matches` | Observations that could belong to more than one run |
| `GET /api/v1/admin/contributors?status=flagged` | Contributors past the quarantine threshold |
| `GET /api/v1/admin/reports` | Open data reports and suppression requests |

## Actions

| Action | Endpoint |
|---|---|
| Accept a quarantined record | `POST /api/v1/admin/observations/{raw_id}/release` |
| Invalidate one record | `POST /api/v1/admin/observations/{raw_id}/invalidate {"reason": "..."}` |
| Invalidate an upload | `POST /api/v1/admin/uploads/{upload_id}/invalidate {"reason": "..."}` |
| Flag, ban or restore a contributor (optionally invalidating everything they sent) | `POST /api/v1/admin/contributors/{id}/status {"status": "banned", "reason": "...", "invalidate_all": true}` |
| Hide or restore a profile | `POST /api/v1/admin/characters/{public_id}/visibility {"visibility": "suppressed", "note": "..."}` |
| Close a report | `POST /api/v1/admin/reports/{report_id}/resolve {"status": "resolved", "note": "..."}` |
| Recompute everything | `POST /api/v1/admin/rebuild`, or `python -m app.cli rebuild` |

Every action recomputes the affected runs and characters in the same transaction and is written to `audit_log`.

## CLI (`python -m app.cli ...`, run inside the backend container)

| Command | Use |
|---|---|
| `rebuild` | After changing an interpretation setting (e.g. `METER_DEATH_INTERPRETATION`) or a statistic definition |
| `seed` | Development and staging only: generate and ingest synthetic data (refused in production) |
| `purge-synthetic --yes` | Remove every synthetic record (e.g. before turning staging into a demo of real data) |
| `export-schema`, `export-openapi` | Regenerate contracts (CI checks they are current) |

## Monitoring

* `GET /health` (liveness) and `GET /health/ready` (database plus migration version) for the container and uptime checks.
* `GET /metrics` (Prometheus) on the internal network: `ft_http_requests_total`, `ft_http_request_seconds`,
  `ft_ingest_batches_total{source,status}`, `ft_ingested_observations_total{type,status}`.
* Structured JSON logs on stdout with request IDs; no client addresses, bodies or installation IDs.
* Alerts worth setting: readiness failing; 5xx rate; a spike in `ft_ingested_observations_total{status="quarantined"}`
  (abuse or an addon or client change); no successful ingests for 24 h.
