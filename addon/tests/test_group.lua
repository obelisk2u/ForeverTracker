local function groupRecords()
  local out = {}
  for _, s in ipairs(observationsOf("character_snapshot")) do
    if s.source == "group" then
      out[#out + 1] = s
    end
  end
  return out
end

local function byName(records)
  local out = {}
  for _, s in ipairs(records) do
    out[s.subject.name] = s
  end
  return out
end

describe("group members outside dungeons", function()
  it("records everyone in the group by name, class and race, without level or role", function()
    boot()
    eq(Mock.instance.inInstance, false)
    local records = groupRecords()
    eq(#records, 4, "the four other members, not the player")
    local mah = byName(records).Mah
    eq(mah.subject.surname, "Beardlong")
    eq(mah.subject.guid, "Player-4620-0000A2")
    eq(mah.subject.class_file, "WARRIOR")
    eq(mah.subject.race_file, "Dwarf")
    eq(mah.subject.level, nil, "level changes, so it is left out")
    eq(mah.subject.role, nil)
    eq(mah.equipment, nil)
    eq(mah.recorded_by.name, "Autumn")
    falsy(byName(records).Autumn, "the player has their own snapshot")
  end)

  it("records someone who joins later, and nobody twice", function()
    boot()
    local party = DefaultParty()
    party[#party] = nil -- Thalen leaves...
    Mock.setParty(party)
    -- ...and Ivo takes his place.
    party[#party + 1] = { name = "Ivo", surname = "Stonebrook", guid = "Player-4620-0000B1", class = "PALADIN", race = "Human", level = 12 }
    Mock.setParty(party)
    Mock.advance(1)
    local records = groupRecords()
    eq(#records, 5)
    eq(byName(records).Ivo.subject.class_file, "PALADIN")
  end)

  it("records a member again only after a change or a week", function()
    local ft = boot()
    eq(ft.Group.scan(), 0, "unchanged and recorded moments ago")
    Mock.unitByName("Mah").name = "Mahk"
    eq(ft.Group.scan(), 1, "a renamed character is recorded again")
    Mock.advance(7 * 24 * 3600)
    eq(ft.Group.scan(), 4, "a week later everyone is refreshed")
  end)

  it("skips members whose names have not loaded yet", function()
    local party = DefaultParty()
    party[2].name = "Unknown"
    boot(party)
    eq(#groupRecords(), 3)
  end)

  it("can be switched off with /ft disable group", function()
    local ft = boot()
    local before = #groupRecords()
    ft.Config.set("group", false)
    Mock.advance(7 * 24 * 3600)
    eq(ft.Group.scan(), 0)
    eq(#groupRecords(), before)
  end)

  it("gives up group records before older dungeon runs when storage is full", function()
    local ft = boot()
    local max = ft.Config.LIMITS.max_observations
    local before = #ForeverTrackerDB.observations
    table.insert(ForeverTrackerDB.observations, 1, { type = "dungeon_run", observation_id = "r-oldest" })
    -- Overflow by exactly as many records as there are group records.
    for i = 1, max - before - 1 + #groupRecords() do
      ft.Storage.push({ type = "probe_report", observation_id = "p-" .. i })
    end
    eq(#ForeverTrackerDB.observations, max)
    eq(#groupRecords(), 0, "the group records went first")
    eq(ForeverTrackerDB.observations[1].observation_id, "r-oldest", "the oldest record, a run, survived")
  end)
end)

describe("raid groups", function()
  -- A raid group: "player" plus raid1..raidN, the player also being one of the raidN tokens (as in the client).
  local function raidGroup(size)
    local party = DefaultParty()
    Mock.units = {}
    for i = 1, size do
      local spec = party[i] or { name = "Raider" .. i, surname = "Clan" .. i, guid = string.format("Player-4620-00B%03d", i), class = "MAGE", race = "Human", level = 60 }
      spec.dead, spec.connected, spec.token = false, true, "raid" .. i
      Mock.units["raid" .. i] = spec
    end
    Mock.units.player = Mock.units.raid1
    Mock.group.inRaid = true
    Mock.group.num = size
    Mock.fire("GROUP_ROSTER_UPDATE")
    Mock.advance(1)
  end

  it("records each raid member once, and not the player", function()
    boot()
    local before = #groupRecords()
    raidGroup(20)
    local records = groupRecords()
    local names = {}
    for i = before + 1, #records do
      local n = records[i].subject.name
      falsy(names[n], n .. " recorded twice")
      names[n] = true
    end
    falsy(names.Autumn, "the player is raid1 as well, and is not a group member of their own")
    eq(#records - before + 4, 19, "everyone else in the raid, counting the four already recorded as a party")
  end)
end)

describe("raid groups and inspection", function()
  it("does not queue the player for inspection when they are one of the raid units", function()
    boot()
    local party = DefaultParty()
    Mock.units = {}
    for i, spec in ipairs(party) do
      spec.dead, spec.connected, spec.token = false, true, "raid" .. i
      Mock.units["raid" .. i] = spec
    end
    Mock.units.player = Mock.units.raid1
    Mock.group.inRaid, Mock.group.num = true, #party
    Mock.ft.Inspect.queueGroup()
    local guids = {}
    for _, q in ipairs(Mock.ft.inspectState.queue) do
      guids[q.guid] = true
    end
    falsy(guids["Player-4620-0000A1"], "the player's own raid unit")
    truthy(guids["Player-4620-0000A2"], "the others are queued")
  end)
end)
