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
  state.meter = { baseline = {}, status = {}, values = {}, deaths = {}, durations = {}, captured_at = {}, encounter = {}, attempts = 0 }
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
  local last = state.last_encounter_end
  if last and session.duration and math.abs(session.duration - last.duration) <= 10 and FT.Util.now() - last.at <= 120 then
    m.encounter[session.id] = last.id
  end
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
  for _, s in ipairs(current) do
    present[s.id] = true
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
        encounter_id = m.encounter[id],
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
