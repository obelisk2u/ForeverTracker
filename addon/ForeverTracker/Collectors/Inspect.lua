-- Equipment (and optionally talent) snapshots of the player and inspected group members.
--
-- Inspection is out of combat only, one request at a time, at least inspect_interval_seconds
-- apart, never while the player has the Inspect window open, and each GUID is refreshed at
-- most every inspect_refresh_seconds. Item details come from the documented item-link format
-- ("item:itemID:enchantID:gem1:gem2:gem3:gem4:...").
local _, FT = ...

local Inspect = {}
FT.Inspect = Inspect
local Safe = FT.Safe

local SLOTS = { 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18 }

function Inspect.parseLink(link)
  local s = Safe.str(link, 400)
  if not s then
    return nil
  end
  local itemString = string.match(s, "item:([%-%d:]+)")
  if not itemString then
    return nil
  end
  local fields = {}
  for part in string.gmatch(itemString .. ":", "([^:]*):") do
    fields[#fields + 1] = tonumber(part)
  end
  local itemId = fields[1]
  if not itemId or itemId < 1 then
    return nil
  end
  local gems = {}
  for i = 3, 6 do
    if fields[i] and fields[i] > 0 then
      gems[#gems + 1] = fields[i]
    end
  end
  local enchant = fields[2]
  if enchant == 0 then
    enchant = nil
  end
  -- Keep the link only if it contains no control characters.
  local safeLink = string.find(s, "[%z\1-\31]") == nil and s or nil
  return { item_id = itemId, enchant_id = enchant, gem_ids = gems, link = safeLink }
end

local function itemLevel(link)
  local ok, level = Safe.call("C_Item.GetDetailedItemLevelInfo", link)
  if ok then
    local lv = Safe.num(level)
    if lv and lv >= 0 then
      return math.floor(lv)
    end
  end
  return nil
end

function Inspect.readEquipment(unit)
  local items = {}
  local missing = 0
  for _, slot in ipairs(SLOTS) do
    local ok, link = Safe.call("GetInventoryItemLink", unit, slot)
    if ok and type(link) ~= "nil" then
      local item = Inspect.parseLink(link)
      if item then
        item.slot = slot
        item.item_level = itemLevel(link)
        local okQ, quality = Safe.call("GetInventoryItemQuality", unit, slot)
        item.quality = okQ and Safe.num(quality) or nil
        items[#items + 1] = item
      else
        missing = missing + 1
      end
    end
  end
  local avg
  if unit == "player" then
    local ok, _, equipped = Safe.call("GetAverageItemLevel")
    avg = ok and Safe.num(equipped) or nil
  else
    local ok, level = Safe.call("C_PaperDollInfo.GetInspectItemLevel", unit)
    avg = ok and Safe.num(level) or nil
  end
  if avg and avg <= 0 then
    avg = nil
  end
  local status = (#items == 0 and "unavailable") or (missing > 0 and "partial") or "observed"
  return { status = status, average_item_level = avg, items = items }
end

local function talents(unit)
  if not FT.Config.enabled("talents") then
    return { status = "disabled" }
  end
  local str
  if unit == "player" then
    local okCfg, configId = Safe.call("C_ClassTalents.GetActiveConfigID")
    local id = okCfg and Safe.num(configId)
    if id then
      local ok, s = Safe.call("C_Traits.GenerateImportString", id)
      str = ok and Safe.str(s, 2000) or nil
    end
  else
    local ok, s = Safe.call("C_Traits.GenerateInspectImportString", unit)
    str = ok and Safe.str(s, 2000) or nil
  end
  if str and not string.match(str, "^[%w%+/=_%-]+$") then
    str = nil
  end
  local spec
  if unit ~= "player" then
    local ok, s = Safe.call("C_SpecializationInfo.GetInspectSpecialization", unit)
    spec = ok and Safe.num(s) or nil
  end
  return { status = str and "observed" or "unavailable", import_string = str, spec_id = spec }
end

local function signature(equipment)
  local parts = {}
  for _, item in ipairs(equipment.items) do
    parts[#parts + 1] = item.slot .. ":" .. item.item_id .. ":" .. tostring(item.enchant_id)
  end
  return table.concat(parts, ",")
end

-- Build and store a character_snapshot observation for a unit.
function Inspect.snapshot(unit, source)
  local subject = FT.Identity.read(unit)
  if not subject or subject.identity_status ~= "ok" then
    return nil
  end
  local equipment = Inspect.readEquipment(unit)
  local key = FT.Identity.key(subject)
  FT.db.snapshot_sigs = FT.db.snapshot_sigs or {}
  local sig = signature(equipment) .. "|" .. tostring(subject.level)
  if key and FT.db.snapshot_sigs[key] == sig then
    return nil -- unchanged since the last snapshot
  end
  local player = FT.Identity.player() or {}
  local observation = {
    type = "character_snapshot",
    observation_id = FT.Storage.nextId("s"),
    revision = 1,
    recorded_by = { guid = player.guid, name = player.name, surname = player.surname },
    namespace = FT.Identity.namespace(),
    realm_label = FT.Identity.realmLabel(),
    client_build = FT.db.client and FT.db.client.build or nil,
    observed_at = FT.Util.now(),
    source = source,
    subject = {
      guid = subject.guid,
      name = subject.name,
      surname = subject.surname,
      identity_status = subject.identity_status,
      class_file = subject.class_file,
      race_file = subject.race_file,
      level = subject.level,
    },
    equipment = equipment,
    talents = talents(unit),
  }
  FT.Storage.push(observation)
  if key then
    FT.db.snapshot_sigs[key] = sig
  end
  return observation
end

function Inspect.selfSnapshot(force)
  local state = FT.inspectState
  local now = FT.Util.now()
  if not force and state.last_self and now - state.last_self < FT.Config.LIMITS.self_snapshot_interval_seconds then
    return nil
  end
  state.last_self = now
  return Inspect.snapshot("player", "self")
end

FT.inspectState = { queue = {}, pending = nil, last_request = 0, last_by_guid = {} }

local function inspectFrameShown()
  local f = _G.InspectFrame
  return f and f.IsShown and f:IsShown()
end

function Inspect.queueGroup()
  if not FT.Config.enabled("inspect") then
    return
  end
  local state = FT.inspectState
  local now = FT.Util.now()
  for _, unit in ipairs(FT.Roster.units()) do
    if unit ~= "player" then
      local okGuid, guid = Safe.call("UnitGUID", unit)
      local g = okGuid and Safe.str(guid, 96)
      if g then
        local last = state.last_by_guid[g]
        if not last or now - last >= FT.Config.LIMITS.inspect_refresh_seconds then
          local queued = false
          for _, q in ipairs(state.queue) do
            if q.guid == g then
              queued = true
            end
          end
          if not queued then
            state.queue[#state.queue + 1] = { unit = unit, guid = g }
          end
        end
      end
    end
  end
end

-- Called on a ticker: issue at most one inspect request.
function Inspect.step()
  if not FT.Config.enabled("inspect") then
    return
  end
  local state = FT.inspectState
  local clock = GetTime()
  if state.pending then
    if clock - state.pending.at > FT.Config.LIMITS.inspect_timeout_seconds then
      state.pending = nil -- no INSPECT_READY; try again later
    else
      return
    end
  end
  if #state.queue == 0 or FT.Meter.inCombat() or inspectFrameShown() then
    return
  end
  if clock - state.last_request < FT.Config.LIMITS.inspect_interval_seconds then
    return
  end
  local nextReq = table.remove(state.queue, 1)
  local okGuid, guid = Safe.call("UnitGUID", nextReq.unit)
  if not okGuid or Safe.str(guid, 96) ~= nextReq.guid then
    return -- the unit token now points at someone else
  end
  local okCan, can = Safe.call("CanInspect", nextReq.unit)
  if not okCan or Safe.bool(can) ~= true then
    return
  end
  if pcall(NotifyInspect, nextReq.unit) then
    state.pending = { unit = nextReq.unit, guid = nextReq.guid, at = clock }
    state.last_request = clock
  end
end

function Inspect.ready(inspecteeGuid)
  local state = FT.inspectState
  local pending = state.pending
  local g = Safe.str(inspecteeGuid, 96)
  if not pending or g ~= pending.guid then
    return
  end
  state.pending = nil
  local okGuid, guid = Safe.call("UnitGUID", pending.unit)
  if okGuid and Safe.str(guid, 96) == g then
    Inspect.snapshot(pending.unit, "inspect")
    state.last_by_guid[g] = FT.Util.now()
  end
  if not inspectFrameShown() then
    pcall(ClearInspectPlayer)
  end
end
