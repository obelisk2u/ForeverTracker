# Raid compatibility (assessed 2026-11-23)

**Status: raids are not recorded.** `Instance.isDungeon` accepts only `instance_type == "party"`, so a raid starts no
run. Forever's first raids open on December 9 (Blizzard's raid overview: Barrow Deeps, 10 players, 8 bosses; Hyjal
Summit, 20 players, 13 bosses on several paths; Onyxia's Lair, 40 players; weekly reset "currently planned"; no raid
finder). The Forever client as of build 1.60.1.71037 (2026-11-20, wago.tools branch `wowf`) has **no Barrow Deeps or
Hyjal Summit map and none of their bosses**; Onyxia's Lair is map 249 with encounter 1084, carried over from Classic.
Raid IDs can only be checked once the build that adds them ships.

This page lists what the dungeon pipeline does with raids today, the shared assumptions fixed so far, and what
recording raids still needs. Measurements marked *harness* come from the real addon code in the Lua test VM against
the mocked client (`addon/tests`), not from the live client.

## What happens in a raid today

| Step | Behaviour | Code |
|---|---|---|
| Entering a raid | No run starts. An open dungeon run is suspended as if the player left the dungeon (Barrow Deeps is reached from behind Blackmaw Hold's last boss, and The Shaper's Terrace has a raid portal). | `Collectors/Instance.lua`, `Sessions/RunTracker.lua` `onEnteringWorld` |
| Raid group members | Recorded as characters (`character_snapshot`, source `group`) through `raid1`…`raid40`. This is live now, since raid groups already form in the open world. | `Collectors/Group.lua`, `Collectors/Roster.lua` `units` |
| A dungeon run while the group is a raid | Every group member is in the run's roster, also those outside the dungeon. With more than 5 at once the backend quarantines the whole run (`too_many_concurrent_members`); *harness*: a Blackmaw Hold run whose group converts to a raid and invites 5 people outside has a 10-member roster and is quarantined. | `Roster.scan`, `backend/app/integrity/sanity.py` |

## Fixed

| Problem | Evidence | Change |
|---|---|---|
| In a raid group the player is also one of `raid1`…`raidN`: they were recorded as a group member of their own, and could be queued to inspect themselves. | `addon/tests/test_group.lua` "raid groups" (failed before the change) | `Group.scan` skips the player's own identity; `Inspect.queueGroup` skips the player's GUID. |
| A recorded instance's type was always written as `party`, so a raid would carry a dungeon's 5-player limits. | `addon/tests/test_runs.lua` "raids" | `Instance.toObservation` keeps `raid`. |
| Upload batches were cut every 200 records whatever their size. *Harness*, one raid night as uploaded JSON: 10 players, 8 bosses, 16 wipes ≈ 107 KB; 20 players, 10 bosses, about 5 hours ≈ 229 KB; 40 players with 6 to 12 wipes ≈ 137 to 227 KB. 35 records of 229 KB in one 200-record batch exceed the server's 8 MB limit, and the uploader treats the 413 answer as permanent, so that batch would never upload. | `packages/savedvariables/tests/test_export.py` | Batches also stay under 4 MB (`MAX_BATCH_BYTES`). Files whose batches already fit are cut exactly as before, so their batch IDs and upload state do not change. |
| One uploader's reset (or wipe) and quick re-pull of a boss within 120 seconds became one attempt with a conflicting result, so a final-boss kill no longer counted. Shared with dungeons; more likely in raids. | `backend/tests/test_dungeon_completion.py` | Separate pulls from one uploader stay separate (`consolidate.py`); different uploaders' records still cluster within 120 s. |

## Still needed before raids are recorded

| Issue | Affected code | What resolves it |
|---|---|---|
| **No single completion.** Raids have no completion event (no raid finder), partial clears and optional or out-of-order bosses are normal, and Hyjal Summit's final boss is disputed (warcraft.wiki.gg: Nythus the Dreambound; Method: The Wild King). Today every raid night would end `left` ("Left early"), and listing a "final" boss would end the run 20 seconds after it and drop later kills. | `consolidate._outcome`, `RunTracker.afterBossKill` / `finished_here`, `final_encounters.json` | A progress outcome for raids (bosses killed out of the raid's known encounters) instead of completed/left. Data: each raid's map ID and encounter IDs from the build that adds them (`DungeonEncounter`), then one full clear per raid showing the kill order. |
| **Lockouts across nights.** Each visit is its own run (15-minute grace), and nothing links the nights of one weekly lockout or tells two raid groups' copies apart beyond roster overlap. | `RunTracker` (grace), `reconciliation/cluster.py` | `GetSavedInstanceInfo`, `RequestRaidInfo`, `GetSavedInstanceEncounterInfo` and `C_RaidLocks` exist in the build-69893 API capture. On two members' clients: `/run RequestRaidInfo()`, then after `UPDATE_INSTANCE_INFO` `/dump GetSavedInstanceInfo(1)`, before and after the first kill and again on a second night. It must show whether the lockout ID is readable (not secret), the same on both clients, and stable across nights. |
| **Raid group during a dungeon run** (see above). | `Roster.scan`, `sanity.py` | A verified way to tell who is inside the instance. In a 5-player dungeon, with the group a raid and one member outside: `/dump GetRaidRosterInfo(n)` (7th value, zone), `/dump C_Map.GetBestMapForUnit("raidN")` and `/dump UnitInRange("raidN")` for a member inside and one outside, in and out of combat. Also whether a raid group can enter a dungeon at all. |
| **Party GUID when a party becomes a raid.** If `GROUP_JOINED` reports a new GUID, going back in after a corpse run counts as a new group and the run splits; uploaders with different GUIDs are not matched (`MATCH_PARTY_GUID_VETO`). | `RT.onGroupJoined`, `RT.onEnteringWorld` (`sameGroup`), `cluster.py` | The `GROUP_JOINED` payload on two clients before and after Convert to Raid, and after a member is swapped in. |
| **More than 40 people in one night** (a 40-player raid with substitutions). Members past the 40th are not added to the roster, so their meter numbers stay unattributed. | `Config.LIMITS.max_roster` (40); schema `roster` and meter `totals` (40 each) | Raise both to 80, with the upload contract (`schema/`, OpenAPI, TS types) regenerated. |
| **Deaths and long nights.** *Harness*: a 40-player night with 12 wipes fills the addon's 480 deaths (deaths then `partial`); a 9-hour night is quarantined (`implausible_run_duration`, 6 h). | `Config.LIMITS.max_deaths` (480), schema `deaths` (500), `sanity.py` `MAX_RUN_SECONDS`, `MAX_DEATH_EVENTS_PER_UNIT`, `MAX_COUNT_PER_RUN["deaths"]` (60) | Scale the limits by `max_players` for raids. |
| **Statistics.** Character statistics and the dungeon list do not look at `instance_type`, so raid nights would mix into deaths per run, death-free share, DPS and HPS medians and completions. | `backend/app/analytics/character_stats.py`, `services/site.py` | Decide which statistics raids get, and keep them separate from dungeon ones. |
| **Multi-NPC bosses** (Ravus and Darlissa, Council of Thorns, Time-Lost Battalion). A repeated `ENCOUNTER_START` for a boss already killed splits the run as a dungeon reset. | `Encounters.start` / `finish`, `RunTracker.splitOnRepeat` | Traces showing one `ENCOUNTER_START` / `ENCOUNTER_END` pair per attempt for each. |
| **Damage meter and load in raids.** 20 to 40 meter sources per session, secrecy after raid boss fights, polling 40 units for deaths each second, inspecting 39 people. | `Collectors/DamageMeter.lua`, `Collectors/Deaths.lua`, `Collectors/Inspect.lua` | `/ft probe` after a raid boss fight (`meter.read` pass); frame time with `/ft debug on` in a full raid. |
