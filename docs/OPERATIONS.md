# Operations

All admin endpoints need `Authorization: Bearer $ADMIN_TOKEN`. They are not in the public OpenAPI document, and Caddy
blocks `/api/v1/admin/*` from the internet. The backend image has no `curl`; call them from inside the container with
Python, for example:

```sh
docker compose -f docker-compose.prod.yml exec backend python -c "import os, urllib.request as u; \
  r = u.Request('http://localhost:8000/api/v1/admin/summary', headers={'Authorization': 'Bearer ' + os.environ['ADMIN_TOKEN']}); \
  print(u.urlopen(r).read().decode())"
```

## Daily review

| Endpoint | Shows |
|---|---|
| `GET /api/v1/admin/summary` | Raw observations by status |
| `GET /api/v1/admin/quarantine` | Quarantined records with reasons |
| `GET /api/v1/admin/unresolved-matches` | Observations that could belong to more than one run (review only: re-matching keeps them listed until the evidence settles it) |
| `GET /api/v1/admin/contributors?status=flagged` | Contributors past the quarantine threshold (`flag_evidence`: quarantined records counted since their last restore) |
| `GET /api/v1/admin/identity-claims` | Reports that contradict an established identity: a known GUID under another name or class |
| `GET /api/v1/admin/reports` | Open data reports and suppression requests |

## Actions

| Action | Endpoint |
|---|---|
| Accept a quarantined record | `POST /api/v1/admin/observations/{raw_id}/release` |
| Invalidate one record | `POST /api/v1/admin/observations/{raw_id}/invalidate {"reason": "..."}` |
| Invalidate an upload | `POST /api/v1/admin/uploads/{upload_id}/invalidate {"reason": "..."}` |
| Flag, ban or restore a contributor (optionally invalidating everything they sent) | `POST /api/v1/admin/contributors/{id}/status {"status": "banned", "reason": "...", "invalidate_all": true}`. Restoring (`"active"`) resets its flag evidence, so only new quarantined records flag it again; its counters, records and earlier audit entries stay. Records held while it was flagged still need releasing one by one. |
| Accept or reject an identity claim | `POST /api/v1/admin/identity-claims/{id}/resolve {"status": "accepted", "note": "..."}`. Accepting a name claim makes it the name; accepting a class claim corrects the class (runs that left that entry unidentified are not re-read). |
| Hide or restore a profile | `POST /api/v1/admin/characters/{public_id}/visibility {"visibility": "suppressed", "note": "..."}` |
| Close a report | `POST /api/v1/admin/reports/{report_id}/resolve {"status": "resolved", "note": "..."}` |
| Recompute everything | `POST /api/v1/admin/rebuild`, or `python -m app.cli rebuild` |

Every action recomputes the affected runs and characters in the same transaction and is written to `audit_log`.

## CLI (`python -m app.cli ...`, run inside the backend container)

| Command | Use |
|---|---|
| `rebuild` | After changing an interpretation setting (e.g. `METER_DEATH_INTERPRETATION`) or a statistic definition. It does not re-match observations into runs. |
| `rematch` | Prints what re-matching every stored observation would change (after a matching setting such as `MATCH_PARTY_GUID_VETO` or `MATCH_MIN_SHARED_CHARACTERS` changes, or to repair runs matched by older versions). Writes nothing. `--apply --yes` applies it, on a restored copy first; production also needs `--production`. |
| `recover-outcomes` | After a final boss is added to `final_encounters.json`: prints the stored runs whose outcome is `left`, `disconnected` or `unknown` and that killed that boss (stored outcomes are derived when a run is rebuilt, so they keep their old status until then). Writes nothing. `--apply --yes` makes only those runs completed (*probable*) and recomputes their participants; production also needs `--production`. |
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
