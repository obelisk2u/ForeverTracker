-- Party death detection.
--
-- Primary source: alive -> dead transitions of UnitIsDeadOrGhost() for every group unit,
-- polled once per second and on UNIT_FLAGS/UNIT_HEALTH. Feign Death is not a death. A unit
-- first seen dead is NOT counted (we did not see it die). Dead flags survive /reload in
-- active_state, so one death is never counted twice.
-- Secondary: PLAYER_DEAD for the observer; UNIT_DIED (restricted, off by default).
-- The same death reported by two sources within DEDUPE_SECONDS is recorded once.
local _, FT = ...

local Deaths = {}
FT.Deaths = Deaths
local Safe = FT.Safe

Deaths.DEDUPE_SECONDS = 3

local function record(run, state, ref, now, source)
  for i = #run.deaths, 1, -1 do
    local d = run.deaths[i]
    if now - d.at > Deaths.DEDUPE_SECONDS then
      break
    end
    if d.unit_ref == ref then
      return false
    end
  end
  if #run.deaths >= FT.Config.LIMITS.max_deaths then
    state.deaths_truncated = true
    return false
  end
  run.deaths[#run.deaths + 1] = {
    unit_ref = ref,
    at = now,
    source = source,
    encounter_id = state.current_encounter,
  }
  return true
end
Deaths.record = record

function Deaths.poll(run, state, now)
  if not FT.Config.enabled("deaths_unit_state") then
    return
  end
  state.dead = state.dead or {}
  for ref, unit in pairs(state.units or {}) do
    local okDead, dead = Safe.call("UnitIsDeadOrGhost", unit)
    local isDead = okDead and Safe.bool(dead)
    if isDead == nil then
      state.death_tracking_partial = true
    else
      if isDead then
        local okFeign, feign = Safe.call("UnitIsFeignDeath", unit)
        if okFeign and Safe.bool(feign) == true then
          isDead = false
        end
      end
      local before = state.dead[ref]
      if isDead and before == false then
        record(run, state, ref, now, "unit_state")
      end
      state.dead[ref] = isDead
    end
  end
end

function Deaths.playerDead(run, state, now)
  local ref = FT.Roster.observerRef(run)
  if ref then
    record(run, state, ref, now, "player_dead")
    state.dead = state.dead or {}
    state.dead[ref] = true
  end
end

function Deaths.unitDied(run, state, now, guid)
  if not FT.Config.enabled("deaths_unit_died") then
    return
  end
  local g = Safe.str(guid, 96)
  if g == nil then
    state.unit_died_secret = true
    return
  end
  local ref = FT.Roster.refForGuid(state, g)
  if ref then
    record(run, state, ref, now, "unit_died_event")
  end
end

function Deaths.status(state)
  if not FT.Config.enabled("deaths_unit_state") then
    return "disabled"
  end
  if not Safe.api("UnitIsDeadOrGhost") then
    return "unavailable"
  end
  if state.death_tracking_partial or state.deaths_truncated or state.resumed_without_state then
    return "partial"
  end
  return "active"
end
