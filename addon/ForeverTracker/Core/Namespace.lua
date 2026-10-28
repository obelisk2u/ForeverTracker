-- ForeverTracker: shared namespace, constants and small utilities.
local addonName, FT = ...

FT.name = addonName
FT.version = "0.1.0"
FT.SCHEMA_VERSION = 1
FT.SV_FORMAT = "forevertracker.savedvariables"
FT.EXPORT_FORMAT = "forevertracker.savedvariables"

-- Forever's interface numbers are 16000-16999 (it shares Retail's WOW_PROJECT_ID, so the
-- project ID cannot tell them apart). See docs/RESEARCH_FOREVER_API.md section 3.
FT.FOREVER_INTERFACE_MIN = 16000
FT.FOREVER_INTERFACE_MAX = 16999

FT.Util = {}
local Util = FT.Util

function Util.now()
  -- Server epoch seconds keep different observers' records on one clock.
  if GetServerTime then
    local ok, t = pcall(GetServerTime)
    if ok and type(t) == "number" then
      return t
    end
  end
  return time()
end

function Util.clockOffset()
  if not GetServerTime then
    return nil
  end
  local ok, t = pcall(GetServerTime)
  if not ok or type(t) ~= "number" then
    return nil
  end
  return time() - t
end

function Util.copy(value, seen)
  if type(value) ~= "table" then
    return value
  end
  seen = seen or {}
  if seen[value] then
    return seen[value]
  end
  local out = {}
  seen[value] = out
  for k, v in pairs(value) do
    out[Util.copy(k, seen)] = Util.copy(v, seen)
  end
  return out
end

function Util.count(t)
  local n = 0
  for _ in pairs(t or {}) do
    n = n + 1
  end
  return n
end

function Util.print(msg)
  local frame = DEFAULT_CHAT_FRAME
  if frame and frame.AddMessage then
    frame:AddMessage("|cff6fb3ffForeverTracker|r: " .. tostring(msg))
  end
end

function Util.debug(msg)
  if FT.db and FT.db.settings and FT.db.settings.debug then
    Util.print("|cff999999" .. tostring(msg) .. "|r")
  end
end

function Util.randomHex(len)
  local parts = {}
  for i = 1, len do
    parts[i] = string.format("%x", math.random(0, 15))
  end
  return table.concat(parts)
end

function Util.isForeverClient()
  local _, _, _, interface = GetBuildInfo()
  return type(interface) == "number" and interface >= FT.FOREVER_INTERFACE_MIN and interface <= FT.FOREVER_INTERFACE_MAX
end
