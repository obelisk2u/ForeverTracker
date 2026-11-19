-- Personal dungeon records, so the addon is useful on its own, without the companion app.
--
-- Every finished run is summarized once (RunTracker.finalize) into ForeverTrackerDB.records:
--   characters : character key -> name, surname, class
--   dungeons   : character key -> dungeon key -> totals and personal bests (never trimmed)
--   history    : the newest MAX_HISTORY run summaries, oldest first
-- `observations` is a bounded upload queue; these records are not, so personal bests survive
-- any number of runs. The first load of this version backfills them from stored runs.
local _, FT = ...

local Records = {}
FT.Records = Records

-- Version 2 counts a final-boss kill as a completion; older records are rebuilt from stored runs.
-- Version 3 adds The Hall of Thanes to the final bosses.
-- Version 4 leaves out of the group whoever only passed through.
-- Since then the records note which final bosses and wings they were made with (`finals`): an
-- update that adds one rebuilds them from stored runs (Records.init), with no new version.
-- Scarlet Monastery's wings share one map ID; each wing has its own records (FT.WINGS).
-- RULES changes when the way a summary is made changes, rebuilding them the same way.
Records.VERSION = 4
Records.MAX_HISTORY = 500
Records.MAX_PARTY = 8
-- Someone in the group for less than this, and at no boss pull, only passed through (left as the
-- run began and was replaced): not part of the run's group. The website uses the same rule.
Records.PASSED_THROUGH_SECONDS = 300
-- A run with less combat than this does not set a DPS/HPS record (one quick pull is not a run).
Records.MIN_RATE_COMBAT_SECONDS = 60
-- 2: a run marked as completed in 0.2.10 (flags.marked_completed) is judged like any other.
Records.RULES = 2

-- The final bosses and wings this version knows, as one string: "map:encounter,..." and
-- "wing:map:key:encounter,..." in sorted order.
local function finalsKey()
  local keys = {}
  for map, bosses in pairs(FT.FINAL_ENCOUNTERS or {}) do
    for id in pairs(bosses) do
      keys[#keys + 1] = map .. ":" .. id
    end
  end
  for map, wings in pairs(FT.WINGS or {}) do
    for _, wing in ipairs(wings) do
      for id in pairs(wing.bosses) do
        keys[#keys + 1] = "wing:" .. map .. ":" .. wing.key .. ":" .. id
      end
    end
  end
  table.sort(keys)
  keys[#keys + 1] = "rules:" .. Records.RULES
  return table.concat(keys, ",")
end

function Records.fresh()
  return { version = Records.VERSION, finals = finalsKey(), characters = {}, dungeons = {}, history = {} }
end

-- The same key Identity uses for a player, so the current character's records can be found.
function Records.charKey(who)
  return who and FT.Identity.key(who) or nil
end

function Records.currentCharKey()
  return Records.charKey(FT.Identity.player())
end

local function observer(run)
  for _, entry in ipairs(run.roster or {}) do
    if entry.is_observer then
      return entry
    end
  end
  return nil
end

-- The observer's value for one meter metric, when the meter actually read it.
local function myMetric(run, ref, metric)
  if not ref or not run.meter then
    return nil
  end
  for _, total in ipairs(run.meter.totals or {}) do
    if total.unit_ref == ref then
      local m = total.metrics and total.metrics[metric]
      if m and type(m.value) == "number" and (m.status == "observed" or m.status == "partial") then
        return m.value
      end
      return nil
    end
  end
  return nil
end

function Records.dungeonKey(s)
  local key = tostring(s.map_id or s.dungeon or "?") .. ":" .. tostring(s.difficulty_id or 0)
  return s.wing and (key .. ":" .. s.wing) or key
end

local function passedThrough(run, entry, started, ended)
  local spans, seconds = {}, 0
  for _, p in ipairs(entry.presence or {}) do
    local from, to = math.max(p.start or started, started), math.min(p["end"] or ended, ended)
    if to > from then
      spans[#spans + 1] = { from, to }
      seconds = seconds + (to - from)
    end
  end
  if #spans == 0 or seconds >= Records.PASSED_THROUGH_SECONDS or seconds >= (ended - started) / 2 then
    return false
  end
  for _, e in ipairs(run.encounters or {}) do
    for _, span in ipairs(spans) do
      if e.started_at and span[1] <= (e.ended_at or e.started_at) and e.started_at <= span[2] then
        return false
      end
    end
  end
  return true
end

-- One finished run -> a compact summary from the observer's point of view.
function Records.summarize(run)
  if type(run) ~= "table" or run.type ~= "dungeon_run" or not run.timing or not run.instance then
    return nil
  end
  local me = observer(run)
  local key = Records.charKey(run.recorded_by) or Records.charKey(me)
  if not key then
    return nil
  end
  local ref = me and me.ref
  local started = run.timing.started_at
  local ended = run.timing.ended_at or run.timing.last_updated_at or started
  local bosses, wipes, killed = 0, 0, {}
  local finals = FT.FINAL_ENCOUNTERS[run.instance.map_id] or {}
  local finalBoss = false
  for _, e in ipairs(run.encounters or {}) do
    if e.success == true and not killed[e.encounter_id] then
      killed[e.encounter_id] = true
      bosses = bosses + 1
      finalBoss = finalBoss or finals[e.encounter_id] == true
    elseif e.success == false then
      wipes = wipes + 1
    end
  end
  -- No completion event (a group formed outside the dungeon finder) but the final boss died.
  local result = run.state
  if result ~= "completed" and result ~= "abandoned" and finalBoss then
    result = "completed"
  end
  local deaths = 0
  for _, d in ipairs(run.deaths or {}) do
    if ref and d.unit_ref == ref then
      deaths = deaths + 1
    end
  end
  local party = {}
  for _, entry in ipairs(run.roster or {}) do
    if not entry.is_observer and entry.name and #party < Records.MAX_PARTY and not passedThrough(run, entry, started, ended) then
      party[#party + 1] = { name = entry.name, surname = entry.surname, class_file = entry.class_file, role = entry.role }
    end
  end
  local combat = run.meter and run.meter.combat_seconds
  local wing = FT.wingOf(run)
  return {
    id = run.observation_id,
    char = key,
    name = (me and me.name) or (run.recorded_by and run.recorded_by.name),
    surname = (me and me.surname) or (run.recorded_by and run.recorded_by.surname),
    class_file = me and me.class_file,
    map_id = run.instance.map_id,
    wing = wing and wing.key,
    dungeon = FT.dungeonName(run),
    difficulty = run.instance.difficulty_name,
    difficulty_id = run.instance.difficulty_id,
    started_at = started,
    ended_at = ended,
    duration = math.max(0, ended - started),
    result = result,
    final_boss = finalBoss,
    bosses = bosses,
    wipes = wipes,
    deaths = deaths,
    party_deaths = #(run.deaths or {}),
    damage = myMetric(run, ref, "damage_done"),
    healing = myMetric(run, ref, "healing_done"),
    interrupts = myMetric(run, ref, "interrupts"),
    combat_seconds = (type(combat) == "number" and combat > 0) and combat or nil,
    party = party,
  }
end

-- Per-second rate over the run's combat time, or nil when there was too little combat.
function Records.rate(s, amount)
  if amount and s.combat_seconds and s.combat_seconds >= Records.MIN_RATE_COMBAT_SECONDS then
    return amount / s.combat_seconds
  end
  return nil
end

-- Zero is no record: the meter reports 0 healing for a mage, not "none".
local function better(current, value, lower)
  if value == nil or value <= 0 then
    return false
  end
  if current == nil then
    return true
  end
  if lower then
    return value < current.value
  end
  return value > current.value
end

local function best(d, field, value, s, lower)
  if better(d[field], value, lower) then
    d[field] = { value = value, at = s.ended_at, id = s.id }
  end
end

-- Fold one summary into a dungeon's totals and bests.
function Records.fold(d, s)
  d.runs = (d.runs or 0) + 1
  d.bosses = (d.bosses or 0) + s.bosses
  d.deaths = (d.deaths or 0) + s.deaths
  d.time = (d.time or 0) + s.duration
  if s.result == "completed" then
    d.completed = (d.completed or 0) + 1
    best(d, "fastest", s.duration, s, true)
  end
  best(d, "damage", s.damage, s)
  best(d, "healing", s.healing, s)
  best(d, "dps", Records.rate(s, s.damage), s)
  best(d, "hps", Records.rate(s, s.healing), s)
  if s.ended_at > (d.last_at or 0) then
    d.last_at = s.ended_at
  end
end

function Records.add(s)
  local rec = FT.db.records
  local c = rec.characters[s.char] or {}
  c.name, c.surname = s.name or c.name, s.surname or c.surname
  c.class_file = s.class_file or c.class_file
  if s.ended_at > (c.last_at or 0) then
    c.last_at = s.ended_at
  end
  rec.characters[s.char] = c

  local byChar = rec.dungeons[s.char] or {}
  rec.dungeons[s.char] = byChar
  local dkey = Records.dungeonKey(s)
  local d = byChar[dkey] or { map_id = s.map_id, difficulty_id = s.difficulty_id }
  d.name = s.dungeon or d.name
  d.difficulty = s.difficulty or d.difficulty
  Records.fold(d, s)
  byChar[dkey] = d

  local history = rec.history
  history[#history + 1] = s
  while #history > Records.MAX_HISTORY do
    table.remove(history, 1)
  end
end

-- RunTracker.finalize: record a finished run.
function Records.addRun(run)
  local s = Records.summarize(run)
  if s then
    Records.add(s)
  end
  return s
end

-- Rebuild every summary after stored runs or the final bosses changed (RunTracker.splitStored,
-- Records.init). Runs that already left the upload queue survive only as summaries, so those are
-- kept as they are.
function Records.rebuild()
  local db = FT.db
  local old = type(db.records) == "table" and db.records.history or {}
  local stored = {}
  for _, o in ipairs(db.observations or {}) do
    if type(o) == "table" and o.type == "dungeon_run" and o.observation_id then
      stored[o.observation_id] = true
    end
  end
  db.records = Records.fresh()
  for _, s in ipairs(old) do
    if type(s) == "table" and not stored[s.id] then
      Records.add(s)
    end
  end
  for _, o in ipairs(db.observations or {}) do
    if type(o) == "table" and o.type == "dungeon_run" then
      Records.addRun(o)
    end
  end
  db.records.backfilled = true
  return db.records
end

function Records.init()
  local db = FT.db
  if type(db.records) ~= "table" or type(db.records.history) ~= "table" or db.records.version ~= Records.VERSION then
    db.records = Records.fresh()
  end
  local rec = db.records
  if not rec.backfilled then
    -- Runs recorded before this version: oldest first, as they were stored.
    for _, o in ipairs(db.observations or {}) do
      if o.type == "dungeon_run" then
        Records.addRun(o)
      end
    end
    rec.backfilled = true
  end
  if rec.finals ~= finalsKey() then
    -- An update added a final boss: a stored run that killed it now counts as completed.
    rec = Records.rebuild()
  end
  return rec
end

-- What the records window shows: charKey = a character's key, or nil for all characters.
function Records.view(charKey)
  local rec = FT.db.records
  local view = {
    totals = { runs = 0, completed = 0, bosses = 0, deaths = 0, time = 0 },
    bests = {},
    dungeons = {},
    history = {},
  }
  local merged = {}
  for key, byChar in pairs(rec.dungeons) do
    if charKey == nil or key == charKey then
      for dkey, d in pairs(byChar) do
        local m = merged[dkey]
        if not m then
          m = { name = d.name, difficulty = d.difficulty, runs = 0, completed = 0, bosses = 0, deaths = 0, time = 0 }
          merged[dkey] = m
          view.dungeons[#view.dungeons + 1] = m
        end
        m.name = m.name or d.name
        m.difficulty = m.difficulty or d.difficulty
        m.runs = m.runs + (d.runs or 0)
        m.completed = m.completed + (d.completed or 0)
        m.bosses = m.bosses + (d.bosses or 0)
        m.deaths = m.deaths + (d.deaths or 0)
        m.time = m.time + (d.time or 0)
        if (d.last_at or 0) > (m.last_at or 0) then
          m.last_at = d.last_at
        end
        for field, lower in pairs({ fastest = true, damage = false, healing = false, dps = false, hps = false }) do
          if d[field] and better(m[field], d[field].value, lower) then
            m[field] = d[field]
          end
        end
      end
    end
  end
  table.sort(view.dungeons, function(a, b)
    if a.runs ~= b.runs then
      return a.runs > b.runs
    end
    return tostring(a.name) < tostring(b.name)
  end)
  local t = view.totals
  for _, m in ipairs(view.dungeons) do
    t.runs = t.runs + m.runs
    t.completed = t.completed + m.completed
    t.bosses = t.bosses + m.bosses
    t.deaths = t.deaths + m.deaths
    t.time = t.time + m.time
    for field, lower in pairs({ fastest = true, damage = false, healing = false, dps = false, hps = false }) do
      if m[field] and better(view.bests[field], m[field].value, lower) then
        view.bests[field] = { value = m[field].value, at = m[field].at, dungeon = m.name }
      end
    end
  end
  for i = #rec.history, 1, -1 do
    local s = rec.history[i]
    if charKey == nil or s.char == charKey then
      view.history[#view.history + 1] = s
    end
  end
  return view
end

function Records.character(charKey)
  return charKey and FT.db.records.characters[charKey] or nil
end
