# Observation schema (version 1)

The source of truth is `backend/app/schemas/observations.py`. The generated JSON Schema is
`schema/observation-batch.v1.schema.json` (`python -m app.cli export-schema`). Unknown fields are rejected; every
change to the contract increments `schema_version`.

## Batch envelope

```json
{
  "format": "forevertracker.batch",
  "schema_version": 1,
  "batch_id": "sv-3f9c...",            // content-derived: same content => same id
  "installation_id": "ft-0a1b2c...",   // random, created by the addon; the server stores only an HMAC of it
  "created_at": 1792540800,
  "synthetic": false,                  // true only for simulator data; refused in production
  "addon": {"name": "ForeverTracker", "version": "0.1.0", "schema_version": 1},
  "client": {"game_version": "1.60.1", "build": "70532", "interface": 16001, "locale": "enUS", "project_id": 1},
  "observations": [ ... ]              // 1..500; each validated independently
}
```

The envelope is validated first. Then each observation is validated, checked for plausibility and applied on its
own, so one bad record never rejects the rest of the batch.

## Common observation fields

| Field | Meaning |
|---|---|
| `type` | `dungeon_run`, `character_snapshot` or `probe_report` |
| `observation_id` | Stable per installation (e.g. `r-1792000000-12`) |
| `revision` | Increases every time the addon saves a changed version of the record |
| `recorded_by` | The observer's character (`guid`, `name`, `surname`, `identity_status`) |
| `namespace` | `region_id`, `region_name`, `ruleset` (`pve`/`pvp`/`rp`/`hardcore`/`unknown`). Forever names are unique per region. |
| `realm_label` | Whatever `GetRealmName()` returned. Recorded, **never** used for identity. |
| `client_build` | Client build number |

`identity_status` is `ok`, `secret` (the client returned a secret value) or `unavailable`. A secret identity is
never guessed at; such roster entries stay unidentified.

## `dungeon_run`

```json
{
  "type": "dungeon_run",
  "instance": {"map_id": 990001, "name": "Hall of Thanes", "instance_type": "party", "difficulty_id": 1, "difficulty_name": "Normal", "max_players": 5},
  "party_guid": "Party-...",                       // from GROUP_JOINED when available
  "timing": {"started_at": 1792000000, "ended_at": 1792001800, "last_updated_at": 1792001800, "clock": "server"},
  "state": "completed",                            // in_progress | completed | left | abandoned | disconnected | unknown
  "completion": {"status": "verified", "evidence": [{"kind": "lfg_completion_reward", "at": 1792001790}]},
  "timeline": [{"at": 1792000000, "kind": "entered", "detail": {"map_id": 990001}}],
  "roster": [{
    "ref": "u2", "guid": "Player-4620-0000A2", "name": "Mah", "surname": "Beardlong", "identity_status": "ok",
    "class_file": "WARRIOR", "race_file": "Dwarf", "level": 18, "role": "TANK", "is_observer": false,
    "presence": [{"start": 1792000000, "end": 1792001800}], "connection_drops": 0
  }],
  "encounters": [{"encounter_id": 3001, "name": "Thane Ironvow", "started_at": 1792000300, "ended_at": 1792000390, "success": true}],
  "deaths": [{"unit_ref": "u2", "at": 1792000350, "source": "unit_state", "encounter_id": 3001}],
  "meter": {
    "status": "observed",                          // observed | partial | secret | unavailable | disabled
    "combat_seconds": 250.0,                       // sum of captured session durations
    "sessions": [{"session_id": 3, "duration_sec": 90.0, "status": "captured", "captured_at": 1792000400}],
    "totals": [{"unit_ref": "u2", "guid": "Player-4620-0000A2", "metrics": {
      "damage_done": {"value": 89000, "status": "observed", "sessions": 3},
      "deaths": {"value": 1, "status": "observed", "sessions": 3}
    }}],
    "death_entries": [{"unit_ref": "u2", "session_id": 3, "death_time_sec": 10.0, "death_recap_id": 7000, "total": 1}]
  },
  "collection": {"identity": "active", "encounters": "active", "deaths_unit_state": "active", "meter": "active", "inspect": "active", "talents": "disabled"},
  "flags": {"resumed_after_reload": true}
}
```

All timestamps are **server epoch seconds** (`GetServerTime()`), so different observers' records share one clock.
`local_clock_offset` records the gap between the local and server clocks.

Meter metric keys: `damage_done`, `healing_done`, `absorbs`, `interrupts`, `dispels`, `damage_taken`,
`avoidable_damage_taken`, `deaths`. Per-value status is `observed`, `partial` (some sessions unreadable), `secret` or
`unavailable`. **A value of `null` means unknown; it is never replaced by 0.** A member absent from every captured
session's sources has an observed 0 for that metric, because the meter covered them and they contributed nothing.

## `character_snapshot`

`observed_at`, `source` (`self` or `inspect`), `subject` (identity, class, race, level), `equipment` (`status`,
`average_item_level`, `items[]` with `slot`, `item_id`, `item_level`, `enchant_id`, `gem_ids`, `quality`, `link`) and
`talents` (`status`, `spec_id`, `import_string`).

## `probe_report`

`observed_at` and `results[]` of `{check, status (pass|fail|warn|skip|info), detail}`. These are stored for launch
validation and are not shown publicly.

## Metric provenance on the server

Every candidate value becomes a row in `metric_observations`, and the public value in `participant_metrics`
carries:

```json
{
  "metric": "deaths", "value": 2, "unit": "count",
  "source": "native_damage_meter",        // or death_events
  "status": "observed",                   // observed | incomplete | estimated | unavailable | unverified
  "coverage": "complete_session",         // complete_session | partial_session | unknown
  "resolution": "corroborated",           // single_source | corroborated | conflicted | conflict_resolved
  "confidence": "high",
  "contributors": 2,
  "derived": false
}
```

## SavedVariables layout

`ForeverTrackerDB` (account-wide) contains `format`, `schema_version`, `installation_id`, `load_count`, `settings`,
`observations` (ring buffer, 400 records by default), `active_run` (the run in progress, already in the upload shape),
`active_state` (internal bookkeeping, never uploaded), `diagnostics` and `dropped`. The extractor
(`packages/savedvariables/forevertracker_sv/export.py`) keeps the newest revision of each observation and splits
them into batches of at most 200.
