-- Native damage meter (C_DamageMeter) adapter.
--
-- Status: REQUIRES LIVE VALIDATION. The API exists on Forever (Blizzard's generated docs for
-- 1.60.1.70009) but whether values become readable after combat, inside a dungeon, has not
-- been measured. Everything here degrades to "secret"/"unavailable"; nothing is guessed.
--
-- Scoping, without touching the player's own meter (ResetAllCombatSessions is never called):
--   * sessions that already existed when the run started are excluded (baseline);
--   * sessions that appear while the observer is outside the instance are excluded;
--   * every other session is captured after combat, with retries while values are secret;
--   * Overall is never used as run totals.
--
-- Boss fights: the meter starts a session per combat, and a session belongs to the boss attempt
-- its time span overlaps most. Its end is when it was first seen after combat (sessions end with
-- the player's combat, so also when the player dies mid-fight); its start is that minus its
-- length. Each attempt in run.encounters gets the summed totals of its sessions as `meter`.
-- (Validated on build 70862: matching by session length alone missed fights the player died in
-- and pulls that ran straight from trash into the boss.)
local _, FT = ...

local Meter = {}
FT.Meter = Meter
local Safe = FT.Safe

Meter.TYPES = {
  { "damage_done", "DamageDone" },
  { "healing_done", "HealingDone" },
  { "absorbs", "Absorbs" },
  { "interrupts", "Interrupts" },
  { "dispels", "Dispels" },
  { "damage_taken", "DamageTaken" },
  { "avoidable_damage_taken", "AvoidableDamageTaken" },
  { "deaths", "Deaths" },
}

function Meter.available()
  if not FT.Config.enabled("meter") then
    return false, "disabled"
  end
  if not (Safe.api("C_DamageMeter.GetAvailableCombatSessions") and Safe.api("C_DamageMeter.GetCombatSessionFromID")) then
    return false, "api_missing"
  end
  local ok, available, reason = Safe.call("C_DamageMeter.IsDamageMeterAvailable")
  if ok and Safe.bool(available) == false then
    return false, Safe.str(reason, 100) or "not_available"
  end
  return true
end

function Meter.sessions()
  local out = {}
  local ok, list = Safe.call("C_DamageMeter.GetAvailableCombatSessions")
  list = ok and Safe.table(list) or nil
  if not list then
    return out, ok and "secret" or "error"
  end
  for _, s in ipairs(list) do
    s = Safe.table(s)
    local id = s and Safe.num(s.sessionID)
    if id then
      out[#out + 1] = { id = id, duration = s and Safe.num(s.durationSeconds) }
    end
  end
  return out
end

local function inCombat()
  local okLock, lock = Safe.call("InCombatLockdown")
  local okAff, aff = Safe.call("UnitAffectingCombat", "player")
  return (okLock and Safe.bool(lock) == true) or (okAff and Safe.bool(aff) == true)
end
Meter.inCombat = inCombat

function Meter.startRun(run, state)
  local available, reason = Meter.available()
  run.meter = {
    status = available and "observed" or (reason == "disabled" and "disabled" or "unavailable"),
    reason = (not available) and reason or nil,
    combat_seconds = 0,
    sessions = {},
    totals = {},
    death_entries = {},
  }
  state.meter = { baseline = {}, status = {}, values = {}, deaths = {}, durations = {}, captured_at = {}, ended_at = {}, attempts = 0 }
  if available then
    for _, s in ipairs(Meter.sessions()) do
      state.meter.baseline[s.id] = true
    end
  end
end

function Meter.suspend(run, state)
  if not state.meter then
    return
  end
  Meter.capturePass(run, state)
  local seen = {}
  for _, s in ipairs(Meter.sessions()) do
    seen[s.id] = true
  end
  state.meter.seen_before_suspend = seen
end

function Meter.resume(run, state)
  local m = state.meter
  if not m then
    return
  end
  local before = m.seen_before_suspend
  if before then
    for _, s in ipairs(Meter.sessions()) do
      if not before[s.id] and m.status[s.id] == nil then
        m.baseline[s.id] = true -- combat that happened outside the instance
      end
    end
    m.seen_before_suspend = nil
  end
end

function Meter.reset(run, state)
  if state.meter then
    state.meter.was_reset = true
    FT.RunTracker.mark("meter_reset", {})
  end
end

local function resolveRef(run, state, guid, name)
  if guid then
    local ref = FT.Roster.refForGuid(state, guid)
    if ref then
      return ref
    end
  end
  return FT.Roster.refForName(run, name)
end

-- Read one session for every meter type. Returns "captured", "secret" or "missed".
function Meter.captureSession(run, state, session)
  local get = Safe.api("C_DamageMeter.GetCombatSessionFromID")
  local enum = Enum and Enum.DamageMeterType or {}
  local values, deaths = {}, {}
  local anyData, anySecret, unmatched = false, false, 0
  for _, t in ipairs(Meter.TYPES) do
    local metric, enumName = t[1], t[2]
    local typeId = enum[enumName]
    if typeId ~= nil then
      local ok, result = pcall(get, session.id, typeId)
      local data, reason = nil, "error"
      if ok then
        data, reason = Safe.table(result)
      end
      if reason == "secret" then
        anySecret = true
      elseif data then
        anyData = true
        local sources = Safe.table(data.combatSources) or {}
        for _, src in ipairs(sources) do
          src = Safe.table(src)
          if src then
            local guid = Safe.str(src.sourceGUID, 96)
            local name, nameReason = Safe.str(src.name, 48)
            local total, totalReason = Safe.num(src.totalAmount)
            if totalReason == "secret" or nameReason == "secret" then
              anySecret = true
            else
              local ref = resolveRef(run, state, guid, name)
              if ref and total then
                values[ref] = values[ref] or {}
                values[ref][metric] = (values[ref][metric] or 0) + total
                if metric == "deaths" then
                  local recap = Safe.num(src.deathRecapID)
                  if recap and recap ~= 0 then
                    deaths[#deaths + 1] = {
                      unit_ref = ref,
                      guid = guid,
                      session_id = session.id,
                      death_time_sec = Safe.num(src.deathTimeSeconds),
                      death_recap_id = recap,
                      total = total,
                    }
                  end
                end
              elseif not ref then
                unmatched = unmatched + 1
              end
            end
          end
        end
      end
    end
  end
  local m = state.meter
  if anySecret then
    m.status[session.id] = "secret"
    return "secret"
  end
  if not anyData then
    m.status[session.id] = "missed"
    return "missed"
  end
  m.status[session.id] = "captured"
  m.values[session.id] = values
  m.deaths[session.id] = deaths
  m.durations[session.id] = session.duration
  m.captured_at[session.id] = FT.Util.now()
  m.unmatched = (m.unmatched or 0) + unmatched
  return "captured"
end

-- Capture every in-scope session not yet captured. Returns true if a retry is worthwhile.
function Meter.capturePass(run, state)
  local m = state.meter
  if not m or run.meter.status == "disabled" or run.meter.status == "unavailable" then
    return false
  end
  if inCombat() then
    return true
  end
  local retry = false
  local current = Meter.sessions()
  local present = {}
  m.ended_at = m.ended_at or {} -- runs resumed from an older version's save
  for _, s in ipairs(current) do
    present[s.id] = true
    if not m.baseline[s.id] and m.ended_at[s.id] == nil then
      m.ended_at[s.id] = FT.Util.now() -- first seen out of combat: when it ended
    end
    if not m.baseline[s.id] and m.status[s.id] ~= "captured" then
      local status = Meter.captureSession(run, state, s)
      if status == "secret" then
        retry = true
      end
    end
  end
  -- Sessions seen earlier but gone before capture are missed.
  for id, status in pairs(m.status) do
    if status ~= "captured" and not present[id] then
      m.status[id] = "missed"
    end
  end
  Meter.rebuild(run, state)
  return retry
end

function Meter.schedule(run, state)
  if not state.meter or state.meter.scheduled then
    return
  end
  state.meter.scheduled = true
  local delays = FT.Config.LIMITS.meter_retry_delays
  local attempt = 0
  local function step()
    attempt = attempt + 1
    local active = FT.Storage.activeRun()
    local st = FT.db.active_state
    if active ~= run or not st or not st.meter then
      return
    end
    local again = Meter.capturePass(run, st)
    if again and attempt < #delays then
      FT.Events.after(delays[attempt + 1], "meter", step)
    else
      st.meter.scheduled = nil
    end
  end
  FT.Events.after(delays[1], "meter", step)
end

-- Turn per-session captures into run totals with per-metric status.
-- The index in run.encounters of the boss attempt a captured session overlaps most, or nil.
-- Two seconds of slack at the start covers whole-second clocks and the capture delay.
function Meter.attemptFor(run, m, id)
  local ended, duration = m.ended_at and m.ended_at[id], m.durations[id]
  if not ended or not duration then
    return nil
  end
  local from, to = ended - duration - 2, ended + 1
  local best, bestOverlap = nil, 0
  for i, e in ipairs(run.encounters) do
    local overlap = math.min(to, e.ended_at or ended) - math.max(from, e.started_at)
    if overlap > bestOverlap then
      best, bestOverlap = i, overlap
    end
  end
  return best
end

-- Give each boss attempt the summed totals of its sessions. The status is "partial" when the
-- observer died during the attempt: their session ended there, so the rest of the fight is missing.
local function rebuildAttempts(run, m, ids)
  local enum = Enum and Enum.DamageMeterType or {}
  local attempts, sessionAttempt = {}, {}
  for _, id in ipairs(ids) do
    local i = m.status[id] == "captured" and Meter.attemptFor(run, m, id)
    if i then
      sessionAttempt[id] = i
      local a = attempts[i] or { sessions = 0, combat = 0, values = {} }
      attempts[i] = a
      a.sessions = a.sessions + 1
      a.combat = a.combat + (m.durations[id] or 0)
      for ref, v in pairs(m.values[id] or {}) do
        local sums = a.values[ref] or {}
        a.values[ref] = sums
        for metric, amount in pairs(v) do
          sums[metric] = (sums[metric] or 0) + amount
        end
      end
    end
  end
  local observer = FT.Roster.observerRef(run)
  for i, e in ipairs(run.encounters) do
    local a = attempts[i]
    if a then
      local died = false
      for _, d in ipairs(run.deaths) do
        if d.unit_ref == observer and d.at >= e.started_at and d.at <= (e.ended_at or d.at) then
          died = true
          break
        end
      end
      local totals = {}
      for _, entry in ipairs(run.roster) do
        local metrics = {}
        for _, t in ipairs(Meter.TYPES) do
          if enum[t[2]] ~= nil then
            metrics[t[1]] = (a.values[entry.ref] and a.values[entry.ref][t[1]]) or 0
          end
        end
        totals[#totals + 1] = { unit_ref = entry.ref, metrics = metrics }
      end
      e.meter = {
        status = died and "partial" or "observed",
        observer_died = died or nil,
        combat_seconds = a.combat,
        sessions = a.sessions,
        totals = totals,
      }
    else
      e.meter = nil
    end
  end
  return sessionAttempt
end

function Meter.rebuild(run, state)
  local m = state.meter
  local meter = run.meter
  local captured, seen, secret = 0, 0, 0
  local sessions = {}
  local ids = {}
  for id in pairs(m.status) do
    ids[#ids + 1] = id
  end
  table.sort(ids)
  local sessionAttempt = rebuildAttempts(run, m, ids)
  local combat = 0
  for _, id in ipairs(ids) do
    local status = m.status[id]
    seen = seen + 1
    if status == "captured" then
      captured = captured + 1
      combat = combat + (m.durations[id] or 0)
    elseif status == "secret" then
      secret = secret + 1
    end
    if #sessions < FT.Config.LIMITS.max_meter_sessions then
      sessions[#sessions + 1] = {
        session_id = id,
        duration_sec = m.durations[id],
        status = status,
        captured_at = m.captured_at[id],
        encounter_id = sessionAttempt[id] and run.encounters[sessionAttempt[id]].encounter_id or nil,
      }
    end
  end
  meter.sessions = sessions
  meter.combat_seconds = combat
  if seen == 0 then
    meter.status = "observed"
  elseif captured == seen and not m.was_reset then
    meter.status = "observed"
  elseif captured > 0 then
    meter.status = "partial"
  elseif secret > 0 then
    meter.status = "secret"
  else
    meter.status = "partial"
  end

  local enum = Enum and Enum.DamageMeterType or {}
  local totals = {}
  local deaths = {}
  for _, entry in ipairs(run.roster) do
    local metrics = {}
    for _, t in ipairs(Meter.TYPES) do
      local metric = t[1]
      if enum[t[2]] == nil then
        metrics[metric] = { status = "unavailable", sessions = 0 }
      elseif captured == 0 then
        metrics[metric] = { status = secret > 0 and "secret" or "unavailable", sessions = 0 }
      else
        local sum = 0
        for _, id in ipairs(ids) do
          local v = m.values[id] and m.values[id][entry.ref]
          if v and v[metric] then
            sum = sum + v[metric]
          end
        end
        metrics[metric] = { value = sum, status = (captured == seen) and "observed" or "partial", sessions = captured }
      end
    end
    totals[#totals + 1] = {
      unit_ref = entry.ref,
      guid = entry.guid,
      name = entry.name,
      class_file = entry.class_file,
      metrics = metrics,
    }
  end
  for _, id in ipairs(ids) do
    for _, d in ipairs(m.deaths[id] or {}) do
      if #deaths < FT.Config.LIMITS.max_deaths then
        deaths[#deaths + 1] = d
      end
    end
  end
  meter.totals = totals
  meter.death_entries = deaths
end
