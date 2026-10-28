-- Secret-value-safe access to client data.
--
-- Midnight-engine clients (Forever included) return "secret values" from restricted APIs.
-- Tainted (addon) code must not compare, do arithmetic on, or boolean-test them; doing so
-- throws. Every value read from a restricted API goes through these helpers BEFORE any use,
-- and a secret is turned into (nil, "secret"). See docs/RESEARCH_FOREVER_API.md section 7.2.
local _, FT = ...

local Safe = {}
FT.Safe = Safe

local function isSecret(v)
  local check = issecretvalue
  if check == nil then
    return false
  end
  local ok, result = pcall(check, v)
  -- If the check itself fails we cannot prove the value is safe.
  return (not ok) or result == true
end
Safe.isSecret = isSecret

local function isSecretTable(t)
  local check = issecrettable
  if check == nil then
    return false
  end
  local ok, result = pcall(check, t)
  return (not ok) or result == true
end
Safe.isSecretTable = isSecretTable

-- Returns value, or nil plus a reason ("secret" / "nil").
-- The secret check comes first: even `v == nil` is a comparison, which throws on a secret.
-- type() is permitted on secrets.
function Safe.read(v)
  if isSecret(v) then
    return nil, "secret"
  end
  if type(v) == "nil" then
    return nil, "nil"
  end
  return v
end

function Safe.str(v, maxLen)
  local value, reason = Safe.read(v)
  if value == nil then
    return nil, reason
  end
  if type(value) ~= "string" or value == "" then
    return nil, "invalid"
  end
  if maxLen and #value > maxLen then
    value = string.sub(value, 1, maxLen)
  end
  return value
end

function Safe.num(v)
  local value, reason = Safe.read(v)
  if value == nil then
    return nil, reason
  end
  if type(value) ~= "number" or value ~= value or value == math.huge or value == -math.huge then
    return nil, "invalid"
  end
  return value
end

function Safe.bool(v)
  local value, reason = Safe.read(v)
  if value == nil then
    return nil, reason
  end
  if type(value) ~= "boolean" then
    return nil, "invalid"
  end
  return value
end

function Safe.table(t)
  local kind = type(t)
  if kind ~= "table" then
    if kind == "nil" then
      return nil, "nil"
    end
    return nil, isSecret(t) and "secret" or "invalid"
  end
  if isSecretTable(t) or isSecret(t) then
    return nil, "secret"
  end
  return t
end

-- Resolve "C_DamageMeter.GetCombatSessionFromID" or "UnitGUID" to a function, or nil.
function Safe.api(path)
  local node = _G
  for part in string.gmatch(path, "[^%.]+") do
    if type(node) ~= "table" then
      return nil
    end
    node = node[part]
  end
  if type(node) == "function" then
    return node
  end
  return nil
end

-- pcall a named API. Returns ok, ... (ok = false with "missing" when absent).
function Safe.call(path, ...)
  local fn = Safe.api(path)
  if fn == nil then
    return false, "missing"
  end
  return pcall(fn, ...)
end
