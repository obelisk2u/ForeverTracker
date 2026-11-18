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

1. A GUID already known links to its character, even under a different name. A different name is a **claim**
   (`identity_claims`, one row per contributor): the public name and the name history change only once
   `IDENTITY_RENAME_MIN_CONTRIBUTORS` (default 2) distinct contributors report it with a newer timestamp, or a
   moderator accepts the claim. One upload cannot rename an established character. An older record that carries a
   name the character had before is history, not a claim.
2. A known GUID with a **different class** is a contradiction (a class never changes, so one side is wrong). It is
   recorded as a claim for review and nothing is merged: in a run, that roster entry stays unidentified and the rest
   of the run is kept; a snapshot about that character is quarantined (`guid_class_conflict`). Neither counts
   against the uploader (see "Contributor trust" in [`DATA_INTEGRITY.md`](DATA_INTEGRITY.md)).
3. A new GUID upgrades a single class-compatible *name-only* character with the same name. Otherwise it creates a
   new character.
4. A name without a GUID links only if exactly one class-compatible character holds that name, or if one holder's
   name evidence covers the observation time (within 30 days) while the others' does not. **Otherwise the roster
   entry stays unidentified.** The run shows "1 roster entry could not be identified safely" instead of merging two
   people.
5. Secret or unavailable identities are never guessed.
6. Synthetic and real data never link to each other.

Characters are never merged automatically. `characters.merged_into_id` is honoured (the old profile URL redirects)
but nothing sets it yet: there is no character-merge action. Moderators review claims with
`GET /api/v1/admin/identity-claims` and `POST /api/v1/admin/identity-claims/{id}/resolve` (see
[`OPERATIONS.md`](OPERATIONS.md)).

## Run matching

Code: `app/reconciliation/cluster.py`. Matching is a function of the current accepted observations, not of the
order uploads, revisions and retries arrive in: whenever a `dungeon_run` observation is applied, the decision is
recomputed for every observation it could belong with.

1. **Neighbourhood**: accepted observations in the same namespace and dungeon whose windows are within
   `MATCH_TIME_PADDING_SECONDS` (15 minutes) and that share a character or party GUID with it, transitively, plus
   every observation already in a run involved.
2. **Evidence**, observation against a group of observations (their raw records, never derived rows):
   * *Vetoes* (any one blocks a match): the group's single party GUID differs (unless `MATCH_PARTY_GUID_VETO=false`);
     difficulties differ; the same boss killed more than 10 minutes apart (two instance copies; this holds even
     when another pull of that boss lines up).
   * *Shared characters*: identified on both sides, with presence overlapping by at least 60 s.
   * *Aligned encounters*: same boss pull within 120 s.
   * Score = 2 × shared characters + 3 × party-GUID match + aligned encounters + time-overlap ratio.
3. **Clustering**, in start-time order: no veto and at least `MATCH_MIN_SHARED_CHARACTERS` (default 2) shared
   characters, or a party-GUID match plus one, is a match. One matching group: join it. Several: join the best if
   its score is at least 1.5 times the next; otherwise the observation becomes its own run marked `unresolved`,
   its candidates are stored in `run_match_candidates` for review, and no later upload joins it.
4. **Runs and IDs**: each group keeps the existing run holding most of its observations, so public run IDs stay
   put (the first part of a run the addon splits keeps the merged run's ID). A run that loses every observation is
   merged into the run that received them (`merged_into_id`): its URL redirects instead of disappearing. Each move
   is recorded in the link's `match_evidence.moved_from`.

So an early `/reload` (a first revision covering seconds of the run), a stored run that the addon later splits, a
second observer arriving before or after either, and retries all end in the same runs
(`backend/tests/test_reconciliation_convergence.py`).

**Existing data**: `python -m app.cli rematch` prints what re-matching every stored observation would change
(moves, merges, new runs, unresolved observations) and writes nothing. `--apply --yes` applies it (production also
needs `--production`): try it on a restored copy first. `python -m app.cli rebuild` recomputes runs' contents and
statistics but never re-matches.

The matcher was measured against simulator ground truth (`test_simulation_accuracy.py`): **0 false merges, 0 splits,
every multi-observer run reconciled**. That covers simulated late entries, early leavers, missing party GUIDs and
name-only members. Real data may differ.

## Consolidation

`rebuild_run` recomputes everything derived for a run from its accepted observations. It is deterministic and
idempotent.

* **Timing**: earliest start, latest end among finished records (an observer still "in progress" does not hold the
  run open once another observer has finished it).
* **Outcome**: `completed/verified` if any observer saw a completion event; `completed/probable` if the curated final
  boss was killed; else `abandoned` if an abandon vote passed; else `completed/reported` if an observer marked the run
  as completed in the addon (`flags.marked_completed`); else `in_progress`, `disconnected`, `left` or `unknown`. Only
  `verified` completions count in completion statistics.
* **Participants**: union of presence intervals, most frequent assigned role, highest level, count of observers that
  saw them. Someone in the group for under `PASSED_THROUGH_SECONDS` (5 minutes) and at no boss pull only passed
  through (left as the run began and was replaced): they are not a participant, so the run does not appear in their
  history or statistics, and the run page names them separately.
* **Encounters**: the same boss pull from several observers (start within 120 s) becomes one row; contradicting
  kill/wipe results are flagged `conflict`.
* **Deaths**: events for the same character within `DEATH_DEDUPE_WINDOW_SECONDS` (3 s) are one death, with every
  source and observer listed.
* **Wipes**: `encounter_failed` from `ENCOUNTER_END`; `party_wipe` is *inferred* (everyone present died within 20 s).

## Metric conflicts

Candidates per (participant, metric):

* each observer's native-meter totals: coverage `complete_session` only if every session the observer saw was
  captured and the observer was present for at least 95% of the run;
  * runs recorded before addon 0.2.10 (no `addon_version`): a session "captured" at 1 s or less was read as the group
    pulled and never again. When every session the observer captured was read that way, their totals are
    `unavailable` (shown as —) rather than near-zero numbers;
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
* Within a batch, new revisions of observations the contributor sent before are applied first, then new observations.
  A new revision can shrink its run: the addon splits a run it stored as one when the group reset the dungeon and went
  straight back in (a boss it had killed was pulled again), sending the first part as a new revision and the second as
  a new observation, which must be matched against the corrected run rather than join the merged one.
* Ingestion holds a transaction-scoped advisory lock, so concurrent uploads of one run cannot create two runs.
* Re-sending anything (a batch, an older revision, the same file again) leaves the runs as they were.
