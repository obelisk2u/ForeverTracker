-- Deterministic JSON encoder for export strings (object keys sorted, arrays detected).
-- Non-finite numbers become null. Only plain data (no functions/userdata) is encodable.
local _, FT = ...

local Json = {}
FT.Json = Json

local ESCAPES = { ['"'] = '\\"', ["\\"] = "\\\\", ["\b"] = "\\b", ["\f"] = "\\f", ["\n"] = "\\n", ["\r"] = "\\r", ["\t"] = "\\t" }

local function encodeString(s)
  return '"' .. string.gsub(s, '[%c"\\]', function(c)
    return ESCAPES[c] or string.format("\\u%04x", string.byte(c))
  end) .. '"'
end

local function encodeNumber(n)
  if n ~= n or n == math.huge or n == -math.huge then
    return "null"
  end
  if n == math.floor(n) and math.abs(n) < 2 ^ 53 then
    return string.format("%d", n)
  end
  return string.format("%.14g", n)
end

local function arrayLength(t)
  local n = 0
  for k in pairs(t) do
    if type(k) ~= "number" or k < 1 or k ~= math.floor(k) then
      return nil
    end
    n = n + 1
  end
  for i = 1, n do
    if t[i] == nil then
      return nil
    end
  end
  return n
end

local encode

local function encodeTable(t, depth)
  if depth > 40 then
    error("json: nesting too deep")
  end
  local n = arrayLength(t)
  local out = {}
  if n then
    for i = 1, n do
      out[i] = encode(t[i], depth + 1)
    end
    return "[" .. table.concat(out, ",") .. "]"
  end
  local keys = {}
  for k in pairs(t) do
    keys[#keys + 1] = tostring(k)
  end
  table.sort(keys)
  for _, k in ipairs(keys) do
    local v = t[k]
    if v == nil then
      v = t[tonumber(k)]
    end
    out[#out + 1] = encodeString(k) .. ":" .. encode(v, depth + 1)
  end
  return "{" .. table.concat(out, ",") .. "}"
end

encode = function(v, depth)
  local kind = type(v)
  if kind == "nil" then
    return "null"
  elseif kind == "boolean" then
    return v and "true" or "false"
  elseif kind == "number" then
    return encodeNumber(v)
  elseif kind == "string" then
    return encodeString(v)
  elseif kind == "table" then
    return encodeTable(v, depth or 0)
  end
  error("json: cannot encode " .. kind)
end

function Json.encode(value)
  return encode(value, 0)
end
