-- /ft probe: report which capabilities this client actually offers, without crashing when
-- one is missing. Results are printed and stored as a probe_report observation, so launch-day
-- testers can upload them (docs/FOREVER_LAUNCH_VALIDATION.md).
local _, FT = ...

local Probe = {}
FT.Probe = Probe
local Safe = FT.Safe

Probe.REQUIRED_APIS = {
  "UnitGUID", "UnitName", "UnitNameUnmodified", "UnitClass", "UnitRace", "UnitLevel", "UnitExists",
  "UnitGroupRolesAssigned", "UnitIsDeadOrGhost", "UnitIsConnected", "GetNumGroupMembers", "IsInGroup", "IsInRaid",
  "IsInInstance", "GetInstanceInfo", "GetServerTime", "GetBuildInfo", "C_EventUtils.IsEventValid", "issecretvalue",
}
Probe.OPTIONAL_APIS = {
  "RegionalUniqueNamesEnabled", "GetCurrentRegion", "GetCurrentRegionName", "GetRealmName", "UnitIsFeignDeath",
  "NotifyInspect", "CanInspect", "ClearInspectPlayer", "GetInventoryItemLink", "GetInventoryItemQuality",
  "GetAverageItemLevel", "C_PaperDollInfo.GetInspectItemLevel", "C_Item.GetDetailedItemLevelInfo",
  "C_Traits.GenerateInspectImportString", "C_Traits.GenerateImportString", "C_ClassTalents.GetActiveConfigID",
  "C_SpecializationInfo.GetInspectSpecialization", "C_DamageMeter.IsDamageMeterAvailable",
  "C_DamageMeter.GetAvailableCombatSessions", "C_DamageMeter.GetCombatSessionFromID",
  "C_DamageMeter.GetSessionDurationSeconds", "C_RestrictedActions.GetAddOnRestrictionState",
  "C_CombatLog.IsCombatLogRestricted", "C_GameRules.IsGameRuleActive", "C_EncodingUtil.SerializeJSON",
  "issecrettable", "CombatLogGetCurrentEventInfo",
}
Probe.EVENTS = {
  "PLAYER_ENTERING_WORLD", "PLAYER_LOGOUT", "GROUP_ROSTER_UPDATE", "GROUP_JOINED", "GROUP_LEFT", "PLAYER_DEAD",
  "ENCOUNTER_START", "ENCOUNTER_END", "BOSS_KILL", "LFG_COMPLETION_REWARD", "SCENARIO_COMPLETED",
  "CHALLENGE_MODE_COMPLETED", "INSTANCE_ABANDON_VOTE_FINISHED", "PLAYER_REGEN_ENABLED", "UNIT_FLAGS", "UNIT_HEALTH",
  "UNIT_DIED", "PARTY_KILL", "INSPECT_READY", "DAMAGE_METER_COMBAT_SESSION_UPDATED",
  "DAMAGE_METER_CURRENT_SESSION_UPDATED", "DAMAGE_METER_RESET", "ADDON_RESTRICTION_STATE_CHANGED",
  "COMBAT_LOG_EVENT_UNFILTERED",
}

local function add(results, check, status, detail)
  if detail then
    detail = string.gsub(tostring(detail), "[%c]", " ")
    if #detail > 290 then
      detail = string.sub(detail, 1, 290)
    end
  end
  results[#results + 1] = { check = check, status = status, detail = detail }
end

local function guarded(results, check, fn)
  local ok, err = pcall(fn)
  if not ok then
    add(results, check, "fail", "probe error: " .. tostring(err))
  end
end

local function describeMember(m)
  if not m then
    return "no unit"
  end
  return string.format(
    "status=%s name=%s surname=%s guid=%s class=%s level=%s role=%s",
    tostring(m.identity_status), m.name and "yes" or "no", m.surname and "yes" or "no",
    m.guid and "yes" or "no", tostring(m.class_file), tostring(m.level), tostring(m.role)
  )
end

function Probe.run()
  local r = {}
  guarded(r, "client.build", function()
    local version, build, _, interface = GetBuildInfo()
    add(r, "client.build", FT.Util.isForeverClient() and "pass" or "warn",
      string.format("version=%s build=%s interface=%s project=%s", tostring(version), tostring(build), tostring(interface), tostring(WOW_PROJECT_ID)))
  end)
  guarded(r, "names.regional", function()
    local on = FT.Identity.regionalNames()
    add(r, "names.regional", on and "pass" or "warn", on and "RegionalUniqueNamesEnabled() = true: second name value is a surname" or "RegionalUniqueNamesEnabled() is not true")
  end)
  for _, name in ipairs(Probe.REQUIRED_APIS) do
    add(r, "api." .. name, Safe.api(name) and "pass" or "fail", nil)
  end
  for _, name in ipairs(Probe.OPTIONAL_APIS) do
    add(r, "api." .. name, Safe.api(name) and "pass" or "info", Safe.api(name) and nil or "absent")
  end
  for _, event in ipairs(Probe.EVENTS) do
    local valid = FT.Events.isValid(event)
    add(r, "event." .. event, valid and "pass" or "info", valid and nil or "not valid on this client")
  end
  guarded(r, "identity.player", function()
    local m = FT.Identity.player()
    local ok = m and m.identity_status == "ok" and m.guid ~= nil
    add(r, "identity.player", ok and "pass" or "fail", describeMember(m))
  end)
  guarded(r, "identity.party", function()
    local okGroup, inGroup = Safe.call("IsInGroup")
    if not (okGroup and Safe.bool(inGroup)) then
      add(r, "identity.party", "skip", "not in a group")
      return
    end
    local counts = { ok = 0, secret = 0, unavailable = 0, noguid = 0 }
    for _, unit in ipairs(FT.Roster.units()) do
      if unit ~= "player" then
        local m = FT.Identity.read(unit)
        if m then
          counts[m.identity_status] = (counts[m.identity_status] or 0) + 1
          if not m.guid then
            counts.noguid = counts.noguid + 1
          end
        end
      end
    end
    local status = (counts.secret == 0 and counts.unavailable == 0 and counts.noguid == 0) and "pass" or "warn"
    add(r, "identity.party", status, string.format("ok=%d secret=%d unavailable=%d without_guid=%d", counts.ok, counts.secret, counts.unavailable, counts.noguid))
  end)
  guarded(r, "namespace", function()
    local ns = FT.Identity.namespace()
    add(r, "namespace", "info", string.format("region_id=%s region_name=%s ruleset=%s realm_label=%s",
      tostring(ns.region_id), tostring(ns.region_name), ns.ruleset, tostring(FT.Identity.realmLabel())))
  end)
  guarded(r, "instance", function()
    local i = FT.Instance.current()
    add(r, "instance", "info", string.format("in_instance=%s type=%s map_id=%s difficulty=%s name=%s",
      tostring(i.in_instance), tostring(i.instance_type), tostring(i.map_id), tostring(i.difficulty_id), tostring(i.name)))
  end)
  guarded(r, "meter.available", function()
    local available, reason = FT.Meter.available()
    add(r, "meter.available", available and "pass" or "fail", available and nil or reason)
    if not available then
      return
    end
    local sessions = FT.Meter.sessions()
    add(r, "meter.sessions", "info", "available sessions: " .. #sessions)
    local last = sessions[#sessions]
    if not last then
      add(r, "meter.read", "skip", "no combat session to read yet; fight something, wait 10 s out of combat, probe again")
      return
    end
    local typeId = Enum and Enum.DamageMeterType and Enum.DamageMeterType.DamageDone
    local ok, s = Safe.call("C_DamageMeter.GetCombatSessionFromID", last.id, typeId)
    local data, why = Safe.table(ok and s or nil)
    local inCombat = FT.Meter.inCombat()
    if not data then
      add(r, "meter.read", inCombat and "warn" or "fail", "session " .. last.id .. " unreadable (" .. tostring(why) .. "), in_combat=" .. tostring(inCombat))
      return
    end
    local sources = Safe.table(data.combatSources) or {}
    local readable, secret = 0, 0
    for _, src in ipairs(sources) do
      src = Safe.table(src)
      local total, reason = Safe.num(src and src.totalAmount)
      local guid, greason = Safe.str(src and src.sourceGUID)
      if total and (guid or greason ~= "secret") then
        readable = readable + 1
      elseif reason == "secret" or greason == "secret" then
        secret = secret + 1
      end
    end
    add(r, "meter.read", secret == 0 and readable > 0 and "pass" or "warn",
      string.format("session %d: sources=%d readable=%d secret=%d in_combat=%s", last.id, #sources, readable, secret, tostring(inCombat)))
  end)
  guarded(r, "restrictions", function()
    local get = Safe.api("C_RestrictedActions.GetAddOnRestrictionState")
    local types = Enum and Enum.AddOnRestrictionType
    if not get or not types then
      add(r, "restrictions", "info", "restriction API absent")
      return
    end
    local parts = {}
    for name, value in pairs(types) do
      local ok, st = pcall(get, value)
      parts[#parts + 1] = name .. "=" .. tostring(ok and Safe.num(st) or "?")
    end
    table.sort(parts)
    add(r, "restrictions", "info", table.concat(parts, " "))
  end)
  guarded(r, "combatlog", function()
    local ok, restricted = Safe.call("C_CombatLog.IsCombatLogRestricted")
    add(r, "combatlog", "info", "IsCombatLogRestricted=" .. tostring(ok and Safe.bool(restricted)) ..
      " CombatLogGetCurrentEventInfo=" .. (Safe.api("CombatLogGetCurrentEventInfo") and "present" or "absent"))
  end)
  add(r, "savedvariables.loaded", FT.loadedExistingData and "pass" or "warn",
    FT.loadedExistingData and ("existing data loaded; load_count=" .. tostring(FT.db.load_count))
      or "no earlier ForeverTracker data was loaded (first run, or the client did not load SavedVariables)")
  guarded(r, "savedvariables.persist", function()
    local marker = FT.db.diagnostics.persist_marker
    if not marker then
      add(r, "savedvariables.persist", "skip", "run /ft probe persist to start the persistence test")
    else
      local loads = (FT.db.load_count or 0) - (marker.load_count or 0)
      add(r, "savedvariables.persist", loads > 0 and "pass" or "info",
        string.format("marker %s survived %d load(s); last load was %s", marker.token, loads, FT.lastLoadKind or "?"))
    end
  end)
  local collectors = {}
  for name in pairs(FT.Config.COLLECTORS) do
    collectors[#collectors + 1] = name .. "=" .. (FT.Config.enabled(name) and "on" or "off")
  end
  table.sort(collectors)
  add(r, "collectors", "info", table.concat(collectors, " "))
  local errs = {}
  for owner, n in pairs(FT.capabilities.errors) do
    errs[#errs + 1] = owner .. "=" .. n
  end
  add(r, "errors", #errs == 0 and "pass" or "warn", #errs == 0 and "no collector errors" or table.concat(errs, " ") .. " last: " .. tostring(FT.lastError and FT.lastError.message))
  return r
end

function Probe.store(results)
  local player = FT.Identity.player() or {}
  local observation = {
    type = "probe_report",
    observation_id = FT.Storage.nextId("p"),
    revision = 1,
    recorded_by = { guid = player.guid, name = player.name, surname = player.surname, identity_status = player.identity_status or "unavailable" },
    namespace = FT.Identity.namespace(),
    realm_label = FT.Identity.realmLabel(),
    client_build = FT.db.client and FT.db.client.build or nil,
    observed_at = FT.Util.now(),
    results = results,
  }
  FT.Storage.push(observation)
  FT.db.diagnostics.last_probe_at = observation.observed_at
  return observation
end

function Probe.persist(reset)
  local diag = FT.db.diagnostics
  if reset then
    diag.persist_marker = nil
    FT.Util.print("persistence marker cleared.")
    return
  end
  if diag.persist_marker then
    local loads = (FT.db.load_count or 0) - (diag.persist_marker.load_count or 0)
    if loads > 0 then
      FT.Util.print(string.format("PASS: marker %s survived %d load(s) (last load: %s).", diag.persist_marker.token, loads, FT.lastLoadKind or "?"))
    else
      FT.Util.print("marker written this session. Now /reload, or exit the game completely and log back in, then run /ft probe persist again.")
    end
    return
  end
  diag.persist_marker = { token = FT.Util.randomHex(8), written_at = FT.Util.now(), load_count = FT.db.load_count }
  FT.Util.print("marker " .. diag.persist_marker.token .. " written. Now /reload or restart the game, then run /ft probe persist again.")
end

function Probe.print(results)
  local counts = {}
  for _, res in ipairs(results) do
    counts[res.status] = (counts[res.status] or 0) + 1
    if res.status ~= "pass" and res.status ~= "info" or string.find(res.check, "^identity") or string.find(res.check, "^meter") or res.check == "namespace" then
      FT.Util.print(string.format("[%s] %s %s", res.status, res.check, res.detail or ""))
    end
  end
  FT.Util.print(string.format("probe: %d pass, %d warn, %d fail, %d info, %d skip. Saved as an uploadable probe report.",
    counts.pass or 0, counts.warn or 0, counts.fail or 0, counts.info or 0, counts.skip or 0))
end
