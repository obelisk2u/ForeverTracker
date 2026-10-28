# World of Warcraft: Forever — Addon API Research

Status: **pre-launch research**, compiled 2026-10-26 while the Forever beta is offline.
Nothing in this document was executed against a running Forever client by the ForeverTracker team.
Every capability is classified by the strength of its evidence (section 2), and every
"requires live validation" item has a matching test in
[`FOREVER_LAUNCH_VALIDATION.md`](FOREVER_LAUNCH_VALIDATION.md).

---

## 1. Sources and how much weight each carries

| # | Source | What it is | Weight |
|---|---|---|---|
| S1 | Local client install, `C:\Program Files (x86)\World of Warcraft\_classic_beta_\` | The actual Forever beta client on the developer machine: `.build.info`, `Logs/`, `WTF/`, installed addons. Inspected read-only. Client files were not modified and no CASC archives were extracted. | Highest for *facts about this client* (version, file layout, SavedVariables layout). |
| S2 | [Ketho/wow-ui-source-forever](https://github.com/Ketho/wow-ui-source-forever) (branch `forever`, tag `1.60.1 (70009)`) | Mirror of the Forever client's own interface code, including `Blizzard_APIDocumentationGenerated` (Blizzard's machine-generated API documentation) and `Blizzard_DamageMeter`. | High for *existence, signatures, secrecy annotations*. Does not prove runtime behaviour. |
| S3 | [Thunderz96/forever-addon-kit](https://github.com/Thunderz96/forever-addon-kit) `data/forever_api.json` and README | Captured API surface from the live beta client (build 69893): 6,045 global functions, 269 namespaces. Plus in-client measurements. | High for *existence at build 69893*; medium for behavioural claims (single author, early build). |
| S4 | Questie / QuestieDB (installed copy in S1, with `QuestieDB_Forever.toc`) | Third-party addon with Forever-specific code paths and comments. | Medium. Comments describe observed behaviour but are not tests. |
| S5 | Pokézeroth (installed copy in S1, `## Interface: 16001`) | Small third-party addon that runs on Forever; its SavedVariables exist in S1. | Medium. Its *saved data* is client evidence; its comments are claims. |
| S6 | [warcraft.wiki.gg](https://warcraft.wiki.gg/) — [Secret Values](https://warcraft.wiki.gg/wiki/Secret_Values), [C_DamageMeter.GetCombatSessionFromType](https://warcraft.wiki.gg/wiki/API_C_DamageMeter.GetCombatSessionFromType) | Community documentation, written mostly against Retail 12.x (Midnight). | Medium. Retail behaviour, not necessarily Forever behaviour. |
| S7 | [AllTheThings issue #2630](https://github.com/ATTWoWAddon/AllTheThings/issues/2630) | Bug report documenting Forever surname behaviour of `UnitName`/`UnitFullName`. | Medium-high (reproduced and fixed upstream). |
| S8 | Blizzard news: [Forever beta now live](https://news.blizzard.com/en-us/article/24304160/the-world-of-warcraft-forever-beta-now-live), [Create a Name of Your Own](https://news.blizzard.com/en-us/article/24304161/create-a-name-of-your-own-in-wow-forever) | Official product information. | Authoritative for product facts (names, realm model). Says nothing about the addon API. |
| S9 | Press: [Wowhead](https://www.wowhead.com/forever/news/world-of-warcraft-forever-beta-will-return-shortly-383532), [Icy Veins dungeon list](https://www.icy-veins.com/wow-forever/news/all-9-new-wow-forever-dungeons-previewed-how-to-access-level-ranges-locations-and-more/), [Wikipedia](https://en.wikipedia.org/wiki/World_of_Warcraft:_Forever) | Secondary reporting. | Low-medium. Used only for product context (dungeon names, dates). |

Version caveat: the local client (S1) is **1.60.1.70532**. The generated docs (S2) are from **70009** and the API capture (S3) from **69893**. Blizzard changed behaviour between those builds (S3 documents fixes in 70009). Anything not observed in S1 must be re-checked on the launch build.

---

## 2. Classification legend

| Class | Meaning |
|---|---|
| **V — Verified** | Observed in Forever client artifacts on this machine (S1), or present in both S2 and S3 *and* exercised by an addon whose saved output exists in S1. |
| **D — Documented** | Present in Blizzard's generated Forever API documentation (S2) and the API capture (S3). Signature known; runtime values in dungeons not observed. |
| **L — Requires live validation** | Behaviour that decides whether a collector works, and that no source has measured on Forever in the situations we care about (5-player dungeons, grouped, after combat). |
| **U — Unsupported** | Absent from the client, restricted for addons, or excluded by ForeverTracker policy. |

---

## 3. Client identity

| Topic | Finding | Class | Evidence |
|---|---|---|---|
| Product / folder | Beta: product `wow_classic_beta`, folder `_classic_beta_`, executable `WowB.exe`. Launch (name-reservation client, 2026-10-28): product `wowf`, folder `_forever_`, executable `Wow.exe`. Battle.net's `HKLM\SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft\InstallPath` pointed at `_forever_`. | V | S1 and the launch install: `.build.info`, `.flavor.info` |
| Game version / build | `1.60.1.70532` in the beta; `1.60.1.70658` in the name-reservation client. Both are 1.60.1, so interface 16001. | V | `.build.info` |
| Interface (TOC) number | `16001`. `GetBuildInfo()` returns `16001` as the 4th value. | V | S1: `QuestieDB_Forever.toc` and `Pokezeroth.toc` declare 16001, and Pokézeroth's SavedVariables were written by this client, so a base `.toc` declaring 16001 loads. S3 `client.interface = 16001`. |
| Engine lineage | Retail (Midnight) engine. `WOW_PROJECT_ID == WOW_PROJECT_MAINLINE` (project 1). 269 `C_*` namespaces. Classic globals (`GetItemInfo`, `GetSpellInfo`, `UnitAura`, `GetTalentInfo`, `CombatLogGetCurrentEventInfo`) are absent. | V | S3 `client.project = 1`, S4 comment "Forever shares Retail's project ID", S1 folder layout (`D3D12/`, `Speech/`, `icudt78l.dat`) matches `_retail_`, not `_classic_era_`. |
| Detecting Forever at runtime | Interface range `16000 ≤ v < 17000` (what Questie does). `WOW_PROJECT_ID` cannot distinguish it from Retail. The internal game type is **`camelot`** (Blizzard's own TOCs use `## AllowLoadGameType: standard, camelot`). | V / D | S4 `QuestieCompat.lua`, S2 `Blizzard_DamageMeter.toc` |
| Version-check trap | `select(4, GetBuildInfo()) >= 100000` (the usual "modern client" test) is false on Forever. | V | S3 |
| Unknown events | `frame:RegisterEvent("UNKNOWN")` **throws** and aborts the file. | D (measured by S3) | S3 README. ForeverTracker wraps every registration in `pcall` and checks `C_EventUtils.IsEventValid` first. |
| Lua error cap | After 100 Lua errors per session the client stops reporting errors. | D (measured by S3) | S3. Another reason to never let a collector error repeatedly. |
| `ReloadUI()` | Protected; addons cannot call it. | D (measured by S3) | S3. |

---

## 4. Character identity

### 4.1 Names and surnames — the central identity hazard

Forever gives every character **two names**: a first name and a secondary name ("surname"). Blizzard: *"Your full character name needs to be distinct within your region, rather than only within a single realm"* and the game is *"built around a larger, realmless structure"* (S8).

| API | Forever behaviour | Class | Evidence |
|---|---|---|---|
| `UnitName(unit)` / `UnitNameUnmodified(unit)` / `UnitFullName(unit)` | Returns `firstName, surname`. **The second return value is a surname, not a realm.** `name, realm = UnitName(unit)` stores the surname as the realm. | V (by S7, S4) | S7, and S4's AceDB: `local name, surname = UnitNameUnmodified("player")` |
| `GetUnitName(unit, showServer)` | Returns the complete `"First Surname"` string whatever `showServer` is. | D (S7) | S7 |
| Addon-message sender names | `"Firstname Lastname"` even after `Ambiguate`. | D (S4 comment) | S4 `CommsRouting.lua` |
| `RegionalUniqueNamesEnabled()` | Exists. Questie's AceDB uses it to key characters by `"First Surname"` under a ruleset key (`PvE`/`PvP`/`RP`/`Hardcore`) instead of a realm. | D | S2 `UnitDocumentation.lua`, S4 AceDB |
| `C_PlayerInfo.ShouldDisplaySurname()` | Exists (presentation setting). Hiding the surname affects the world display only; "it will still appear in chat" (S8). | D | S2, S8 |
| Local evidence of the name format | WTF character folders are named `<First>-<Surname>` inside a numbered realm folder (`70`). The folder hyphen joins first name and surname. **It is not `Name-Realm`.** AceDB's profile key in this client is `"<First> <Surname>"`. Two characters on one account can share a surname, so surnames are not unique. | V | S1 |
| `GetRealmName()` | Returns the client's realm string. Its value on Forever has not been observed (the WTF realm folder `70` suggests it may be a numeric/opaque label). **Not used as part of character identity.** | L | S7 states realm must be read independently of name parts. |
| Region | `GetCurrentRegion()` / `GetCurrentRegionName()` exist. AceDB notes `GetCurrentRegionName()` returns `""` on PTR/beta. | D / L | S2, S4 |
| Ruleset | `C_GameRules.IsGameRuleActive(Enum.GameRule.HardcoreRuleset / RPRuleset / PvPRuleset)` is what Questie uses to derive the namespace key. | D / L | S4 AceDB |

**ForeverTracker identity rules derived from this:**

1. Never read the second return of `UnitName`-family functions as a realm. The addon records `name` and `surname` separately and builds `fullName = name .. " " .. surname`.
2. The **character namespace** is `(game, region, ruleset)`, e.g. `forever:us:pve`. The realm string is stored as an observed attribute (`realmLabel`) and never used for identity or URLs.
3. `GetCurrentRegionName()` may be empty on beta. The addon records `GetCurrentRegion()` (number) and the name, and the backend maps both.
4. Shared surnames are normal ("Asha Brightvale", "Thalen Brightvale", S8). The surname is part of the full name, never a family or account identifier.

### 4.2 GUIDs

| Topic | Finding | Class | Evidence |
|---|---|---|---|
| Format | Player GUIDs look like `Player-<server id>-<8 hex digits>`, e.g. `Player-4620-0123ABCD` (seen in client log lines such as `Player-…: ignoring outdated/duplicate ClientNewWorld`). | V | S1 `Logs/Client.log`, `character-list-order.txt` |
| Party members' GUIDs | `UnitGUID` is annotated `SecretWhenUnitIdentityRestricted`. Per S6, identity results are secret *"when the unit isn't player-controlled or in the party/raid"*, so party members should be readable. | D → **L** | S2, S6 |
| Stability | Retail convention: a player GUID survives renames and changes on realm transfer. Not documented for Forever's realmless model. | L | — |
| Structure parsing | **ForeverTracker never parses GUID segments** (server ID, etc.). The whole GUID string is an opaque identifier scoped to a namespace. | Policy | Prompt requirement. Blizzard does not document GUID structure as a contract. |

### 4.3 Class, race, level, role

| API | Notes | Class |
|---|---|---|
| `UnitClass(unit)` → `className, classFilename, classID` | `className` is `ConditionalSecret`. **Use `classFilename`** (e.g. `MAGE`), which has no conditional annotation. | D |
| `UnitRace(unit)` → `localized, english, raceID` | `SecretWhenUnitIdentityRestricted`. Skyborne is a new race, so race IDs must not be hard-coded. | D |
| `UnitLevel(unit)` | Present. | D |
| `UnitGroupRolesAssigned(unit)` | `SecretWhenUnitIdentityRestricted`. Returns `TANK`/`HEALER`/`DAMAGER`/`NONE`. In manually formed groups roles are often `NONE`, so the backend treats role as *observed assignment*, not as the role actually played. | D / L |
| `RAID_CLASS_COLORS` | Questie: *"Some clients (e.g. WoW Forever) don't define RAID_CLASS_COLORS for every class."* Our addon never indexes it without a nil check. | D (S4) |
| Specializations | `GetSpecialization` is **absent**. Spec IDs are new (paladin 1486). `C_SpecializationInfo.GetSpecialization` / `GetInspectSpecialization` exist. | V (S3) / D |

---

## 5. Group roster

| API / Event | Notes | Class |
|---|---|---|
| `IsInGroup()`, `IsInRaid()`, `GetNumGroupMembers()`, `UnitExists("partyN")` | Present (S3). | D |
| `GROUP_ROSTER_UPDATE` | `UniqueEvent` (coalesced). Must be treated as "something changed, re-scan". | D |
| `GROUP_JOINED(category, partyGUID)`, `GROUP_LEFT(category, partyGUID)`, `GROUP_FORMED` | **Carries a party GUID.** If every member's client reports the same `partyGUID`, it is the strongest cross-observer run-matching key available. Whether the value is shared, stable across roster changes, and readable in dungeons is unknown. | D → **L** |
| `UnitIsConnected(unit)`, `UNIT_CONNECTION(unit, isConnected)` | Disconnect visibility for party members. | D |
| `C_RecentAllies` | Exists (Retail "recent allies" system). Not used: it reflects Blizzard's list, not our observation. | D |

---

## 6. Dungeon and instance detection

| API / Event | Notes | Class |
|---|---|---|
| `IsInInstance()` → `inInstance, instanceType` (`"party"` for 5-player dungeons) | Standard. | D |
| `GetInstanceInfo()` → `name, instanceType, difficultyID, difficultyName, maxPlayers, dynamicDifficulty, isDynamic, instanceID, instanceGroupSize, LfgDungeonID` | Questie calls it on Forever (`select(8, GetInstanceInfo())`) and maps instance IDs. `instanceID` is the **map ID** of the dungeon, **not** the ID of the specific instance copy. There is no documented per-copy identifier for 5-player dungeons. | D |
| Forever dungeon map IDs | Unknown. The nine new dungeons (Hall of Thanes, Ruins of Lordaeron, Excavation Site, City of Dalaran, The Drowned City, Krol'dok Stronghold, Alcaz Prison, Blackmaw Hold, Shaper's Terrace; S9) have no published map IDs. QuestieDB's Forever zone table is copied from Classic data and includes Northrend dungeons, so it is not a Forever dungeon list. **The backend learns the dungeon catalog from observations**, and synthetic data uses obviously synthetic IDs. | L |
| `PLAYER_ENTERING_WORLD(isInitialLogin, isReloadingUi)` | Fires on login, `/reload` and every loading screen. Distinguishes reload from zoning. | D |
| `PLAYER_LEAVING_WORLD`, `ZONE_CHANGED_NEW_AREA` | Present. | D |
| `ENCOUNTER_START(encounterID, encounterName, difficultyID, groupSize)` | Present. | D → L (fires for Forever 5-player bosses?) |
| `ENCOUNTER_END(encounterID, encounterName, difficultyID, groupSize, success, encounterUnitStatus)` | `success` is `1`/`0`. New `encounterUnitStatus` lists boss units with `remainingHealthPercent`. | D → L |
| `BOSS_KILL(encounterID, encounterName)` | Present. | D → L |
| `IsEncounterInProgress()` / `C_InstanceEncounter.IsEncounterInProgress()` | Present. | D |
| Completion signals | `LFG_COMPLETION_REWARD`, `SCENARIO_COMPLETED`, `CHALLENGE_MODE_COMPLETED` exist. Whether any of them fires for a normal Forever 5-player dungeon is unknown. `EncounterJournalDisabled=1` was a beta game rule (S3), so the Encounter Journal cannot list a dungeon's bosses at runtime. | **L** |
| Abandon | `INSTANCE_ABANDON_VOTE_FINISHED(votePassed)` and `C_PartyInfo.StartInstanceAbandonVote` exist (the Retail instance-abandon vote). | D → L |
| `C_ChallengeMode.GetDeathCount()` | Exists, but applies only to challenge-mode runs. | D |

**Consequence:** dungeon *completion* can only be marked **verified** when a completion event is observed. Leaving an instance never implies completion. "All known bosses killed" becomes *probable* only once the backend's dungeon catalog has a curated final-encounter ID for that dungeon.

---

## 7. Restrictions, secret values and the combat log

### 7.1 Restriction model (carried over from Midnight)

`Enum.AddOnRestrictionType` (S2): `Combat` (0), `Encounter` (1), `ChallengeMode` (2), `PvPMatch` (3), **`Map` (4) — "The player is on a map that applies addon restrictions"**, `Chat` (5).
`C_RestrictedActions.GetAddOnRestrictionState(type)` and `ADDON_RESTRICTION_STATE_CHANGED(type, state)` report it. Dungeons are expected to be restricted maps (S6: *SecretOnRestrictedMaps, 12.0.5*).

### 7.2 Secret values

From S6 and S3:

- Secret values can be stored in variables and **as table values**, but *"Tainted code is not allowed to store secret values as keys in tables"*.
- Tainted code cannot compare, do arithmetic on, or boolean-test secrets. *"Never `or`/compare a possibly-secret value; even a boolean test throws"* (S3). `type(secret)` returns the real type.
- Helper functions present on Forever (S3): `issecretvalue`, `issecrettable`, `canaccessvalue`, `canaccesssecrets`, `hasanysecretvalues`, `scrubsecretvalues`, `secretwrap`, `dropsecretaccess`. Plus `C_Secrets` with 27 predicates, including `ShouldUnitIdentityBeSecret`.
- **What happens if a secret is written to SavedVariables is undocumented.** ForeverTracker therefore never stores a value without first checking `issecretvalue(v) == false`. Secret values are recorded as the status `"secret"` with a `nil` value.

ForeverTracker's Lua rule: every value read from a restricted API goes through `FT.Safe.read(v)`, which returns `nil, "secret"` for secrets **before** any comparison, arithmetic, or `tostring`.

### 7.3 Combat log

| Topic | Finding | Class |
|---|---|---|
| `CombatLogGetCurrentEventInfo` | **Absent** from the Forever API capture. | U (V by S3) |
| `COMBAT_LOG_EVENT_UNFILTERED` | Documented with `HasRestrictions = true`. Third-party addons state Midnight-engine clients forbid addons from registering it. `C_CombatLog.IsCombatLogRestricted()` exists. | U |
| `UNIT_DIED(unitGUID)`, `PARTY_KILL(attackerGUID, targetGUID)` | Exist as standalone events, documented `Restricted = true`. Pokézeroth registers them on Forever (guarded by `C_EventUtils.IsEventValid`) and its saved kill counts grew, so the events fire in the open world. Payload readability in **dungeons** (restricted map) is unknown. | D → **L** |

**Consequence:** no combat-log-based damage, healing, interrupt or death accounting. The only party-wide combat statistics source is the native damage meter.

### 7.4 Health and death state

| API | Notes | Class |
|---|---|---|
| `UnitHealth` etc. | Secret in combat for player and target (S3 measurement). Not used. | D |
| `UnitIsDeadOrGhost(unit)`, `UnitIsDead`, `UnitIsGhost`, `UnitIsFeignDeath` | No secrecy annotation in S2. Candidate for **party-wide death detection by state transition** (alive → dead), polled and on `UNIT_FLAGS`/`UNIT_HEALTH`. | D → **L** |
| `PLAYER_DEAD`, `PLAYER_ALIVE`, `PLAYER_UNGHOST` | Local player only. | D |
| `C_DeathRecap` | Exists. Death recap IDs also appear on damage-meter death entries. | D |

---

## 8. Native damage meter (`C_DamageMeter`)

### 8.1 Surface (S2, identical in S3 and on warcraft.wiki.gg)

Functions:
`GetAvailableCombatSessions() → {sessionID, name, durationSeconds?}[]`,
`GetCombatSessionFromID(sessionID, type)`, `GetCombatSessionFromType(sessionType, type)` — both **`SecretWhenInCombat`**,
`GetCombatSessionSourceFromID/FromType(..., sourceGUID?, sourceCreatureID?)` (per-spell breakdown, `SecretWhenInCombat`),
`GetSessionDurationSeconds(sessionType)`, `IsDamageMeterAvailable() → isAvailable, failureReason`, `ResetAllCombatSessions()`.

Events: `DAMAGE_METER_COMBAT_SESSION_UPDATED(type, sessionID)`, `DAMAGE_METER_CURRENT_SESSION_UPDATED`, `DAMAGE_METER_RESET`.

`Enum.DamageMeterSessionType`: Overall 0, Current 1, Expired 2.
`Enum.DamageMeterType`: DamageDone 0, Dps 1, HealingDone 2, Hps 3, Absorbs 4, Interrupts 5, Dispels 6, DamageTaken 7, AvoidableDamageTaken 8, **Deaths 9**, EnemyDamageTaken 10.
`Enum.DamageMeterCombineSessionType`: None, **ChallengeMode**, Arena, ArenaMultiRound (the client can merge sessions for a challenge-mode run).

`DamageMeterCombatSession = { combatSources[], maxAmount, totalAmount, durationSeconds? }`
`DamageMeterCombatSource = { sourceGUID? (ConditionalSecret), sourceCreatureID?, name (ConditionalSecret), classFilename (NeverSecret), specIconID, totalAmount, amountPerSecond, isLocalPlayer (NeverSecret), deathRecapID (NeverSecret), deathTimeSeconds, classification, sourceDisplayType, factionGroup? }`

### 8.2 What is established vs. unknown

| Question | Status |
|---|---|
| The meter exists in Forever | **V.** `Blizzard_DamageMeter` loads for game type `camelot` (S2), and `Blizzard_DamageMeter.lua` SavedVariables exist for every character in S1. |
| Values are secret during combat | **D** (`SecretWhenInCombat`). |
| Values become readable after combat | **L.** Retail addon authors report that sessions persist briefly after `PLAYER_REGEN_ENABLED` and that secrets resolve within a few seconds (one changelog polls every 0.3 s for up to 9 s). Not measured on Forever, and not measured inside a restricted dungeon map. |
| `sourceGUID` / `name` of party members readable after combat | **L** (`ConditionalSecret`). |
| One session per combat? Per boss? | **L.** Blizzard's UI labels individual sessions "Combat #N" and shows Current/Overall separately. Whether 5-player dungeon trash pulls and boss pulls each create a session, and how many sessions are retained, is unknown. |
| `Overall` = one dungeon run | **No.** Overall accumulates since the last reset (the user's or Blizzard's), so ForeverTracker never treats it as run totals. |
| `Deaths` type semantics | **L.** Each source carries `deathRecapID` and `deathTimeSeconds`, suggesting one entry per death *or* per unit with a count in `totalAmount`. The addon records both raw shapes and the backend interprets them under a feature flag. |
| Values can be serialized to SavedVariables | **L.** Plain numbers and strings (after `issecretvalue` is false) should serialize like any other Lua value. Secrets are never written. |
| Party-wide from one client | **D → L.** `combatSources` lists every source the meter tracks (S2 structure). One addon user would then see all party members' totals, which is the basis of the "one installation observes the whole party" design. |
| `ResetAllCombatSessions()` | **D.** ForeverTracker never calls it automatically, because that would destroy the player's own meter history. Run scoping is done by session-ID bookkeeping (§9). |

---

## 9. Equipment and talents (inspection)

| API / Event | Notes | Class |
|---|---|---|
| `CanInspect(unit)`, `NotifyInspect(unit)`, `INSPECT_READY(inspecteeGUID)`, `ClearInspectPlayer()` | Present. `NotifyInspect` takes a unit token (S2). | D → L (range, throttle, secrecy in dungeons) |
| `GetInventoryItemLink(unit, slot)`, `GetInventoryItemID(unit, slot)` | Present. Works for `"player"` without inspection. | D |
| `C_PaperDollInfo.GetInspectItemLevel(unit)`, `GetAverageItemLevel()` | Present. | D |
| `C_Item.GetDetailedItemLevelInfo(link)`, `C_Item.GetItemInfoInstant` | Present (`GetItemInfo` global is absent; use `C_Item`). | D |
| Talents | Forever uses Retail's trait system (`C_Traits`, `C_ClassTalents`). `C_Traits.GenerateInspectImportString(unit)` and `C_Traits.HasValidInspectData()` exist. The "Legacy" trait tree unlocks at level 25 (S3). | D → L |
| Enchant IDs | Parsed from the item link's `item:` payload (the documented hyperlink format), not from GUIDs. | D |

Inspection is **opt-in at the collector level, rate-limited** (one request at a time, at least 2 s apart), never issued in combat, and only for group members.

---

## 10. SavedVariables

| Topic | Finding | Class |
|---|---|---|
| Write timing | Written on logout, exit and `/reload` (standard). "Exit Now" skips writing `config-cache.wtf` but a normal logout writes it (S3). | D |
| **Load bug (build 69893)** | S3 proved, with a pre-seeded file, that the client *"writes SavedVariables on exit and never reads them back"*. Independently confirmed by a second developer and a forum thread. | D for 69893 |
| **Loading on the local build** | Pokézeroth's per-character file grew from `totalKills = 93` (`.bak`, 2026-10-19 04:27) to `totalKills = 102` (2026-10-19 15:08), and the earlier `firstKill` timestamps were kept. The later session therefore loaded the earlier data, so **SavedVariables loaded on the build in use on 2026-10-19.** | V (inferred) for that build. **L** for launch. |
| Location | `WTF/Account/<ACCOUNT>/SavedVariables/<Addon>.lua` (account-wide) and `WTF/Account/<ACCOUNT>/<realm folder>/<First-Surname>/SavedVariables/<Addon>.lua` (per character). The realm folder on this machine is named `70`. | V |
| `.bak` files | The client keeps the previous version as `.bak`. | V |

**Design consequences:**

1. The addon uses one **account-wide** SavedVariable (`ForeverTrackerDB`), so the uploader has one file to watch.
2. The addon cannot tell "first install" from "the load failed" inside one session, so it never assumes earlier data exists. It records an `installationId` (created on first run) and a `loadCount`. Probe mode has a two-step persistence test (`/ft probe persist`, then restart the game, then `/ft probe persist` again). The uploader flags a file whose `installationId` changes between versions, which is the signature of the load bug.
3. The **uploader archives every distinct version** of the file it sees (content-hashed spool) before parsing. If the load bug returns, each session's data survives being overwritten by the next session.
4. The addon also offers a copy-paste **export string** (`/ft export`), so a user can submit data without the file.
5. Storage is bounded (ring buffer of runs and snapshots) so the file cannot grow without limit.

---

## 11. Other useful client facts

- `C_EncodingUtil.SerializeJSON(value, options)` exists (D). The addon can use it for export strings when present, and falls back to its own serializer otherwise.
- `GetServerTime()` exists (D). All ForeverTracker timestamps use **server epoch seconds**, so observers' records align. The local `time()` is recorded only to measure clock skew.
- `C_Timer.After/NewTicker/NewTimer` exist (D).
- `C_EventUtils.IsEventValid(event)` exists (D). Used before every `RegisterEvent`.
- `C_ChatInfo.SendAddonMessage` exists, but ForeverTracker does **not** use addon chat. It is restricted during encounters (`AddOnRestrictionType.Chat`), and observation must not depend on other players running the addon.

---

## 12. Capability matrix (summary)

| Capability | Class | ForeverTracker behaviour |
|---|---|---|
| Interface 16001 base TOC loads | V | `ForeverTracker.toc` declares `## Interface: 16001`. |
| Detect Forever client | V | Interface range check, plus a recorded `gameType` probe. |
| Read own name + surname + class + race + level + GUID | D | Collected. Secret-checked. |
| Read party members' identity | D → L | Collected when not secret. Secret → recorded as `identityStatus = "secret"`. |
| Region / ruleset namespace | D → L | Recorded raw. The backend maps it. Unknown → namespace `forever:unknown:unknown` (never merged with known namespaces). |
| Party GUID (`GROUP_JOINED`) | D → L | Recorded. Used as a strong *positive* match signal only when present on both sides. |
| Dungeon entry / exit, map ID, difficulty | D | Run state machine (see `ARCHITECTURE.md`, "Dungeon-run state machine"). |
| Boss encounters (`ENCOUNTER_START/END`) | D → L | Recorded with success flag. |
| Verified completion | L | Only on a completion event. Otherwise `unknown` or `left`. |
| Abandon vote | D → L | `abandoned` when `votePassed`. |
| Native meter per-session totals after combat | L | Adapter behind flag `collector.damageMeter`. Every value secret-checked; unreadable values are `status: "secret"`. |
| Native meter deaths | L | Recorded raw, interpreted server-side, flag `deathsFromMeter`. |
| Party death detection via unit state | D → L | Collector `deathsFromUnitState` (on by default, provenance `unit_state`). |
| `UNIT_DIED` GUID events | D → L | Collector off by default (`collector.unitDiedEvents`). |
| Combat log | U | Not used. |
| Inspection: gear | D → L | Collector `collector.inspect` (default on, throttled, out of combat). |
| Inspection: talents | D → L | Collector `collector.talents` (default off until validated). |
| SavedVariables persistence | V (local build) / L (launch) | Probe + uploader archive + export string. |
| HTTP from addon | U | Never. Upload happens outside the game. |
| Automation / protected actions | U | Never. |

---

## 13. Open questions for launch day

All of these are executable tests in [`FOREVER_LAUNCH_VALIDATION.md`](FOREVER_LAUNCH_VALIDATION.md):

1. Are party members' `UnitGUID` / `UnitName` / `UnitClass` readable inside a Forever 5-player dungeon, in and out of combat?
2. What do `GetRealmName()`, `GetCurrentRegion()`, `GetCurrentRegionName()` and the ruleset predicates return at launch?
3. Is `partyGUID` from `GROUP_JOINED` identical on every member's client, and does it survive roster changes?
4. How many damage-meter sessions does a dungeon run create, how long are they retained, and when do their values stop being secret after `PLAYER_REGEN_ENABLED`?
5. What is the shape of `Deaths` (type 9) sessions: one entry per death or one per unit?
6. Does `UnitIsDeadOrGhost("partyN")` change reliably for party members anywhere in the instance?
7. Do `ENCOUNTER_START/END` fire for Forever's 5-player bosses, and does any completion event fire at the end of a normal dungeon?
8. Does `NotifyInspect` → `INSPECT_READY` work for party members in dungeons, at what range, and with what throttle?
9. Do SavedVariables load and persist on the launch build?
10. Is a 5-member party fully observable from one client (identity + meter + deaths)?
