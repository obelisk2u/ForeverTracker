-- Group roster tracking for the active run.
--
-- Members get a run-local reference ("u1", "u2", ...). Presence is a list of intervals during
-- which the member was in the group while the observer was inside the instance.
local _, FT = ...

local Roster = {}
FT.Roster = Roster
local Safe = FT.Safe

function Roster.units()
  local units = { "player" }
  local okRaid, inRaid = Safe.call("IsInRaid")
  local okNum, num = Safe.call("GetNumGroupMembers")
  local n = (okNum and Safe.num(num)) or 0
  if okRaid and Safe.bool(inRaid) == true then
    for i = 1, math.min(n, 40) do
      units[#units + 1] = "raid" .. i
    end
  else
    for i = 1, 4 do
      units[#units + 1] = "party" .. i
    end
  end
  return units
end

local function findByName(run, member)
  if not member.name then
    return nil
  end
  for _, entry in ipairs(run.roster) do
    if entry.name == member.name and entry.surname == member.surname and (entry.guid == nil or member.guid == nil) then
      return entry
    end
  end
  return nil
end

local function update(entry, member)
  if member.guid and not entry.guid then
    entry.guid = member.guid
  end
  if member.name and not entry.name then
    entry.name, entry.surname = member.name, member.surname
  end
  if entry.identity_status ~= "ok" and member.identity_status == "ok" then
    entry.identity_status = "ok"
  end
  if member.level and (entry.level == nil or member.level > entry.level) then
    entry.level = member.level
  end
  if member.role and member.role ~= "NONE" then
    entry.role = member.role
  elseif entry.role == nil then
    entry.role = member.role
  end
  entry.class_file = entry.class_file or member.class_file
  entry.class_id = entry.class_id or member.class_id
  entry.race_file = entry.race_file or member.race_file
  entry.race_id = entry.race_id or member.race_id
end

local function openInterval(entry, now)
  local p = entry.presence
  local last = p[#p]
  if last == nil or last["end"] ~= nil then
    p[#p + 1] = { start = now }
  end
end

local function closeInterval(entry, now)
  local p = entry.presence
  local last = p[#p]
  if last and last["end"] == nil then
    last["end"] = now
  end
end

function Roster.closeAll(run, now)
  for _, entry in ipairs(run.roster) do
    closeInterval(entry, now)
  end
end

-- Scan the group and update the run's roster. Returns joined, left counts.
function Roster.scan(run, state, now)
  state.refs = state.refs or {}
  state.units = {}
  state.connected = state.connected or {}
  local seen = {}
  local joined = 0
  for _, unit in ipairs(Roster.units()) do
    local member = FT.Identity.read(unit)
    local key = member and FT.Identity.key(member)
    if key then
      local ref = state.refs[key]
      local entry
      if ref then
        for _, e in ipairs(run.roster) do
          if e.ref == ref then
            entry = e
            break
          end
        end
      end
      if not entry then
        entry = findByName(run, member)
        if entry then
          state.refs[key] = entry.ref
        end
      end
      if not entry and #run.roster < FT.Config.LIMITS.max_roster then
        entry = {
          ref = "u" .. (#run.roster + 1),
          identity_status = member.identity_status,
          is_observer = unit == "player",
          presence = {},
          connection_drops = 0,
        }
        run.roster[#run.roster + 1] = entry
        state.refs[key] = entry.ref
        joined = joined + 1
      end
      if entry then
        update(entry, member)
        if unit == "player" then
          entry.is_observer = true
        end
        openInterval(entry, now)
        seen[entry.ref] = true
        state.units[entry.ref] = unit
        local okConn, conn = Safe.call("UnitIsConnected", unit)
        local connected = okConn and Safe.bool(conn)
        if connected == false and state.connected[entry.ref] ~= false then
          entry.connection_drops = (entry.connection_drops or 0) + 1
        end
        if connected ~= nil then
          state.connected[entry.ref] = connected
        end
      end
    elseif member then
      state.unidentified = (state.unidentified or 0) + 1
    end
  end
  local left = 0
  for _, entry in ipairs(run.roster) do
    if not seen[entry.ref] then
      local p = entry.presence[#entry.presence]
      if p and p["end"] == nil then
        left = left + 1
      end
      closeInterval(entry, now)
    end
  end
  return joined, left
end

function Roster.refForGuid(state, guid)
  return guid and state.refs and state.refs["g:" .. guid] or nil
end

function Roster.refForName(run, name)
  if not name then
    return nil
  end
  for _, entry in ipairs(run.roster) do
    if entry.name == name then
      return entry.ref
    end
  end
  return nil
end

function Roster.observerRef(run)
  for _, entry in ipairs(run.roster) do
    if entry.is_observer then
      return entry.ref
    end
  end
  return nil
end
