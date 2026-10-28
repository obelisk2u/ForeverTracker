-- A mock of the World of Warcraft: Forever addon environment, for offline tests.
--
-- It models the parts of the client ForeverTracker uses, including the hazards documented in
-- docs/RESEARCH_FOREVER_API.md: RegisterEvent throws for unknown events, values can be secret
-- (sentinels that error on arithmetic/indexing), the damage meter is secret during combat,
-- and SavedVariables are only written on logout / reload.
--
-- This mock encodes our best understanding of the API. Passing tests prove the addon handles
-- these behaviours; they do NOT prove the real client behaves this way.

Mock = Mock or {}
local M = Mock

local SecretMT = {}
local function secretError()
  error("attempt to use a secret value", 2)
end
SecretMT.__index = secretError
SecretMT.__newindex = secretError
SecretMT.__add, SecretMT.__sub, SecretMT.__mul, SecretMT.__div = secretError, secretError, secretError, secretError
SecretMT.__lt, SecretMT.__le, SecretMT.__unm, SecretMT.__len, SecretMT.__call = secretError, secretError, secretError, secretError, secretError
SecretMT.__tostring = function()
  return "<secret>"
end

function M.secret(v)
  return setmetatable({}, SecretMT)
end

local SecretTableMT = { __index = secretError, __len = secretError }
function M.secretTable()
  return setmetatable({}, SecretTableMT)
end

M.DEFAULT_EVENTS = {
  "ADDON_LOADED", "PLAYER_LOGIN", "PLAYER_ENTERING_WORLD", "PLAYER_LEAVING_WORLD", "PLAYER_LOGOUT",
  "ADDONS_UNLOADING", "GROUP_ROSTER_UPDATE", "GROUP_JOINED", "GROUP_LEFT", "GROUP_FORMED", "PLAYER_DEAD",
  "PLAYER_ALIVE", "PLAYER_UNGHOST", "ENCOUNTER_START", "ENCOUNTER_END", "BOSS_KILL", "LFG_COMPLETION_REWARD",
  "SCENARIO_COMPLETED", "CHALLENGE_MODE_COMPLETED", "CHALLENGE_MODE_START", "INSTANCE_ABANDON_VOTE_FINISHED",
  "PLAYER_REGEN_ENABLED", "PLAYER_REGEN_DISABLED", "PLAYER_IN_COMBAT_CHANGED", "UNIT_FLAGS", "UNIT_HEALTH",
  "UNIT_DIED", "PARTY_KILL", "UNIT_CONNECTION", "INSPECT_READY", "DAMAGE_METER_COMBAT_SESSION_UPDATED",
  "DAMAGE_METER_CURRENT_SESSION_UPDATED", "DAMAGE_METER_RESET", "ADDON_RESTRICTION_STATE_CHANGED",
  "ZONE_CHANGED_NEW_AREA", "COMBAT_LOG_EVENT_UNFILTERED",
}

M.METER_TYPES = {
  DamageDone = 0, Dps = 1, HealingDone = 2, Hps = 3, Absorbs = 4, Interrupts = 5, Dispels = 6,
  DamageTaken = 7, AvoidableDamageTaken = 8, Deaths = 9, EnemyDamageTaken = 10,
}
local TYPE_TO_METRIC = {
  [0] = "damage_done", [2] = "healing_done", [4] = "absorbs", [5] = "interrupts", [6] = "dispels",
  [7] = "damage_taken", [8] = "avoidable_damage_taken", [9] = "deaths",
}

function M.reset()
  M.clock = 1792000000
  M.gameTime = 1000.0
  M.localOffset = 0
  M.timers = {}
  M.timerSeq = 0
  M.frames = {}
  M.validEvents = {}
  for _, e in ipairs(M.DEFAULT_EVENTS) do
    M.validEvents[e] = true
  end
  M.chat = {}
  M.units = {}
  M.group = { inRaid = false }
  M.instance = { inInstance = false, type = "none" }
  M.combat = false
  M.meter = { available = true, reason = "", sessions = {}, secretUntil = 0, missing = false }
  M.regionalNames = true
  M.region, M.regionName, M.realm = 1, "", "70"
  M.rules = {}
  M.build = { "1.60.1", "70532", "Oct 22 2026", 16001 }
  M.saved = nil
  M.itemLevels = {}
  M.inspectFrameShown = false
  M.inspectRequests = nil
  ForeverTrackerDB = nil
  SlashCmdList = {}
  M.installGlobals()
end

-- Clock -------------------------------------------------------------------------------------

function M.advance(seconds)
  local target = M.gameTime + seconds
  while true do
    local nextTimer, idx
    for i, t in ipairs(M.timers) do
      if not t.cancelled and t.at <= target and (nextTimer == nil or t.at < nextTimer.at or (t.at == nextTimer.at and t.seq < nextTimer.seq)) then
        nextTimer, idx = t, i
      end
    end
    if not nextTimer then
      break
    end
    local delta = nextTimer.at - M.gameTime
    M.gameTime = nextTimer.at
    M.clock = M.clock + delta
    if nextTimer.interval then
      nextTimer.at = nextTimer.at + nextTimer.interval
    else
      table.remove(M.timers, idx)
    end
    nextTimer.fn(nextTimer.handle)
  end
  M.clock = M.clock + (target - M.gameTime)
  M.gameTime = target
end

local function addTimer(seconds, fn, interval)
  M.timerSeq = M.timerSeq + 1
  local t = { at = M.gameTime + seconds, fn = fn, interval = interval, seq = M.timerSeq }
  t.handle = { Cancel = function() t.cancelled = true end, IsCancelled = function() return t.cancelled end }
  table.insert(M.timers, t)
  return t.handle
end

-- Events ------------------------------------------------------------------------------------

function M.fire(event, ...)
  for _, f in ipairs(M.frames) do
    if f._events[event] and f._scripts.OnEvent then
      f._scripts.OnEvent(f, event, ...)
    end
  end
end

-- Frames ------------------------------------------------------------------------------------

local function stub()
  local obj = { _text = "", _scripts = {}, _shown = false }
  return setmetatable(obj, {
    __index = function(t, k)
      if k == "SetText" then
        return function(self, s) self._text = s end
      elseif k == "GetText" then
        return function(self) return self._text end
      elseif k == "SetScript" then
        return function(self, name, fn) self._scripts[name] = fn end
      elseif k == "GetScript" then
        return function(self, name) return self._scripts[name] end
      elseif k == "Show" then
        return function(self) self._shown = true end
      elseif k == "Hide" then
        return function(self) self._shown = false end
      elseif k == "IsShown" then
        return function(self) return self._shown end
      elseif k == "CreateFontString" or k == "CreateTexture" then
        return function() return stub() end
      end
      return function() end
    end,
  })
end

local function makeFrame(kind, name, parent, template)
  local f = stub()
  f._events = {}
  f.RegisterEvent = function(self, event)
    if not M.validEvents[event] then
      error("Attempt to register unknown event \"" .. tostring(event) .. "\"", 2)
    end
    self._events[event] = true
  end
  f.UnregisterEvent = function(self, event) self._events[event] = nil end
  table.insert(M.frames, f)
  if name then
    _G[name] = f
  end
  return f
end

-- Units -------------------------------------------------------------------------------------

local function unit(token)
  local u = M.units[token]
  if u and u.exists ~= false then
    return u
  end
  return nil
end

local function maybeSecret(u, field, value)
  if u.secret and u.secret[field] then
    return M.secret(value)
  end
  return value
end

function M.setParty(members)
  M.units = {}
  for i, spec in ipairs(members) do
    local token = (i == 1) and "player" or ("party" .. (i - 1))
    spec.token = token
    if spec.dead == nil then
      spec.dead = false
    end
    if spec.connected == nil then
      spec.connected = true
    end
    M.units[token] = spec
  end
  M.group.num = #members > 1 and #members or 0
  M.fire("GROUP_ROSTER_UPDATE")
end

function M.unitByName(name)
  for token, u in pairs(M.units) do
    if u.name == name then
      return u, token
    end
  end
end

function M.removeMember(name)
  local members = {}
  for i = 0, 4 do
    local token = i == 0 and "player" or ("party" .. i)
    local u = M.units[token]
    if u and u.name ~= name then
      members[#members + 1] = u
    end
  end
  M.setParty(members)
end

function M.setDead(name, dead)
  local u = M.unitByName(name)
  u.dead = dead
  M.fire("UNIT_FLAGS", u.token)
  if u.token == "player" and dead then
    M.fire("PLAYER_DEAD")
  end
end

-- Instances ---------------------------------------------------------------------------------

function M.enterDungeon(spec)
  M.instance = {
    inInstance = true,
    type = spec.type or "party",
    name = spec.name or "Hall of Thanes",
    difficultyId = spec.difficultyId or 1,
    difficultyName = spec.difficultyName or "Normal",
    maxPlayers = spec.maxPlayers or 5,
    mapId = spec.mapId or 990001,
    lfgDungeonId = spec.lfgDungeonId or 0,
  }
  M.fire("PLAYER_ENTERING_WORLD", false, false)
end

function M.leaveInstance()
  M.instance = { inInstance = false, type = "none" }
  M.fire("PLAYER_ENTERING_WORLD", false, false)
end

-- Combat and the damage meter ---------------------------------------------------------------

function M.startCombat()
  M.combat = true
  M.fire("PLAYER_REGEN_DISABLED")
end

-- values: { [name] = { damage_done = n, healing_done = n, interrupts = n, deaths = n, ... } }
-- deathEntries: list of names (one entry per death in the Deaths type)
function M.endCombat(duration, values, opts)
  opts = opts or {}
  M.combat = false
  local id = #M.meter.sessions + 1 + (M.meter.idOffset or 0)
  M.meter.sessions[#M.meter.sessions + 1] = { id = id, duration = duration, values = values or {}, opts = opts }
  M.meter.secretUntil = M.gameTime + (opts.secretFor or 0)
  M.fire("PLAYER_REGEN_ENABLED")
  M.fire("DAMAGE_METER_COMBAT_SESSION_UPDATED", 0, id)
  return id
end

local function buildSession(s, typeId)
  local metric = TYPE_TO_METRIC[typeId]
  local secret = M.combat or M.gameTime < M.meter.secretUntil
  local sources = {}
  local total = 0
  for name, vals in pairs(s.values) do
    local u = M.unitByName(name)
    local guid = u and u.guid or ("Pet-0-" .. name)
    local amount = metric and vals[metric]
    if metric == "deaths" then
      for _ = 1, (vals.deaths or 0) do
        sources[#sources + 1] = {
          sourceGUID = secret and M.secret(guid) or guid,
          name = secret and M.secret(name) or name,
          classFilename = u and u.class or "",
          totalAmount = secret and M.secret(1) or 1,
          amountPerSecond = 0,
          deathRecapID = 7000 + #sources,
          deathTimeSeconds = secret and M.secret(10) or 10,
          isLocalPlayer = u and u.token == "player" or false,
        }
      end
    elseif amount and amount > 0 then
      total = total + amount
      sources[#sources + 1] = {
        sourceGUID = secret and M.secret(guid) or guid,
        name = secret and M.secret(name) or name,
        classFilename = u and u.class or "",
        totalAmount = secret and M.secret(amount) or amount,
        amountPerSecond = secret and M.secret(amount / s.duration) or amount / s.duration,
        deathRecapID = 0,
        deathTimeSeconds = 0,
        isLocalPlayer = u and u.token == "player" or false,
      }
    end
  end
  return { combatSources = sources, totalAmount = secret and M.secret(total) or total, maxAmount = 0, durationSeconds = s.duration }
end

-- Globals -----------------------------------------------------------------------------------

function M.installGlobals()
  local G = _G
  G.CreateFrame = makeFrame
  G.UIParent = stub()
  G.DEFAULT_CHAT_FRAME = { AddMessage = function(_, msg) table.insert(M.chat, msg) end }
  G.UNKNOWNOBJECT = "Unknown"
  G.WOW_PROJECT_ID, G.WOW_PROJECT_MAINLINE = 1, 1
  G.C_Timer = {
    After = function(s, fn) addTimer(s, fn) end,
    NewTimer = function(s, fn) return addTimer(s, fn) end,
    NewTicker = function(s, fn) return addTimer(s, fn, s) end,
  }
  G.GetTime = function() return M.gameTime end
  G.GetServerTime = function() return math.floor(M.clock) end
  G.time = function() return math.floor(M.clock) + M.localOffset end
  G.GetBuildInfo = function() return M.build[1], M.build[2], M.build[3], M.build[4] end
  G.GetLocale = function() return "enUS" end
  G.issecretvalue = function(v) return getmetatable(v) == SecretMT end
  G.issecrettable = function(t) return getmetatable(t) == SecretTableMT end
  G.C_EventUtils = { IsEventValid = function(e) return M.validEvents[e] == true end }
  G.RegionalUniqueNamesEnabled = function() return M.regionalNames end
  G.GetCurrentRegion = function() return M.region end
  G.GetCurrentRegionName = function() return M.regionName end
  G.GetRealmName = function() return M.realm end
  G.Enum = {
    DamageMeterType = M.METER_TYPES,
    DamageMeterSessionType = { Overall = 0, Current = 1, Expired = 2 },
    GameRule = { HardcoreRuleset = 101, RPRuleset = 102, PvPRuleset = 103 },
    AddOnRestrictionType = { Combat = 0, Encounter = 1, ChallengeMode = 2, PvPMatch = 3, Map = 4, Chat = 5 },
  }
  G.C_GameRules = { IsGameRuleActive = function(rule) return M.rules[rule] == true end }
  G.C_RestrictedActions = { GetAddOnRestrictionState = function() return 0 end }
  G.C_CombatLog = { IsCombatLogRestricted = function() return true end }

  G.UnitExists = function(t) return unit(t) ~= nil end
  G.UnitGUID = function(t) local u = unit(t) return u and maybeSecret(u, "guid", u.guid) end
  local function name(t)
    local u = unit(t)
    if not u then return nil end
    return maybeSecret(u, "name", u.name), u.surname and maybeSecret(u, "name", u.surname) or nil
  end
  G.UnitName = name
  G.UnitNameUnmodified = name
  G.UnitClass = function(t) local u = unit(t) if u then return u.class, u.class, u.classId or 1 end end
  G.UnitRace = function(t) local u = unit(t) if u then return u.race, u.race, u.raceId or 1 end end
  G.UnitLevel = function(t) local u = unit(t) return u and u.level or 0 end
  G.UnitGroupRolesAssigned = function(t) local u = unit(t) return u and (u.role or "NONE") or "NONE" end
  G.UnitIsDeadOrGhost = function(t) local u = unit(t) return u and (u.dead or u.ghost) and true or false end
  G.UnitIsFeignDeath = function(t) local u = unit(t) return u and u.feign or false end
  G.UnitIsConnected = function(t) local u = unit(t) return u and u.connected ~= false end
  G.UnitAffectingCombat = function() return M.combat end
  G.InCombatLockdown = function() return M.combat end
  G.IsInGroup = function() return (M.group.num or 0) > 1 end
  G.IsInRaid = function() return M.group.inRaid end
  G.GetNumGroupMembers = function() return M.group.num or 0 end
  G.IsInInstance = function() return M.instance.inInstance, M.instance.type end
  G.GetInstanceInfo = function()
    local i = M.instance
    if not i.inInstance then
      return "Azeroth", "none", 0, "", 0, 0, false, 0, 0, 0
    end
    return i.name, i.type, i.difficultyId, i.difficultyName, i.maxPlayers, 0, false, i.mapId, 5, i.lfgDungeonId
  end

  G.C_DamageMeter = {
    IsDamageMeterAvailable = function() return M.meter.available, M.meter.reason end,
    GetAvailableCombatSessions = function()
      local out = {}
      for _, s in ipairs(M.meter.sessions) do
        if not s.expired then
          out[#out + 1] = { sessionID = s.id, name = "Combat " .. s.id, durationSeconds = s.duration }
        end
      end
      return out
    end,
    GetCombatSessionFromID = function(id, typeId)
      for _, s in ipairs(M.meter.sessions) do
        if s.id == id and not s.expired then
          return buildSession(s, typeId)
        end
      end
      return { combatSources = {}, totalAmount = 0, maxAmount = 0 }
    end,
    GetSessionDurationSeconds = function() return 0 end,
    ResetAllCombatSessions = function()
      error("ForeverTracker must never reset the player's damage meter")
    end,
  }

  G.CanInspect = function(t) local u = unit(t) return u ~= nil and u.inspectable ~= false end
  G.NotifyInspect = function(t)
    local u = unit(t)
    M.inspectRequests = (M.inspectRequests or 0) + 1
    if u and u.inspectable ~= false then
      addTimer(0.3, function() M.fire("INSPECT_READY", u.guid) end)
    end
  end
  G.ClearInspectPlayer = function() end
  G.InspectFrame = { IsShown = function() return M.inspectFrameShown end }
  G.GetInventoryItemLink = function(t, slot)
    local u = unit(t)
    local item = u and u.gear and u.gear[slot]
    if not item then return nil end
    return string.format("|cff0070dd|Hitem:%d:%d:%d:0:0:0:0:0:20|h[%s]|h|r", item.id, item.enchant or 0, item.gem or 0, item.name or "Item")
  end
  G.GetInventoryItemQuality = function(t, slot)
    local u = unit(t)
    local item = u and u.gear and u.gear[slot]
    return item and (item.quality or 3) or nil
  end
  G.GetAverageItemLevel = function() local u = unit("player") return u and u.ilvl or 0, u and u.ilvl or 0 end
  G.C_PaperDollInfo = { GetInspectItemLevel = function(t) local u = unit(t) return u and u.ilvl or 0 end }
  G.C_Item = {
    GetDetailedItemLevelInfo = function(link)
      local id = tonumber(string.match(link, "item:(%d+)"))
      return M.itemLevels[id]
    end,
  }
  G.C_Traits = {
    GenerateInspectImportString = function(t) local u = unit(t) return u and u.talents end,
    GenerateImportString = function() local u = unit("player") return u and u.talents end,
  }
  G.C_ClassTalents = { GetActiveConfigID = function() return 1 end }
  G.C_SpecializationInfo = { GetInspectSpecialization = function(t) local u = unit(t) return u and u.specId or 0 end }
end

-- Simulate a client without these functions or namespaces.
function M.withoutApis(paths)
  for _, path in ipairs(paths) do
    M.removeApi(path)
  end
end

function M.removeApi(path)
  local parent, key = _G, nil
  for part in string.gmatch(path, "[^%.]+") do
    if key then
      parent = parent[key]
    end
    key = part
  end
  if parent then
    parent[key] = nil
  end
end

-- Addon lifecycle ---------------------------------------------------------------------------

M.ROOT = M.ROOT or "addon/ForeverTracker/"

function M.addonFiles()
  local files = {}
  local f = assert(io.open(M.ROOT .. "ForeverTracker.toc", "r"))
  for line in f:lines() do
    line = string.gsub(line, "\r", "")
    if line ~= "" and not string.find(line, "^##") then
      files[#files + 1] = string.gsub(line, "\\", "/")
    end
  end
  f:close()
  return files
end

function M.loadAddon(savedVariables)
  M.frames = {}
  M.timers = {}
  ForeverTrackerDB = savedVariables
  local ns = {}
  for _, file in ipairs(M.addonFiles()) do
    local chunk = assert(loadfile(M.ROOT .. file))
    chunk("ForeverTracker", ns)
  end
  M.ft = ns
  M.fire("ADDON_LOADED", "ForeverTracker", false)
  return ns
end

local function deepcopy(v)
  if type(v) ~= "table" then
    return v
  end
  local out = {}
  for k, x in pairs(v) do
    out[deepcopy(k)] = deepcopy(x)
  end
  return out
end
M.deepcopy = deepcopy

-- Log in: load the addon with whatever the "file" currently holds.
function M.login()
  local ft = M.loadAddon(deepcopy(M.saved))
  M.fire("PLAYER_ENTERING_WORLD", true, false)
  return ft
end

-- What the client does on logout / exit / reload: fire events, then write the file.
function M.saveVariables()
  M.fire("PLAYER_LOGOUT")
  M.saved = deepcopy(ForeverTrackerDB)
  return M.saved
end

function M.reload()
  M.saveVariables()
  local ft = M.loadAddon(deepcopy(M.saved))
  M.fire("PLAYER_ENTERING_WORLD", false, true)
  return ft
end

function M.logout(gapSeconds)
  M.saveVariables()
  M.frames, M.timers = {}, {}
  M.clock = M.clock + (gapSeconds or 0)
  M.gameTime = M.gameTime + (gapSeconds or 0)
end

-- The client died without writing the file: only the last saved copy survives.
function M.crash(gapSeconds)
  M.frames, M.timers = {}, {}
  M.clock = M.clock + (gapSeconds or 0)
  M.gameTime = M.gameTime + (gapSeconds or 0)
end

function M.slash(msg)
  SlashCmdList.FOREVERTRACKER(msg)
end

function M.chatContains(fragment)
  for _, line in ipairs(M.chat) do
    if string.find(line, fragment, 1, true) then
      return true
    end
  end
  return false
end
