# Observation schema (version 1)

The source of truth is `backend/app/schemas/observations.py`. The generated JSON Schema is
`schema/observation-batch.v1.schema.json` (`python -m app.cli export-schema`). Unknown fields are rejected; every
change to the contract increments `schema_version` (adding an optional field, as 0.2.10 and 0.2.11 did, does not).

How the layers are kept in agreement:

* CI regenerates the JSON Schema and the OpenAPI document and fails if either differs from the committed file, and
  regenerates the frontend's TypeScript types from the OpenAPI document the same way.
* `backend/tests/test_contract.py` (no database needed) runs the real addon in the Lua 5.1 harness, parses and
  extracts its SavedVariables, and checks every batch against both the Pydantic models and the generated JSON
  Schema, for the current addon (`fixtures/savedvariables/ForeverTracker.current.lua`, regenerated with
  `python tools/make_fixtures.py`, which `--check` compares), addon 0.1.0's fixture, and edge cases (missing, null
  and empty values, limits, enums, unknown versions); the two must give the same verdict. Lua's limits
  (`Config.LIMITS`) and the values the addon writes are checked against the schema's limits and enums.

## Batch envelope

```json
{
  "format": "forevertracker.batch",
  "schema_version": 1,
  "batch_id": "sv-3f9c...",            // content-derived: same content => same id
  "installation_id": "ft-0a1b2c...",   // random, created by the addon; the server stores only an HMAC of it
  "created_at": 1792540800,
  "synthetic": false,                  // true only for simulator data; refused in production
  "addon": {"name": "ForeverTracker", "version": "0.2.11", "schema_version": 1},
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
| `addon_version` | `dungeon_run` only, from addon 0.2.10: the version that started recording the run (kept if a newer one resumes it). Absent means an older version. |

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
    "unmatched_sources": 0,                        // 0.2.11+: player sources matched to no one (see below)
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

`flags.marked_completed` (addon 0.2.10): the player marked the run as completed in the addon (the records window's
button or `/ft complete`). The run still ends `unknown` (or `left` from outside), since no completion event came; the
website counts it as completed with `reported` confidence.

All timestamps are **server epoch seconds** (`GetServerTime()`), so different observers' records share one clock.
`local_clock_offset` records the gap between the local and server clocks.

Meter metric keys: `damage_done`, `healing_done`, `absorbs`, `interrupts`, `dispels`, `damage_taken`,
`avoidable_damage_taken`, `deaths`. Per-value status is `observed`, `partial` (some sessions unreadable, or some
player's numbers not attributed), `secret` or `unavailable`. **A value of `null` means unknown; it is never replaced
by 0.**

The addon gives a meter source to a roster member by GUID, else by an exact full name (`First Surname` or
`First-Surname`), else by a first name that only one member has; it never guesses between two members who share a
first name. Player sources it cannot attribute are counted in `meter.unmatched_sources` (from 0.2.11; pets and
other non-player sources are left out). A member absent from every captured session's sources gets 0: the server
treats that as an observed 0 only when `unmatched_sources` is 0. With unattributed sources, or from an older addon
that does not report the count, a member with no damage, healing or damage taken while others have numbers is
**unknown** (published as unavailable), and with unattributed sources no total is complete.

Each boss attempt in `encounters[]` carries `meter` (from 0.2.0): the summed totals of the sessions overlapping it,
`combat_seconds`, `sessions`, and `status` (`partial` when the observer died during it, or a player's numbers in it
could not be attributed). Each `meter.sessions[]` entry names the `encounter_id` it was matched to.

## `character_snapshot`

`observed_at`, `source` (`self` or `inspect`), `subject` (identity, class, race, level), `equipment` (`status`,
`average_item_level`, `items[]` with `slot`, `item_id`, `item_level`, `enchant_id`, `gem_ids`, `quality`, `link`) and
`talents` (`status`, `spec_id`, `import_string`).

Addon 0.2.6 also sent each item's tooltip text as `tooltip`. The server accepts the field so those snapshots are not
rejected, and drops it: it is never stored or shown.

`source: "group"` is a group member seen anywhere, not only in a dungeon (`Collectors/Group.lua`): `subject` carries
GUID, name, surname, class and race only, never level or role, and there is no `equipment` or `talents`. The addon
records a member again only when one of those fields changes or after a week, and drops these records first when its
400-record buffer is full.

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

**A file written by a newer addon** (`schema_version` higher than this addon's, missing or not a number) is left
exactly as loaded: that session records nothing, keeps a store that is never saved, and says so in chat and in
`/ft status`. The client then writes the untouched table back at logout. The uploader and the API refuse such a
file (`unsupported schema_version`); the uploader keeps its archived copy.

## Lua table shapes

A Lua table can be a list, a map, or both. Before anything is hashed, uploaded or validated, the extractor (shared by
the uploader and the API's SavedVariables and `/ft export` endpoints) normalizes every table with
`forevertracker_sv.shapes.normalize`:

| Table | Becomes |
|---|---|
| Keys exactly 1..n (a list) | a JSON array |
| Only named keys | a JSON object |
| Only positive whole-number keys with gaps (a list with `nil` holes) | a JSON array in key order |
| Empty (`{}`) | `[]`; fields that expect an object accept it as `{}` |
| Positions and names mixed, or keys that are neither (`true`, `1.5`, `0`, `-1`) | **refused**, with the path, e.g. `ForeverTrackerDB.observations[3].flags: mixes list positions (1) with named fields ('a')` |

A refused table rejects only its own record: the rest of the file uploads, the API response lists it under
`summary.rejected_records`, and `disclose` names it. If the record list itself, `client` or `ForeverTrackerDB` is
ambiguous, the whole file is refused. The source file is never changed. The `/ft export` string is JSON, whose keys
are always strings, so there the addon's `"1"`, `"2"`... keys count as list positions. A batch posted to
`/api/v1/ingest/batches` is taken as written: lists must be JSON arrays.
