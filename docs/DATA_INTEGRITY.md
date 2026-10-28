# Data integrity and abuse prevention

## Threat model

Uploads are **self-reported**. Anyone can edit a SavedVariables file or hand-craft an upload. A checksum proves only
that a payload was not corrupted in transit, not that the gameplay happened. ForeverTracker therefore never labels
data as verified by Blizzard. It limits the damage any one contributor can do, and it marks a value as
corroborated only when independent contributors agree.

Realistic abuse: inflating one's own DPS, fabricating runs for someone else's name, flooding the API, and injecting
data to poison another character's profile.

## Controls

| Layer | Control | Where |
|---|---|---|
| Transport | HTTPS (Caddy); request body cap 9 MB at the proxy, 2 MB per JSON batch and 8 MB per SavedVariables file at the API | `deploy/Caddyfile`, `app/api/deps.py` |
| Rate limits | Per installation (120/h) and per client address (300/h), sliding window. Addresses are hashed with a per-process salt and never stored. | `app/integrity/ratelimit.py` |
| Parsing | SavedVariables are parsed by a data-only grammar (no Lua execution), with limits on size, depth, string length, value count and number range | `packages/savedvariables` |
| Schema | Strict Pydantic models; unknown fields rejected; bounded strings, lists and numbers | `app/schemas/observations.py` |
| Plausibility | Reject: internally inconsistent records (end before start, unknown unit references, duplicate GUIDs). Quarantine: timestamps before the Forever beta or in the future, runs over 6 h, more concurrent members than the instance allows, levels above the cap, DPS/HPS above 60,000, implausible counts, meter combat time longer than the run, completion without evidence | `app/integrity/sanity.py` |
| Identity | GUID/class contradictions are quarantined; names alone never merge characters | `app/identity/resolver.py` |
| Duplicates | Unique constraints on batches and observation revisions; content digests | `app/ingestion/service.py` |
| Contributor trust | A contributor reaching `CONTRIBUTOR_FLAG_THRESHOLD` (5) quarantined records is `flagged`: everything they upload afterwards is quarantined until review. `banned` contributors are refused. | `ingestion/service.py`, `services/moderation.py` |
| Publication | Quarantined records are stored but never applied. | `reconciliation/consolidate.py` |
| Synthetic data | Refused in production; filtered from production responses as a second line of defence | `config.py`, `services/visibility.py` |

## Trust classification of a value

| Class | Meaning | Where it can appear |
|---|---|---|
| Corroborated | Two or more independent contributors report agreeing values with full coverage | Profiles, run pages |
| Single source | One contributor | Profiles and run pages (no ✓ mark) |
| Conflicted | Contributors disagree | Run pages (⚠), profile averages |
| Partial | Incomplete coverage | Run pages (◐); excluded from averages |
| Unavailable | The client did not expose it | Shown as "—" |
| Quarantined / invalidated | Failed checks or removed by moderators | Nowhere public |

Corroboration resists a single fabricating contributor, but not several colluding installations. Installation IDs
are free to create. All data is therefore labelled as self-reported, and moderators can invalidate a contributor's
entire history in one action.

## Invalidating fraudulent data

```text
POST /api/v1/admin/observations/{raw_id}/invalidate        {"reason": "..."}
POST /api/v1/admin/uploads/{upload_id}/invalidate          {"reason": "..."}
POST /api/v1/admin/contributors/{id}/status                {"status": "banned", "reason": "...", "invalidate_all": true}
POST /api/v1/admin/observations/{raw_id}/release           (accept a quarantined record after review)
```

Invalidation marks raw observations `invalidated` (they are kept for audit), unlinks them from runs, rebuilds every
affected run (deleting runs left with no observations) and recomputes the statistics of every affected character in
the same transaction. Each action is written to `audit_log`. See [`OPERATIONS.md`](OPERATIONS.md).
