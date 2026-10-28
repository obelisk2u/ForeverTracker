# Forever launch-day validation

**Purpose:** confirm, in the live World of Warcraft: Forever client, every API behaviour ForeverTracker depends on, then
switch verified collectors on through feature flags. The backend and website do not need rewriting for any outcome;
each test below names the flag or setting its result controls.

Everything in the addon was built against Blizzard's generated Forever API documentation (build 1.60.1.70009), a
captured API surface (build 69893) and a mock client. **None of it has run in a live Forever client.** Until these
tests pass, treat every collector marked *needs validation* as unverified.

Background for each test is in [`RESEARCH_FOREVER_API.md`](RESEARCH_FOREVER_API.md).

---

## 0. Setup (15 minutes)

| Item | Detail |
|---|---|
| Testers | **Two** accounts with the addon (A and B) plus three other players without it. Tests 1–9 need only A; test 10 and the cross-check need A and B in the same group. |
| Build | Record the client version shown by `/ft probe` (`client.build` line), and the date. |
| Addon | Copy `addon/ForeverTracker` to `World of Warcraft\_forever_\Interface\AddOns\` (or run the installer). New addons are enabled by default; check the AddOns list at character select. If it shows **Out of date**, the client's interface number moved past 16001: update `## Interface` in the TOC. |
| Debug | `/ft debug on`. Install BugSack/BugGrabber if available, to capture Lua errors. |
| Damage meter | Open Blizzard's damage meter (Options → Gameplay Enhancements). Record whether it is **enabled**; test 5 runs with it both on and off. |
| Record sheet | Copy the results table at the end of this document and fill it in as you go. |

Useful built-ins: `/dump <expression>` prints a value (secret values may print as `<secret>` or error; record what you see), and `/reload`.

After any test that changes data, **log out (or /reload)** so the client writes `WTF\Account\<ACCOUNT>\SavedVariables\ForeverTracker.lua`, then keep a copy of that file next to your notes.

---

## 1. Party names and identifiers can be exported

**Question:** Do `UnitName`/`UnitNameUnmodified`, `UnitGUID`, `UnitClass`, `UnitRace`, `UnitLevel` and `UnitGroupRolesAssigned` return readable (non-secret) values for party members, and is the second name value a surname?

Steps:
1. Form a 5-player party **outside** any instance. Run `/ft probe`.
2. Check: `names.regional` = pass; `identity.player` = pass; `identity.party` = pass with `ok=4 secret=0 unavailable=0 without_guid=0`.
3. `/dump UnitName("party1")` → expect two strings: first name, surname. Write down which is which.
4. `/dump UnitGUID("party1")`, `/dump GetRealmName()`, `/dump GetCurrentRegion()`, `/dump GetCurrentRegionName()`, `/dump RegionalUniqueNamesEnabled()`.
5. Enter a 5-player dungeon. Repeat steps 1–4 **inside**, both out of combat and **during** combat (put the `/dump` on an action-bar macro).

Expected: identical results inside and outside, in and out of combat.

| Result | Action |
|---|---|
| All readable everywhere | Collector `identity` stays on (default). |
| Secret only in combat | No change: the addon reads identity at roster changes; confirm with test 2 that rosters are complete. |
| GUIDs secret in dungeons | Runs will match on names only (weaker). Raise `MATCH_MIN_SHARED_CHARACTERS` to 3 in the backend environment; note in READINESS. |
| `RegionalUniqueNamesEnabled()` is false or the second value is a realm | Set the namespace rule in `app/identity/namespaces.py` and re-check test data; surnames would be wrong in stored names. **Stop and investigate.** |
| `GetRealmName()` / region values | Record them. If `GetCurrentRegionName()` is empty, confirm `GetCurrentRegion()` maps to the right region in `REGION_BY_ID` (`backend/app/identity/namespaces.py`). |

## 2. Roster changes are recorded

1. In a dungeon with 5 players, run `/ft status` (expect `5 member(s)`).
2. Have one player leave the group, then invite a replacement who zones in.
3. Have one player disconnect for 30 s (close the client) and reconnect.
4. Leave the dungeon, wait, log out. Open `ForeverTracker.lua`.

Expected in the newest `dungeon_run` record: 6 roster entries; the leaver's `presence` interval ends when they left; the replacement's starts when they joined; the disconnected player has `connection_drops = 1`; `timeline` contains `roster_changed` entries.

| Result | Action |
|---|---|
| As expected | None. |
| `GROUP_ROSTER_UPDATE` not firing in instances | Investigate; the 1 s ticker only polls deaths, not the roster. |

## 3. Equipment and talent inspections work

1. Outside combat, near the party, wait 30 s after zoning in. Log out and inspect `ForeverTracker.lua`.
2. Expect `character_snapshot` records with `source = "inspect"` for party members, `equipment.items` with item IDs and item levels, and `average_item_level` set.
3. `/ft enable talents`, `/reload`, wait for inspections (or `/ft purge confirm` first to clear signatures), log out. Expect `talents.status = "observed"` with an `import_string` for inspected players.
4. Repeat with a party member 50+ yards away (expect no snapshot, no errors).

| Result | Action |
|---|---|
| Equipment captured | Keep `inspect` on. |
| Item levels missing (`item_level` null) | Item data was not cached; acceptable. Note it. |
| `NotifyInspect` fails in dungeons | `/ft disable inspect` by default (ship with `inspect = false` in `Core/Config.lua`). |
| Talent strings captured and correct (import them in the talent UI) | Change the `talents` default to `true` in `Core/Config.lua`. |

## 4. Dungeon session boundaries are reliable

Run each scenario and note the final `state` of the record after logging out:

| Scenario | Expected `state` | Expected `completion` |
|---|---|---|
| A. Full run via the group finder, kill the last boss, leave | `completed` | `verified`, evidence `lfg_completion_reward` |
| B. Full run with a manually formed group | **record what happens.** If no completion event fires, `unknown` | `none` |
| C. Die, release, run back in (corpse run < 15 min) | one record, timeline `left_instance` → `reentered` | — |
| D. `/reload` inside | one record, `flags.resumed_after_reload = true` | — |
| E. Log out inside, log back in within 15 min | one record, `flags.resumed_after_login = true` | — |
| F. Log out inside, come back after 20 min | `disconnected` | `none` |
| G. Leave after two bosses and do not return | `left` (after 15 min) | `none` |
| H. Instance abandon vote passes | `abandoned` | `none` |

Also run `/dump GetInstanceInfo()` inside each dungeon and record the 8th value (map ID) per dungeon. **Add every map ID and the final boss's encounter ID to the curated dungeon catalog** (`dungeons.final_encounter_id`, set with an Alembic data migration) so "final boss killed" can count as *probable* completion.

| Result | Action |
|---|---|
| Scenario B gives no completion event | Expected limitation. Completion for manual groups relies on the curated `final_encounter_id` (probable). |
| `ENCOUNTER_START/END` do not fire for 5-player bosses | `encounters` collector shows `unavailable`; completion falls back to events only. Note in READINESS. |
| `SCENARIO_COMPLETED` fires for things that are not dungeon completions | Remove that event from `RunTracker.register`. |

## 5. Native damage-meter statistics are accessible after combat

1. In a dungeon, pull one trash pack, kill it, wait 10 s out of combat, then `/ft probe`.
2. Expect `meter.available` = pass, `meter.sessions` ≥ 1, and **`meter.read` = pass** with `secret=0`.
3. Repeat `/ft probe` **during** combat: `meter.read` should be `warn` (secret while in combat), which is expected.
4. Measure how long values stay secret after combat: macro `/run C_Timer.After(1, function() local s=C_DamageMeter.GetAvailableCombatSessions(); local x=C_DamageMeter.GetCombatSessionFromID(s[#s].sessionID, Enum.DamageMeterType.DamageDone); print(issecretvalue(x.combatSources[1].totalAmount)) end)`, varying the delay 0.5–10 s.
5. Record how many sessions one dungeon run creates (`#C_DamageMeter.GetAvailableCombatSessions()` before and after) and whether old sessions disappear (count at the end of a long run).
6. Repeat with the damage meter **disabled** in options.

| Result | Action |
|---|---|
| Readable within 8 s after combat, all sessions retained | Keep `meter` on (default). |
| Readable, but only after longer than 8 s | Extend `meter_retry_delays` in `Core/Config.lua` (e.g. add 15, 30). |
| Sessions expire during a run | Coverage will show `partial`; consider capturing per session more eagerly. Note the retention limit in READINESS. |
| Never readable inside dungeons (restricted map) | Ship with `meter = false`. Profiles still show deaths, encounters and rosters; DPS/HPS/interrupts show "—". |
| Meter must be enabled in options to track | Document in the addon's install notes and the website's download page. |

## 6. Damage-meter values can be serialised

1. After test 5, log out. Open `ForeverTracker.lua` and find the run's `meter` block.
2. Expect `status = "observed"`, `sessions` with `status = "captured"`, and per-member `totals` with numeric `value`s. **No** `<secret>`-like strings or missing values where the meter showed numbers.
3. Upload the file on the website (or `forevertracker-uploader sync`). Expect the run page to show the same totals as Blizzard's meter **Current/Combat** view summed over the run's fights (allow rounding).

| Result | Action |
|---|---|
| Matches the meter | Mark meter values as validated in READINESS. |
| Totals double-count (e.g. pets listed separately and also merged) | Adjust `Meter.captureSession` to skip pet sources; re-test. |

## 7. Individual deaths can be counted

1. Have the tank die once on a boss and once on trash, and have a DPS die, release and run back.
2. Have a hunter use Feign Death.
3. After the run: the record's `deaths` list should contain exactly 3 entries (source `unit_state`, or `player_dead` for the observer), none for Feign Death.
4. Compare with the meter: the `death_entries` list and the `deaths` metric in `totals`.
   * If the meter's **Deaths** view lists **one entry per death**, `death_entries` has 3 entries → keep `METER_DEATH_INTERPRETATION=entry_per_death` (backend default).
   * If it lists **one entry per player** with a count in `totalAmount`, set `METER_DEATH_INTERPRETATION=total_amount` in the backend environment and run `python -m app.cli rebuild`.
5. Wipe on a boss deliberately: expect an `encounter_failed` entry and an *inferred* `party_wipe` on the run page.

| Result | Action |
|---|---|
| Unit-state deaths correct | Keep `deaths_unit_state` on. |
| Missed deaths of distant party members | Coverage stays `partial`; prefer meter deaths (already the higher priority source). |
| `UNIT_DIED` payload readable in dungeons (`/ft enable deaths_unit_died`, `/reload`, test again) | Optionally enable by default; it adds a third corroborating source. |

## 8. Interrupts and damage totals can be captured

1. Interrupt 5 casts with one character, count them by hand.
2. After the run, expect `interrupts.value = 5` for that character in the record, and on the run page.
3. Compare damage done for every member with Blizzard's meter.

Action: as test 6.

## 9. SavedVariables persist correctly

1. `/ft probe persist` → "marker … written".
2. `/reload`, then `/ft probe persist` → expect **PASS … survived 1 load (last load: reload)**.
3. Exit the game completely, start it, log in, `/ft probe persist` → expect **PASS … (last load: login)**.
4. Check `/ft status`: `load #` increases each session and the installation ID never changes.

| Result | Action |
|---|---|
| PASS for both | Mark persistence as validated. |
| Fails after a full restart (the beta 69893 bug) | **Data from each session survives only until the next one writes the file.** Tell users to run the desktop uploader (it archives every version) or to use `/ft export` before logging out. Put a warning on the download page. File a bug with Blizzard. |

## 10. One addon user can contribute data about all party members

1. Party of 5 where **only A** has the addon. Complete a dungeon.
2. Upload A's file. Expect 5 characters searchable on the website, each with this run in their history, each with metrics and the correct role.
3. Repeat the same dungeon with A **and** B running the addon. Upload both files.
4. Expect **one** run whose page says "Reconciled from 2 observers", with metrics marked ✓ (corroborated) where both agree, deaths "seen by 2", and no duplicate run in anyone's history.

| Result | Action |
|---|---|
| As expected | The core product promise is validated. |
| Two runs instead of one | Check the run pages' `party_guid` and timestamps. If party GUIDs differ between members' clients, set the matcher to ignore party GUID vetoes (`matcher.evaluate_candidate`) and re-run `python -m app.cli rebuild`. |

---

## Results record

| # | Test | Build | Result (pass / fail / partial) | Notes and values recorded | Flag or setting changed |
|---|---|---|---|---|---|
| 1 | Identity export | | | | |
| 2 | Roster changes | | | | |
| 3 | Inspection | | | | |
| 4 | Session boundaries | | | | |
| 5 | Meter access | | | | |
| 6 | Meter serialisation | | | | |
| 7 | Deaths | | | | |
| 8 | Interrupts and damage | | | | |
| 9 | Persistence | | | | |
| 10 | Whole-party coverage | | | | |

## Where the switches are

| Switch | Location | Changes |
|---|---|---|
| Collector defaults | `addon/ForeverTracker/Core/Config.lua` → `Config.COLLECTORS` | What a new installation records. |
| Per-user collector toggle | `/ft enable <name>`, `/ft disable <name>` | Overrides the default for one installation. |
| Meter retry timing | `Config.LIMITS.meter_retry_delays` | How long the addon waits for secrets to clear. |
| Meter death semantics | Backend env `METER_DEATH_INTERPRETATION` (`entry_per_death` / `total_amount`), then `python -m app.cli rebuild` | How meter death counts are read. Stored raw data is reinterpreted, nothing is re-uploaded. |
| Matching strictness | Backend env `MATCH_MIN_SHARED_CHARACTERS` | How many overlapping characters two records need to merge. |
| Dungeon catalog | `dungeons.final_encounter_id`, `catalog_status = 'curated'` | Enables *probable* completion from final-boss kills. |

After changing an addon default, bump `## Version` in `ForeverTracker.toc` and `FT.version`, and release the addon.
After changing a backend interpretation setting, run `python -m app.cli rebuild`: aggregates are recalculated from raw observations.
