-- Character identity of units, read without ever touching a secret value.
--
-- Forever names are two-part: UnitName-family functions return firstName, surname. The second
-- value is a SURNAME, not a realm (docs/RESEARCH_FOREVER_API.md section 4.1). We only interpret
-- it as a surname when RegionalUniqueNamesEnabled() says names are regional; otherwise it is a
-- realm and is stored as such.
local _, FT = ...

local Identity = {}
FT.Identity = Identity
local Safe = FT.Safe

local PLACEHOLDER_NAMES = { [""] = true, ["Unknown"] = true, ["UNKNOWNOBJECT"] = true }
if UNKNOWNOBJECT then
  PLACEHOLDER_NAMES[UNKNOWNOBJECT] = true
end

function Identity.regionalNames()
  local ok, result = Safe.call("RegionalUniqueNamesEnabled")
  return ok and result == true
end

local function nameParts(unit)
  local fn = Safe.api("UnitNameUnmodified") or Safe.api("UnitName")
  if not fn then
    return nil, nil, "unavailable"
  end
  local ok, first, second = pcall(fn, unit)
  if not ok then
    return nil, nil, "unavailable"
  end
  local name, reason = Safe.str(first, 48)
  if reason == "secret" then
    return nil, nil, "secret"
  end
  if not name or PLACEHOLDER_NAMES[name] then
    return nil, nil, "unavailable"
  end
  local suffix, suffixReason = Safe.str(second, 48)
  if suffixReason == "secret" then
    return name, nil, "secret"
  end
  return name, suffix, "ok"
end

-- Returns a roster-member-shaped table (without ref/presence) for a unit token.
function Identity.read(unit)
  local okExists, value = Safe.call("UnitExists", unit)
  if not okExists or Safe.bool(value) ~= true then
    return nil
  end
  local member = { identity_status = "ok" }
  local name, second, status = nameParts(unit)
  member.identity_status = status
  if name then
    member.name = name
    -- Only a regional-name client returns a surname here. Elsewhere the second value is a
    -- realm, which ForeverTracker does not use for identity, so it is dropped.
    if Identity.regionalNames() then
      member.surname = second
    end
  end

  local okGuid, guid = Safe.call("UnitGUID", unit)
  if okGuid then
    local g, reason = Safe.str(guid, 96)
    if g and string.match(g, "^[%w%-]+$") then
      member.guid = g
    elseif reason == "secret" then
      member.identity_status = "secret"
    end
  end

  local okClass, _, classFile, classId = Safe.call("UnitClass", unit)
  if okClass then
    local cf = Safe.str(classFile, 24)
    if cf and string.match(cf, "^[A-Z_]+$") then
      member.class_file = cf
    end
    member.class_id = Safe.num(classId)
  end
  local okRace, _, raceFile, raceId = Safe.call("UnitRace", unit)
  if okRace then
    local rf = Safe.str(raceFile, 32)
    if rf and string.match(rf, "^[%a_]+$") then
      member.race_file = rf
    end
    member.race_id = Safe.num(raceId)
  end
  local okLevel, level = Safe.call("UnitLevel", unit)
  if okLevel then
    local lv = Safe.num(level)
    if lv and lv >= 1 then
      member.level = lv
    end
  end
  local okRole, role = Safe.call("UnitGroupRolesAssigned", unit)
  if okRole then
    local r = Safe.str(role, 8)
    if r == "TANK" or r == "HEALER" or r == "DAMAGER" or r == "NONE" then
      member.role = r
    end
  end
  if member.identity_status == "ok" and not member.name then
    member.identity_status = "unavailable"
  end
  return member
end

function Identity.key(member)
  if member.guid then
    return "g:" .. member.guid
  end
  if member.name then
    return "n:" .. member.name .. "|" .. (member.surname or "")
  end
  return nil
end

-- Namespace: region + ruleset (Forever is realmless; names are unique per region).
function Identity.namespace()
  local ns = { ruleset = "unknown" }
  local okRegion, region = Safe.call("GetCurrentRegion")
  if okRegion then
    ns.region_id = Safe.num(region)
  end
  local okName, regionName = Safe.call("GetCurrentRegionName")
  if okName then
    local rn = Safe.str(regionName, 16)
    if rn and string.match(rn, "^%a+$") then
      ns.region_name = rn
    end
  end
  if Identity.regionalNames() then
    ns.ruleset = "pve"
    local rule = Enum and Enum.GameRule
    local active = Safe.api("C_GameRules.IsGameRuleActive")
    if rule and active then
      local checks = { { rule.HardcoreRuleset, "hardcore" }, { rule.RPRuleset, "rp" }, { rule.PvPRuleset, "pvp" } }
      for _, check in ipairs(checks) do
        if check[1] ~= nil then
          local ok, on = pcall(active, check[1])
          if ok and Safe.bool(on) == true then
            ns.ruleset = check[2]
            break
          end
        end
      end
    end
  end
  return ns
end

function Identity.realmLabel()
  local ok, realm = Safe.call("GetRealmName")
  if ok then
    return Safe.str(realm, 120)
  end
  return nil
end

function Identity.player()
  return Identity.read("player")
end
