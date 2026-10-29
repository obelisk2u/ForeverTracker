-- Collector feature flags and limits.
--
-- Collectors whose behaviour on Forever is unverified ship disabled until the launch-day
-- validation (docs/FOREVER_LAUNCH_VALIDATION.md) confirms them. Users can toggle them with
-- /ft enable <name> and /ft disable <name>.
local _, FT = ...

local Config = {}
FT.Config = Config

Config.COLLECTORS = {
  -- name = { default, description, verification }
  identity = { true, "Party names, surnames, GUIDs, class, race, level, role", "documented" },
  group = { true, "Name, surname, class and race of everyone you group with, outside dungeons too (no level)", "documented" },
  encounters = { true, "Boss encounter start/end (ENCOUNTER_START/END)", "documented" },
  deaths_unit_state = { true, "Party deaths from alive->dead state changes", "needs_validation" },
  deaths_unit_died = { false, "UNIT_DIED events (restricted; payload may be secret)", "needs_validation" },
  meter = { true, "Native damage meter session totals after combat", "needs_validation" },
  inspect = { true, "Equipment of party members via inspection (out of combat)", "needs_validation" },
  talents = { false, "Talent loadout strings of inspected players", "needs_validation" },
}

Config.LIMITS = {
  max_observations = 400, -- ring buffer of finished records
  max_timeline = 380,
  max_deaths = 480,
  max_meter_sessions = 380,
  max_roster = 40,
  resume_grace_seconds = 900, -- time to come back after leaving the instance (corpse runs!)
  inspect_interval_seconds = 2.5,
  inspect_refresh_seconds = 1800,
  inspect_timeout_seconds = 5,
  self_snapshot_interval_seconds = 1800,
  group_refresh_seconds = 7 * 24 * 3600, -- re-record an unchanged group member after a week
  death_poll_seconds = 1.0,
  meter_retry_delays = { 0.5, 1, 2, 4, 8 },
  max_collector_errors = 20,
}

function Config.defaults()
  local collectors = {}
  for name, def in pairs(Config.COLLECTORS) do
    collectors[name] = def[1]
  end
  return { collectors = collectors, debug = false }
end

function Config.enabled(name)
  local db = FT.db
  if FT.disabledThisSession and FT.disabledThisSession[name] then
    return false
  end
  if db and db.settings and db.settings.collectors and db.settings.collectors[name] ~= nil then
    return db.settings.collectors[name] == true
  end
  local def = Config.COLLECTORS[name]
  return def ~= nil and def[1] == true
end

function Config.set(name, value)
  if Config.COLLECTORS[name] == nil then
    return false
  end
  FT.db.settings.collectors[name] = value and true or false
  return true
end
