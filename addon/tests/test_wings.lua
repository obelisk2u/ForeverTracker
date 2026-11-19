-- Scarlet Monastery's four wings share instance map 189: each is its own dungeon in the records,
-- named after the wing of the first of its bosses a run pulls (FT.WINGS in Data/Dungeons.lua).

local AUTUMN = "g:Player-4620-0000A1"
local SM = { name = "Scarlet Monastery", mapId = 189 }

local function boss(id, name, success, seconds)
  Mock.fire("ENCOUNTER_START", id, name, 1, 5)
  Mock.advance(seconds or 60)
  Mock.fire("ENCOUNTER_END", id, name, 1, 5, success and 1 or 0, {})
end

local function records()
  return ForeverTrackerDB.records
end

local function storedRuns()
  local n = 0
  for _, o in ipairs(ForeverTrackerDB.observations or {}) do
    if o.type == "dungeon_run" then
      n = n + 1
    end
  end
  return n
end

local function names(history)
  local out = {}
  for _, s in ipairs(history) do
    out[#out + 1] = s.dungeon .. " (" .. s.result .. ")"
  end
  return table.concat(out, ", ")
end

-- One wing, cleared: in, its bosses, out.
local function clear(bosses)
  Mock.enterDungeon(SM)
  Mock.advance(120)
  for _, b in ipairs(bosses) do
    boss(b[1], b[2], true)
    Mock.advance(120)
  end
  Mock.leaveInstance()
  Mock.advance(60)
end

local GRAVEYARD = { { 444, "Interrogator Vishas" }, { 2779, "Bloodmage Thalnos" } }
local LIBRARY = { { 446, "Houndmaster Loksey" }, { 447, "Arcanist Doan" } }
local ARMORY = { { 448, "Herod" } }
local CATHEDRAL = { { 449, "High Inquisitor Fairbanks" }, { 450, "High Inquisitor Whitemane" } }

describe("Scarlet Monastery wings", function()
  it("gives each wing its own records", function()
    local ft = boot()
    clear(GRAVEYARD)
    clear(LIBRARY)
    clear(ARMORY)
    clear(CATHEDRAL)
    eq(
      names(records().history),
      "Scarlet Monastery: Graveyard (completed), Scarlet Monastery: Library (completed), "
        .. "Scarlet Monastery: Armory (completed), Scarlet Monastery: Cathedral (completed)"
    )
    local view = ft.Records.view(AUTUMN)
    eq(#view.dungeons, 4, "four dungeons, not one")
    for _, d in ipairs(view.dungeons) do
      eq(d.runs, 1, d.name)
      eq(d.completed, 1, d.name)
    end
  end)

  it("names the wing on the scoreboard once one of its bosses is pulled", function()
    local ft = boot()
    Mock.enterDungeon(SM)
    eq(ft.dungeonName(activeRun()), "Scarlet Monastery")
    boss(446, "Houndmaster Loksey", true)
    eq(ft.dungeonName(activeRun()), "Scarlet Monastery: Library")
  end)

  it("keeps a run that pulled no boss as the whole dungeon", function()
    boot()
    Mock.enterDungeon(SM)
    Mock.advance(120)
    Mock.leaveInstance()
    Mock.advance(901)
    eq(names(records().history), "Scarlet Monastery (left)")
  end)

  it("starts a new run when the group goes into another wing before the last boss", function()
    boot()
    Mock.enterDungeon(SM)
    boss(444, "Interrogator Vishas", true)
    Mock.advance(300)
    Mock.leaveInstance() -- skipped Thalnos and walked over to the Library
    Mock.advance(90)
    Mock.enterDungeon(SM)
    Mock.advance(200)
    boss(446, "Houndmaster Loksey", true)
    eq(activeRun().encounters[1].encounter_id, 446, "the open run is the Library one")
    boss(447, "Arcanist Doan", true)
    Mock.advance(30)
    eq(names(records().history), "Scarlet Monastery: Graveyard (left), Scarlet Monastery: Library (completed)")
  end)

  it("splits a run an earlier version stored across two wings, when the addon loads", function()
    local ft = boot()
    ft.RunTracker.splitOnRepeat = function() end -- what earlier versions did
    ft.WINGS[189] = nil
    Mock.enterDungeon(SM)
    boss(444, "Interrogator Vishas", true)
    Mock.leaveInstance()
    Mock.advance(90)
    Mock.enterDungeon(SM)
    boss(446, "Houndmaster Loksey", true)
    boss(447, "Arcanist Doan", true)
    Mock.advance(30)
    eq(#records().history, 1, "stored as one run")
    eq(storedRuns(), 1)

    Mock.reload()
    eq(storedRuns(), 2, "the uploader sends both parts")
    eq(names(records().history), "Scarlet Monastery: Graveyard (left), Scarlet Monastery: Library (completed)")
  end)

  it("rebuilds records made before wings, once", function()
    local ft = boot()
    ft.WINGS[189] = nil -- as 0.2.10 had it
    clear(LIBRARY)
    eq(names(records().history), "Scarlet Monastery (completed)")
    ForeverTrackerDB.records.finals = nil -- made without wings
    Mock.reload()
    eq(names(records().history), "Scarlet Monastery: Library (completed)")
    local finals = ForeverTrackerDB.records.finals
    Mock.reload()
    eq(ForeverTrackerDB.records.finals, finals, "the next load does not rebuild them again")
    eq(#records().history, 1)
  end)
end)
