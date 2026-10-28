# Identity resolution and multi-observer reconciliation

Code: `backend/app/identity/`, `backend/app/reconciliation/`. Tests: `backend/tests/test_ingestion_reconciliation.py`,
`test_simulation_accuracy.py`, `test_e2e_pipeline.py`.

## Character identity

**Namespace.** A character lives in a namespace `(game, region, ruleset)`, for example `us-pve`. Forever has no realm
list, and full names ("First Surname") are unique within a region. Rulesets are kept apart until live validation
shows they share one name space. The realm string is stored as `realm_label` and never used for identity.

**Evidence.** `character_identity_evidence` stores why observations belong to a character:

* `guid` evidence (strong): at most one character per GUID per namespace (partial unique index). GUIDs are opaque
  strings; their internal structure is never parsed.
* `name` evidence (weak, or strong when seen together with a GUID): one row per full name the character was seen
  with, with first and last seen times. A name may appear on several characters.

**Rules**, applied in `resolve_character`:

1. A GUID already known links to its character, even under a different name (a rename). The new name is added as
   evidence and becomes current if the observation is newer.
2. A known GUID with a **different class** is a contradiction. The whole observation is quarantined
   (`guid_class_conflict`) and nothing is merged.
3. A new GUID upgrades a single class-compatible *name-only* character with the same name. Otherwise it creates a
   new character.
4. A name without a GUID links only if exactly one class-compatible character holds that name, or if one holder's
   name evidence covers the observation time (within 30 days) while the others' does not. **Otherwise the roster
   entry stays unidentified.** The run shows "1 roster entry could not be identified safely" instead of merging two
   people.
5. Secret or unavailable identities are never guessed.
6. Synthetic and real data never link to each other.

Characters are never merged automatically on name alone. A merge (`merged_into_id`) is an administrative action;
merged characters redirect to the surviving profile URL.

## Run matching

For each incoming `dungeon_run` observation (`app/reconciliation/matcher.py`):

1. **Candidates**: canonical runs in the same namespace and dungeon whose `[started_at, ended_at or last_observed_at]`
   window is within ±15 minutes of the observation's window, with the same synthetic flag.
2. **Evidence per candidate**:
   * *Vetoes* (any one blocks a match): both have party GUIDs and they differ; both have difficulties and they differ;
     the same boss was killed in both more than 10 minutes apart (two instance copies).
   * *Shared characters*: identified in both, with presence intervals overlapping by at least 60 s. A character cannot
     be in two instances at once.
   * *Aligned encounters*: same boss pull within 120 s.
   * Score = 2 × shared characters + 3 × party-GUID match + aligned encounters + time-overlap ratio.
3. **Decision**:
   * No veto and at least `MATCH_MIN_SHARED_CHARACTERS` (default 2) shared characters, or a party-GUID match plus one
     shared character, counts as a match.
   * An earlier revision of the *same* observation keeps its run unless vetoed (stable run URLs).
   * One match: link. Several: link to the best only if its score is at least 1.5 times the next. Otherwise create a
     separate run marked `unresolved` and store every candidate in `run_match_candidates`.

The matcher was measured against simulator ground truth (`test_simulation_accuracy.py`): **0 false merges, 0 splits,
every multi-observer run reconciled**. That covers simulated late entries, early leavers, missing party GUIDs and
name-only members. Real data may differ.

## Consolidation

`rebuild_run` recomputes everything derived for a run from its accepted observations. It is deterministic and
idempotent.

* **Timing**: earliest start, latest end among finished records (an observer still "in progress" does not hold the
  run open once another observer has finished it).
* **Outcome**: `completed/verified` if any observer saw a completion event; `completed/probable` if the curated final
  boss was killed; else `abandoned`, `in_progress`, `disconnected`, `left` or `unknown`.
* **Participants**: union of presence intervals, most frequent assigned role, highest level, count of observers that
  saw them.
* **Encounters**: the same boss pull from several observers (start within 120 s) becomes one row; contradicting
  kill/wipe results are flagged `conflict`.
* **Deaths**: events for the same character within `DEATH_DEDUPE_WINDOW_SECONDS` (3 s) are one death, with every
  source and observer listed.
* **Wipes**: `encounter_failed` from `ENCOUNTER_END`; `party_wipe` is *inferred* (everyone present died within 20 s).

## Metric conflicts

Candidates per (participant, metric):

* each observer's native-meter totals: coverage `complete_session` only if every session the observer saw was
  captured and the observer was present for at least 95% of the run;
* for deaths, also the deduplicated death events: complete if observers with death tracking covered at least 95% of
  the participant's presence.

Resolution (`app/reconciliation/metrics.py`):

1. Unavailable and secret candidates never become numbers. The metric is published as `unavailable`.
2. Rank by coverage, then status, then source priority (meter before death events for deaths), then coverage ratio.
3. Within the best tier, values agreeing across at least two contributors (counts exactly, amounts within 1%) are
   `corroborated`. Disagreement is `conflicted`: the best-covered value is shown with low confidence and every
   candidate is kept in `conflict`.
4. If two sources disagree at equal coverage, the higher-priority source wins and the result is marked
   `conflict_resolved`.
5. DPS and HPS are derived: total ÷ the meter combat seconds of the same evidence.

## Idempotency and revisions

* `upload_batches (contributor_id, batch_key)` is unique. A repeated batch with the same content returns the original
  result; a reused batch ID with different content is refused (409).
* `raw_observations (contributor_id, observation_key, revision)` is unique. The same revision with the same content
  is a duplicate; with different content it is rejected (`revision_content_conflict`).
* A newer revision supersedes older ones and replaces their contribution. A late, older revision is stored as
  `superseded` and never applied.
* Ingestion holds a transaction-scoped advisory lock, so concurrent uploads of one run cannot create two runs.
