-- Serialise a Lua value the way the WoW client writes SavedVariables files:
--   ["key"] = value,   positional entries followed by "-- [n]" comments, %q-style strings.
-- Used by the end-to-end tests to produce a realistic ForeverTracker.lua file.
SVWriter = {}

local function quote(s)
  return string.format("%q", s)
end

local function isArray(t)
  local n = #t
  for k in pairs(t) do
    if type(k) ~= "number" or k < 1 or k > n or k ~= math.floor(k) then
      return false
    end
  end
  return true
end

local function write(v, out, indent)
  local kind = type(v)
  if kind == "string" then
    out[#out + 1] = quote(v)
  elseif kind == "number" then
    if v == math.floor(v) and math.abs(v) < 2 ^ 53 then
      out[#out + 1] = string.format("%d", v)
    else
      out[#out + 1] = string.format("%.14g", v)
    end
  elseif kind == "boolean" then
    out[#out + 1] = v and "true" or "false"
  elseif kind == "table" then
    out[#out + 1] = "{\n"
    if isArray(v) then
      for i = 1, #v do
        write(v[i], out, indent + 1)
        out[#out + 1] = ", -- [" .. i .. "]\n"
      end
    else
      local keys = {}
      for k in pairs(v) do
        keys[#keys + 1] = k
      end
      table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
      for _, k in ipairs(keys) do
        if type(k) == "string" then
          out[#out + 1] = "[" .. quote(k) .. "] = "
        else
          out[#out + 1] = "[" .. tostring(k) .. "] = "
        end
        write(v[k], out, indent + 1)
        out[#out + 1] = ",\n"
      end
    end
    out[#out + 1] = "}"
  else
    out[#out + 1] = "nil"
  end
end

function SVWriter.serialize(globals)
  local out = { "\n" }
  local names = {}
  for name in pairs(globals) do
    names[#names + 1] = name
  end
  table.sort(names)
  for _, name in ipairs(names) do
    out[#out + 1] = name .. " = "
    write(globals[name], out, 0)
    out[#out + 1] = "\n"
  end
  return table.concat(out)
end
