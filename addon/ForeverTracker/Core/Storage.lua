-- SavedVariables lifecycle and bounded storage.
--
-- ForeverTrackerDB (account-wide) holds:
--   observations : ring buffer of finished records (dungeon_run, character_snapshot, probe_report)
--   active_run   : the run in progress, so a /reload or relog can resume it
--   group_seen   : when each group member was last recorded (Collectors/Group.lua)
--   diagnostics  : persistence-test marker and the last probe summary
--
-- The client writes SavedVariables on logout, exit and /reload, never continuously. During
-- the beta (build 69893) it also failed to *load* them; Storage never assumes earlier data
-- exists (docs/RESEARCH_FOREVER_API.md section 10).
local addonName, FT = ...

local Storage = {}
FT.Storage = Storage

local function fresh()
  return {
    format = FT.SV_FORMAT,
    schema_version = FT.SCHEMA_VERSION,
    installation_id = "ft-" .. FT.Util.randomHex(16),
    created_at = FT.Util.now(),
    addon_version = FT.version,
    load_count = 0,
    next_seq = 1,
    settings = FT.Config.defaults(),
    observations = {},
    active_run = nil,
    dropped = { observations = 0 },
    diagnostics = {},
  }
end

local function migrate(db)
  -- Schema version 1 is the first released schema; future migrations go here.
  db.settings = db.settings or FT.Config.defaults()
  db.settings.collectors = db.settings.collectors or {}
  db.observations = db.observations or {}
  db.dropped = db.dropped or { observations = 0 }
  db.diagnostics = db.diagnostics or {}
  db.group_seen = db.group_seen or {}
  db.next_seq = db.next_seq or 1
  return db
end

function Storage.init()
  local db = ForeverTrackerDB
  local loaded = type(db) == "table" and db.format == FT.SV_FORMAT
  if loaded and (type(db.schema_version) ~= "number" or db.schema_version > FT.SCHEMA_VERSION) then
    -- Written by a newer addon version; keep it untouched rather than corrupting it.
    FT.Util.print("saved data was written by a newer version of ForeverTracker; starting a temporary session store.")
    FT.readOnlyFuture = db
    loaded = false
  end
  if not loaded then
    db = fresh()
  end
  db = migrate(db)
  db.load_count = (db.load_count or 0) + 1
  db.addon_version = FT.version
  db.client = Storage.clientInfo()
  ForeverTrackerDB = db
  FT.db = db
  FT.loadedExistingData = loaded
  return db
end

function Storage.clientInfo()
  local version, build, _, interface = GetBuildInfo()
  local info = {
    game_version = type(version) == "string" and version or nil,
    build = type(build) == "string" and build or nil,
    interface = type(interface) == "number" and interface or nil,
    locale = GetLocale and GetLocale() or nil,
    project_id = WOW_PROJECT_ID,
  }
  return info
end

function Storage.nextId(prefix)
  local db = FT.db
  local seq = db.next_seq or 1
  db.next_seq = seq + 1
  return string.format("%s-%d-%d", prefix, FT.Util.now(), seq)
end

-- Over the limit, the oldest group-member record goes first: those are the least valuable, so a
-- raid's worth of them never pushes out a dungeon run that has not been uploaded yet.
function Storage.push(observation)
  local list = FT.db.observations
  table.insert(list, observation)
  local max = FT.Config.LIMITS.max_observations
  while #list > max do
    local victim = 1
    for i, o in ipairs(list) do
      if o.source == "group" then
        victim = i
        break
      end
    end
    table.remove(list, victim)
    FT.db.dropped.observations = (FT.db.dropped.observations or 0) + 1
  end
end

function Storage.setActiveRun(run)
  FT.db.active_run = run
end

function Storage.activeRun()
  return FT.db and FT.db.active_run
end

function Storage.purge()
  FT.db.observations = {}
  FT.db.active_run = nil
  FT.db.active_state = nil
  FT.db.snapshot_sigs = {}
  FT.db.group_seen = {}
  FT.db.dropped = { observations = 0 }
end
