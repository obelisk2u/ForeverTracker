-- Minimal test framework for the addon tests (Lua 5.1).
T = { results = {}, suite = "" }

function describe(name, fn)
  T.suite = name
  fn()
end

function it(name, fn)
  local ok, err = xpcall(function()
    Mock.reset()
    fn()
  end, debug.traceback)
  table.insert(T.results, { name = T.suite .. " > " .. name, ok = ok, err = ok and nil or tostring(err) })
end

local function fmt(v)
  if type(v) == "string" then
    return string.format("%q", v)
  end
  return tostring(v)
end

function eq(actual, expected, msg)
  if actual ~= expected then
    error((msg and (msg .. ": ") or "") .. "expected " .. fmt(expected) .. ", got " .. fmt(actual), 2)
  end
end

function truthy(v, msg)
  if not v then
    error((msg or "expected a truthy value") .. ", got " .. fmt(v), 2)
  end
end

function falsy(v, msg)
  if v then
    error((msg or "expected a falsy value") .. ", got " .. fmt(v), 2)
  end
end

function count(t)
  local n = 0
  for _ in pairs(t or {}) do
    n = n + 1
  end
  return n
end

-- Boot the addon logged in, outside any instance, with a five-player party.
function boot(party, opts)
  opts = opts or {}
  Mock.setParty(party or DefaultParty())
  local ft = Mock.loadAddon(opts.saved)
  Mock.fire("PLAYER_ENTERING_WORLD", true, false)
  return ft
end

function DefaultParty()
  return {
    { name = "Autumn", surname = "Redleaf", guid = "Player-4620-0000A1", class = "MAGE", race = "Human", level = 18, role = "DAMAGER", ilvl = 20,
      gear = { [1] = { id = 1001, enchant = 0 }, [5] = { id = 1005 }, [16] = { id = 1016, enchant = 33 } }, talents = "CAQAAAAAAAAA" },
    { name = "Mah", surname = "Beardlong", guid = "Player-4620-0000A2", class = "WARRIOR", race = "Dwarf", level = 18, role = "TANK", ilvl = 21,
      gear = { [1] = { id = 2001 }, [5] = { id = 2005 } } },
    { name = "Phineas", surname = "Longhorn", guid = "Player-4620-0000A3", class = "PRIEST", race = "Human", level = 17, role = "HEALER", ilvl = 19,
      gear = { [1] = { id = 3001 } } },
    { name = "Asha", surname = "Brightvale", guid = "Player-4620-0000A4", class = "ROGUE", race = "NightElf", level = 18, role = "DAMAGER", ilvl = 20,
      gear = { [1] = { id = 4001 } } },
    { name = "Thalen", surname = "Brightvale", guid = "Player-4620-0000A5", class = "HUNTER", race = "Dwarf", level = 19, role = "DAMAGER", ilvl = 22,
      gear = { [1] = { id = 5001 } } },
  }
end

function activeRun()
  return ForeverTrackerDB and ForeverTrackerDB.active_run
end

function lastObservation(kind)
  local list = ForeverTrackerDB.observations
  for i = #list, 1, -1 do
    if kind == nil or list[i].type == kind then
      return list[i]
    end
  end
end

function observationsOf(kind)
  local out = {}
  for _, o in ipairs(ForeverTrackerDB.observations) do
    if o.type == kind then
      out[#out + 1] = o
    end
  end
  return out
end

function member(run, name)
  for _, m in ipairs(run.roster) do
    if m.name == name then
      return m
    end
  end
end
