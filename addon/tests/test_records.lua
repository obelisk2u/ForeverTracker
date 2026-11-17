-- The player's own dungeon records (Sessions/Records.lua) and the window and minimap button
-- that show them (UI/). The UI tests check what the window would show; how it looks needs the game.

local AUTUMN = "g:Player-4620-0000A1"

local function fight(duration, values)
  Mock.startCombat()
  Mock.advance(duration)
  Mock.endCombat(duration, values)
  Mock.advance(12) -- meter capture retries
end

local function boss(id, name, success, seconds)
  Mock.fire("ENCOUNTER_START", id, name, 1, 5)
  Mock.advance(seconds or 60)
  Mock.fire("ENCOUNTER_END", id, name, 1, 5, success and 1 or 0, {})
end

-- One dungeon run. spec: dungeon, mapId, minutes, completed, damage, healing, combat, bosses
local function dungeonRun(spec)
  Mock.enterDungeon({ name = spec.dungeon or "Hall of Thanes", mapId = spec.mapId or 990001 })
  for i = 1, spec.bosses or 0 do
    boss(3000 + i, "Boss " .. i, true)
  end
  if spec.damage or spec.healing then
    fight(spec.combat or 90, { Autumn = { damage_done = spec.damage, healing_done = spec.healing } })
  end
  Mock.advance((spec.minutes or 20) * 60)
  if spec.completed then
    Mock.fire("LFG_COMPLETION_REWARD")
  end
  Mock.leaveInstance()
  if not spec.completed then
    Mock.advance(901) -- the grace period for coming back
  end
end

local function records()
  return ForeverTrackerDB.records
end

local function contains(list, fragment)
  for _, s in ipairs(list) do
    if string.find(s, fragment, 1, true) then
      return true
    end
  end
  return false
end

describe("personal records", function()
  it("summarizes a finished run from the player's point of view", function()
    boot()
    Mock.enterDungeon({ name = "Hall of Thanes", mapId = 990001 })
    boss(3001, "Thane Gorrak", true, 90)
    boss(3002, "The Echo", false, 40)
    Mock.setDead("Autumn", true)
    Mock.advance(2)
    Mock.setDead("Autumn", false)
    boss(3002, "The Echo", true, 70)
    fight(50, { Autumn = { damage_done = 40000, interrupts = 3 }, Phineas = { healing_done = 22000 } })
    fight(30, { Autumn = { damage_done = 20000 } })
    Mock.fire("LFG_COMPLETION_REWARD")
    Mock.leaveInstance()

    local s = records().history[1]
    eq(#records().history, 1)
    eq(s.char, AUTUMN)
    eq(s.dungeon, "Hall of Thanes")
    eq(s.result, "completed")
    eq(s.bosses, 2, "two different bosses killed")
    eq(s.wipes, 1)
    eq(s.deaths, 1)
    eq(s.damage, 60000)
    eq(s.interrupts, 3)
    eq(s.healing, 0, "the meter read the mage's healing as zero")
    eq(s.combat_seconds, 80)
    eq(#s.party, 4)
    eq(s.party[1].name, "Mah")
    eq(s.party[1].class_file, "WARRIOR")
    local c = records().characters[AUTUMN]
    eq(c.name, "Autumn")
    eq(c.surname, "Redleaf")
    eq(c.class_file, "MAGE")

    local d = records().dungeons[AUTUMN]["990001:1"]
    eq(d.runs, 1)
    eq(d.completed, 1)
    eq(d.fastest.value, s.duration)
    eq(d.damage.value, 60000)
    eq(d.dps.value, 750, "60,000 damage over 80 seconds of combat")
    eq(d.healing, nil, "zero healing is not a personal best")
  end)

  it("counts a final-boss kill as a completion when no completion event fires", function()
    -- A Deadmines group formed outside the dungeon finder: the player dies on VanCleef, the
    -- group kills him, the player releases, runs back in, loots and hearthstones out.
    boot()
    Mock.enterDungeon({ name = "Deadmines", mapId = 36 })
    boss(2741, "Rhahk'Zor", true)
    Mock.fire("ENCOUNTER_START", 2747, "Edwin VanCleef", 1, 5)
    Mock.advance(20)
    Mock.setDead("Autumn", true)
    Mock.advance(25)
    Mock.fire("ENCOUNTER_END", 2747, "Edwin VanCleef", 1, 5, 1, {})
    Mock.advance(60)
    falsy(activeRun(), "the run ended with the final boss")
    local run = lastObservation("dungeon_run")
    eq(run.timing.ended_at - run.encounters[2].ended_at, 20, "once the meter had read the fight")
    Mock.leaveInstance() -- released as a ghost
    Mock.advance(150)
    Mock.enterDungeon({ name = "Deadmines", mapId = 36 }) -- ran back in
    Mock.setDead("Autumn", false)
    falsy(activeRun(), "going back in for the corpse is not a new run")
    Mock.reload()
    falsy(activeRun(), "nor is a /reload inside")
    Mock.advance(400)
    Mock.leaveInstance() -- hearthstone
    Mock.advance(901)

    eq(#observationsOf("dungeon_run"), 1)
    eq(run.state, "unknown", "the uploaded record states only what happened")
    eq(run.completion.status, "none")
    local s = records().history[1]
    eq(s.result, "completed")
    truthy(s.final_boss)
    eq(Mock.ft.Records.view(AUTUMN).totals.completed, 1)
    truthy(Mock.ft.Records.view(AUTUMN).bests.fastest, "it can be a fastest clear")
  end)

  it("ends the run shortly after the final boss dies", function()
    -- The Hall of Thanes (Forever), cleared on 2026-11-10 in this order.
    boot()
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    boss(3493, "Faldrim Anvilmar", true)
    boss(3495, "Infurnus", true)
    boss(3494, "Plunder", true)
    boss(3496, "Durgen Dirgehammer", true)
    Mock.advance(10)
    truthy(activeRun(), "the meter is still reading the fight")
    Mock.advance(10)
    falsy(activeRun())
    local run = lastObservation("dungeon_run")
    eq(run.state, "unknown")
    eq(#run.encounters, 4)
    eq(records().history[1].result, "completed")

    Mock.advance(120)
    Mock.leaveInstance() -- hearthstone
    Mock.advance(60)
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    truthy(activeRun(), "leaving alive and coming back is the next run")
    eq(#observationsOf("dungeon_run"), 1)
  end)

  it("waits for combat to end before ending the run at the final boss", function()
    boot()
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    Mock.startCombat()
    boss(3496, "Durgen Dirgehammer", true)
    Mock.advance(30)
    truthy(activeRun(), "still fighting the adds")
    Mock.endCombat(90, { Autumn = { damage_done = 30000 } })
    Mock.advance(12)
    falsy(activeRun())
    eq(records().history[1].damage, 30000, "the last fight is in the run")
  end)

  it("still ends the run at the final boss after a /reload right after the kill", function()
    boot()
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    boss(3496, "Durgen Dirgehammer", true)
    Mock.advance(5)
    Mock.reload()
    truthy(activeRun())
    Mock.advance(21)
    falsy(activeRun())
    eq(#observationsOf("dungeon_run"), 1)
    eq(records().history[1].result, "completed")
  end)

  it("ends the run at once when the player leaves alive right after the final boss", function()
    boot()
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    boss(3496, "Durgen Dirgehammer", true)
    Mock.advance(5)
    Mock.leaveInstance()
    falsy(activeRun(), "no waiting for a corpse run")
    eq(lastObservation("dungeon_run").state, "left")
    eq(records().history[1].result, "completed")
  end)

  it("keeps the run open after leaving when the final boss is still alive", function()
    boot()
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    boss(3493, "Faldrim Anvilmar", true)
    Mock.leaveInstance()
    truthy(activeRun(), "the group may still go back in")
    Mock.advance(901)
    falsy(activeRun())
    eq(records().history[1].result, "left")
  end)

  it("ends the run when the player leaves the group outside the dungeon", function()
    boot()
    Mock.fire("GROUP_JOINED", 1, "Party-1-AAAA")
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    boss(3493, "Faldrim Anvilmar", true)
    Mock.leaveInstance()
    truthy(activeRun(), "the group may still go back in")
    Mock.advance(5)
    Mock.fire("GROUP_LEFT")
    falsy(activeRun(), "no group, no run to go back to")
    local run = lastObservation("dungeon_run")
    eq(run.state, "left")
    eq(#run.encounters, 1)
  end)

  it("starts a new run when the player goes back in with a different group", function()
    boot()
    Mock.fire("GROUP_JOINED", 1, "Party-1-AAAA")
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    boss(3493, "Faldrim Anvilmar", true)
    Mock.leaveInstance()
    Mock.advance(120)
    Mock.fire("GROUP_JOINED", 1, "Party-1-BBBB") -- straight into another group
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })

    local finished = observationsOf("dungeon_run")
    eq(#finished, 1, "the first group's run is over")
    eq(finished[1].party_guid, "Party-1-AAAA")
    eq(activeRun().party_guid, "Party-1-BBBB")
    eq(#activeRun().encounters, 0)
  end)

  it("splits a run that an earlier version merged with the next group's run", function()
    local ft = boot()
    Mock.fire("GROUP_JOINED", 1, "Party-1-AAAA")
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    boss(3493, "Faldrim Anvilmar", true)
    fight(90, { Autumn = { damage_done = 50000 }, Mah = { damage_done = 30000 } })

    -- What 0.2.2 and earlier did: killing the last boss, leaving and then leaving the group kept
    -- the run open, so going back in with a new group resumed it.
    local RT = ft.RunTracker
    local finalize = RT.finalize
    RT.finalize = function() end
    RT.splitOnRepeat = function() end -- nor did they notice Faldrim being pulled again
    boss(3496, "Durgen Dirgehammer", true)
    Mock.advance(60)
    Mock.leaveInstance()
    local leftAt = Mock.clock
    Mock.advance(5)
    Mock.setParty({ DefaultParty()[1] })
    Mock.fire("GROUP_LEFT")
    Mock.advance(300)
    local newParty = {
      DefaultParty()[1],
      { name = "Bram", surname = "Stonefist", guid = "Player-4620-0000B2", class = "WARRIOR", race = "Dwarf", level = 18, role = "TANK" },
      { name = "Cyra", surname = "Dawnmere", guid = "Player-4620-0000B3", class = "PRIEST", race = "Human", level = 18, role = "HEALER" },
      { name = "Dov", surname = "Ashgrove", guid = "Player-4620-0000B4", class = "ROGUE", race = "Human", level = 18, role = "DAMAGER" },
      { name = "Esk", surname = "Ashgrove", guid = "Player-4620-0000B5", class = "HUNTER", race = "Dwarf", level = 18, role = "DAMAGER" },
    }
    Mock.enterDungeon({ name = "The Hall of Thanes", mapId = 3065 })
    local backAt = Mock.clock
    Mock.setParty(newParty)
    Mock.fire("GROUP_JOINED", 1, "Party-1-BBBB")
    local merged = activeRun().observation_id
    boss(3493, "Faldrim Anvilmar", true)
    fight(60, { Autumn = { damage_done = 20000 }, Bram = { damage_done = 10000 } })
    eq(#activeRun().encounters, 3, "merged, as the earlier version left it")

    -- The new version splits it on the next load.
    RT.finalize = finalize
    ft = Mock.reload()
    local finished = observationsOf("dungeon_run")
    eq(#finished, 1)
    local first, second = finished[1], activeRun()
    eq(first.observation_id, merged, "the first run keeps its identity")
    truthy(first.revision > 1, "and replaces what was uploaded before")
    eq(first.state, "left")
    eq(first.timing.ended_at, leftAt)
    eq(#first.encounters, 2)
    eq(first.encounters[2].name, "Durgen Dirgehammer")
    eq(#first.roster, 5)
    eq(first.party_guid, "Party-1-AAAA")
    for _, e in ipairs(first.roster) do
      truthy(e.name ~= "Bram", "the second group is not in the first run")
    end
    local function damage(run, name)
      for _, entry in ipairs(run.roster) do
        if entry.name == name then
          for _, t in ipairs(run.meter.totals) do
            if t.unit_ref == entry.ref then
              return t.metrics.damage_done.value
            end
          end
        end
      end
    end
    eq(damage(first, "Autumn"), 50000)
    eq(damage(first, "Mah"), 30000)

    truthy(second.observation_id ~= merged, "the second run is a new one")
    eq(second.revision, 1)
    eq(second.timing.started_at, backAt)
    eq(second.party_guid, "Party-1-BBBB")
    eq(second.timeline[1].kind, "entered")
    eq(#second.encounters, 1)
    eq(#second.roster, 5)
    eq(damage(second, "Autumn"), 20000)
    eq(damage(second, "Bram"), 10000)
    local refs = {}
    for _, e in ipairs(second.roster) do
      falsy(refs[e.ref], "unit refs stay unique")
      refs[e.ref] = true
    end

    local s = records().history[1]
    eq(s.result, "completed", "the first run killed the final boss")
    eq(s.damage, 50000)
    eq(#s.party, 4)

    -- The second run goes on normally, and the split happens only once.
    boss(3496, "Durgen Dirgehammer", true)
    Mock.leaveInstance()
    falsy(activeRun())
    local runs = observationsOf("dungeon_run")
    eq(#runs, 2)
    eq(#runs[2].encounters, 2)
    eq(damage(runs[2], "Autumn"), 20000)
    Mock.reload()
    eq(#observationsOf("dungeon_run"), 2)
    eq(#records().history, 2)
  end)

  it("leaves out of the group whoever only passed through", function()
    boot()
    Mock.enterDungeon({ name = "Hall of Thanes", mapId = 990001 })
    Mock.advance(60)
    Mock.removeMember("Thalen") -- left as the run began
    Mock.advance(30)
    local party = DefaultParty()
    party[5] = { name = "Kira", surname = "Stonefist", guid = "Player-4620-0000B1", class = "PALADIN", race = "Dwarf", level = 18, role = "DAMAGER" }
    Mock.setParty(party)
    Mock.advance(28)
    Mock.removeMember("Kira") -- so did the first one to take the place
    Mock.advance(60)
    party[5] = { name = "Bram", surname = "Stonefist", guid = "Player-4620-0000B2", class = "WARRIOR", race = "Dwarf", level = 18, role = "DAMAGER" }
    Mock.setParty(party)
    Mock.advance(30)
    boss(3001, "Thane Gorrak", true, 90)
    Mock.advance(600)
    Mock.fire("LFG_COMPLETION_REWARD")
    Mock.leaveInstance()

    local names = {}
    for _, p in ipairs(records().history[1].party) do
      names[#names + 1] = p.name
    end
    eq(table.concat(names, ","), "Mah,Phineas,Asha,Bram")
    eq(#lastObservation("dungeon_run").roster, 7, "the uploaded record keeps everyone")
  end)

  it("does not count a wipe on the final boss as a completion", function()
    boot()
    Mock.enterDungeon({ name = "Deadmines", mapId = 36 })
    boss(2747, "Edwin VanCleef", false)
    Mock.leaveInstance()
    Mock.advance(901)
    eq(records().history[1].result, "left")
  end)

  it("rebuilds records saved before final-boss completions were counted", function()
    boot()
    Mock.enterDungeon({ name = "Deadmines", mapId = 36 })
    boss(2747, "Edwin VanCleef", true)
    Mock.leaveInstance()
    Mock.advance(901)
    ForeverTrackerDB.records.version = 1 -- as the first records version saved it
    ForeverTrackerDB.records.history[1].result = "left"
    Mock.reload()
    eq(#records().history, 1)
    eq(records().history[1].result, "completed")
  end)

  it("keeps totals and personal bests across runs", function()
    boot()
    dungeonRun({ completed = true, minutes = 20, damage = 90000, combat = 120, bosses = 3 })
    dungeonRun({ completed = true, minutes = 15, damage = 50000, combat = 100, bosses = 3 })
    dungeonRun({ dungeon = "Sunken Archive", mapId = 990002, minutes = 5, bosses = 1 })

    local view = Mock.ft.Records.view(AUTUMN)
    eq(view.totals.runs, 3)
    eq(view.totals.completed, 2)
    eq(view.totals.bosses, 7)
    eq(#view.dungeons, 2)
    eq(view.dungeons[1].name, "Hall of Thanes", "most-played first")
    eq(view.dungeons[1].runs, 2)
    local first, second = records().history[1], records().history[2]
    truthy(second.duration < first.duration)
    eq(view.bests.fastest.value, second.duration, "the quicker clear is the fastest")
    eq(view.bests.fastest.dungeon, "Hall of Thanes")
    eq(view.bests.damage.value, 90000)
    eq(view.bests.dps.value, 750)
    eq(view.dungeons[2].fastest, nil, "leaving early never counts as a clear")
    eq(#view.history, 3)
    eq(view.history[1].dungeon, "Sunken Archive", "newest first")
  end)

  it("does not set a DPS record from a run with too little combat", function()
    boot()
    dungeonRun({ completed = true, damage = 30000, combat = 20 })
    local view = Mock.ft.Records.view(AUTUMN)
    eq(view.bests.damage.value, 30000)
    eq(view.bests.dps, nil)
  end)

  it("outlasts the upload queue's limit", function()
    local ft = boot()
    ft.Config.LIMITS.max_observations = 2
    for _ = 1, 4 do
      dungeonRun({ completed = true, minutes = 10 })
    end
    eq(#ForeverTrackerDB.observations, 2)
    eq(#records().history, 4)
    eq(ft.Records.view(AUTUMN).totals.runs, 4)
  end)

  it("builds records from runs stored by an earlier version, once", function()
    boot()
    dungeonRun({ completed = true, minutes = 12 })
    dungeonRun({ minutes = 3 })
    ForeverTrackerDB.records = nil -- as an earlier version saved it
    Mock.reload()
    eq(#records().history, 2)
    eq(Mock.ft.Records.view(AUTUMN).totals.completed, 1)
    Mock.reload()
    eq(#records().history, 2, "a second load does not count them again")
  end)

  it("are deleted by /ft purge", function()
    boot()
    dungeonRun({ completed = true })
    Mock.slash("purge confirm")
    eq(#records().history, 0)
    eq(Mock.ft.Records.view(nil).totals.runs, 0)
  end)

  it("are kept per character on the account", function()
    boot()
    dungeonRun({ completed = true })
    Mock.logout(60)
    local party = DefaultParty()
    party[1] = { name = "Bram", surname = "Oakhelm", guid = "Player-4620-0000C1", class = "PALADIN", race = "Human", level = 19, role = "TANK" }
    Mock.setParty(party)
    local ft = Mock.login()
    dungeonRun({ dungeon = "Sunken Archive", mapId = 990002, completed = true })
    eq(ft.Records.view(ft.Records.currentCharKey()).totals.runs, 1)
    eq(ft.Records.view(ft.Records.currentCharKey()).history[1].dungeon, "Sunken Archive")
    eq(ft.Records.view(nil).totals.runs, 2)
    eq(ft.Records.character("g:Player-4620-0000C1").class_file, "PALADIN")
  end)
end)

describe("reset dungeons", function()
  -- A dungeon whose final boss the addon does not know.
  local SOMEWHERE = { name = "City of Somewhere", mapId = 990002 }

  local function damage(run, name)
    for _, entry in ipairs(run.roster) do
      if entry.name == name then
        for _, t in ipairs(run.meter.totals) do
          if t.unit_ref == entry.ref then
            return t.metrics.damage_done.value
          end
        end
      end
    end
    return nil
  end

  it("starts a new run when a boss the run already killed is pulled again", function()
    boot()
    Mock.enterDungeon(SOMEWHERE)
    boss(3001, "First Boss", true)
    fight(30, { Autumn = { damage_done = 10000 } })
    boss(3002, "Last Boss", true)
    Mock.advance(60)
    Mock.leaveInstance()
    local leftAt = Mock.clock
    Mock.advance(20) -- the group resets the dungeon and goes back in
    Mock.enterDungeon(SOMEWHERE)
    local backAt = Mock.clock
    local id = activeRun().observation_id
    eq(#observationsOf("dungeon_run"), 0, "nothing said the first run was over")
    fight(20, { Autumn = { damage_done = 4000 } })

    boss(3001, "First Boss", true)
    local runs = observationsOf("dungeon_run")
    eq(#runs, 1, "pulling First Boss again ended the first run")
    local first, second = runs[1], activeRun()
    eq(first.observation_id, id)
    eq(first.timing.ended_at, leftAt)
    eq(#first.encounters, 2)
    eq(damage(first, "Autumn"), 10000)
    truthy(first.flags.split_new_instance)
    truthy(second.observation_id ~= id, "the second run is a new one")
    eq(second.timing.started_at, backAt)
    eq(#second.encounters, 1)
    eq(damage(second, "Autumn"), 4000, "the fight after going back in is the new run's")
    eq(#records().history, 1)
  end)

  it("ends a City of Dalaran run at Shade of the Archmage", function()
    boot()
    Mock.enterDungeon({ name = "City of Dalaran", mapId = 2959 })
    boss(3311, "Atrexis the Grave Knight", true)
    boss(3303, "Shade of the Archmage", true)
    Mock.advance(25)
    falsy(activeRun(), "the run ended at the final boss")
    eq(records().history[1].result, "completed")
  end)

  it("splits a run an earlier version stored as one, once, when the addon loads", function()
    local ft = boot()
    ft.RunTracker.splitOnRepeat = function() end -- what earlier versions did
    Mock.enterDungeon(SOMEWHERE)
    boss(3001, "First Boss", true)
    fight(30, { Autumn = { damage_done = 10000 } })
    -- A death and a corpse run, still in the first copy of the dungeon.
    Mock.setDead("Autumn", true)
    Mock.advance(2)
    Mock.leaveInstance()
    Mock.advance(40)
    Mock.setDead("Autumn", false)
    Mock.enterDungeon(SOMEWHERE)
    boss(3002, "Last Boss", true)
    Mock.advance(30)
    Mock.leaveInstance()
    local leftAt = Mock.clock
    Mock.advance(20)
    Mock.enterDungeon(SOMEWHERE)
    local backAt = Mock.clock
    fight(20, { Autumn = { damage_done = 4000 } })
    boss(3001, "First Boss", true)
    Mock.leaveInstance()
    Mock.advance(901)
    local merged = observationsOf("dungeon_run")
    eq(#merged, 1)
    eq(#merged[1].encounters, 3, "stored as one run")
    local id, revision = merged[1].observation_id, merged[1].revision

    Mock.reload()
    local runs = observationsOf("dungeon_run")
    eq(#runs, 2)
    local first, second = runs[1], runs[2]
    eq(first.observation_id, id, "the first run keeps its identity")
    eq(first.revision, revision + 1, "so its upload replaces the one record")
    eq(first.timing.ended_at, leftAt)
    eq(#first.encounters, 2, "the corpse run stayed in the first run")
    truthy(second.observation_id ~= id)
    eq(second.revision, 1)
    eq(second.timing.started_at, backAt)
    eq(second.timeline[1].kind, "entered")
    eq(#second.encounters, 1)
    eq(second.state, "left")
    -- Per-fight numbers are gone once a run ends: no made-up run totals.
    eq(#first.meter.totals, 0)
    eq(#second.meter.totals, 0)
    eq(second.meter.status, "partial")
    eq(#records().history, 2, "the records window shows two runs")

    Mock.reload()
    eq(#observationsOf("dungeon_run"), 2, "split only once")
    eq(#records().history, 2)
  end)
end)

describe("records window", function()
  it("opens from the minimap button and shows the runs", function()
    local ft = boot()
    dungeonRun({ completed = true, minutes = 18, damage = 120000, combat = 150, bosses = 3 })
    local button = ft.MinimapButton.button()
    truthy(button, "the minimap button exists")
    truthy(button:IsShown())
    button._scripts.OnClick(button, "LeftButton")
    truthy(ft.RecordsUI.isShown())

    local frame = ft.RecordsUI.frame()
    falsy(frame.empty:IsShown())
    local texts = Mock.texts(frame)
    truthy(contains(texts, "Hall of Thanes"), "the dungeon is listed")
    truthy(contains(texts, "Completed"), "with its result")
    truthy(contains(texts, "120.0K"), "and the player's damage")
    truthy(contains(texts, "Autumn Redleaf"), "the subtitle names the character")

    local row = frame.pages.runs.table.rows[1]
    row._scripts.OnEnter(row)
    truthy(contains(Mock.tooltip, "Mah Beardlong"), "the group is in the run's tooltip")
    truthy(contains(Mock.tooltip, "800 DPS"), "120,000 damage over 150 seconds")

    button._scripts.OnClick(button, "LeftButton")
    falsy(ft.RecordsUI.isShown(), "a second click closes it")
  end)

  it("shows an empty state before the first run, and /ft toggles it", function()
    local ft = boot()
    Mock.slash("")
    truthy(ft.RecordsUI.isShown())
    truthy(ft.RecordsUI.frame().empty:IsShown())
    falsy(ft.RecordsUI.frame().content:IsShown())
    Mock.slash("")
    falsy(ft.RecordsUI.isShown())
    Mock.slash("help")
    truthy(Mock.chatContains("/ft minimap"), "help moved to /ft help")
  end)

  it("says the run is paused while the player is outside the dungeon", function()
    local ft = boot()
    Mock.slash("records")
    Mock.enterDungeon({ name = "Hall of Thanes" })
    truthy(contains(Mock.texts(ft.RecordsUI.frame()), "Recording Hall of Thanes"))
    Mock.leaveInstance()
    truthy(contains(Mock.texts(ft.RecordsUI.frame()), "Paused: Hall of Thanes"))
    Mock.enterDungeon({ name = "Hall of Thanes" })
    truthy(contains(Mock.texts(ft.RecordsUI.frame()), "Recording Hall of Thanes"))
  end)

  it("updates while open when a run finishes", function()
    local ft = boot()
    Mock.slash("records")
    truthy(ft.RecordsUI.frame().empty:IsShown())
    dungeonRun({ completed = true })
    falsy(ft.RecordsUI.frame().empty:IsShown())
    truthy(contains(Mock.texts(ft.RecordsUI.frame()), "Hall of Thanes"))
  end)

  it("switches between this character and all characters", function()
    local ft = boot()
    dungeonRun({ completed = true })
    ft.RecordsUI.show()
    local frame = ft.RecordsUI.frame()
    eq(frame.scope.text:GetText(), "This character")
    frame.scope._scripts.OnClick(frame.scope)
    eq(frame.scope.text:GetText(), "All characters")
    truthy(contains(Mock.texts(frame), "All characters"))
  end)

  it("formats numbers and times compactly", function()
    local UI = boot().RecordsUI
    eq(UI.number(1234), "1,234")
    eq(UI.number(12345), "12.3K")
    eq(UI.number(2500000), "2.50M")
    eq(UI.number(nil), "-")
    eq(UI.duration(65), "1:05")
    eq(UI.duration(3725), "1:02:05")
    eq(UI.totalTime(3 * 3600 + 25 * 60), "3h 25m")
    eq(UI.totalTime(45 * 60), "45m")
  end)
end)

describe("scoreboard", function()
  local function page(ft)
    return ft.RecordsUI.frame().pages.scoreboard
  end

  local function row(p, name)
    for _, r in ipairs(p.table.rows) do
      if r.item and r.item.name == name then
        return r
      end
    end
    return nil
  end

  -- The texts in a row's cells: name, damage, DPS, healing, HPS, interrupts, dispels, damage taken, deaths.
  local function cells(r)
    local out = {}
    for i, fs in ipairs(r.cells) do
      out[i] = fs:GetText()
    end
    return out
  end

  local function click(button)
    button._scripts.OnClick(button)
  end

  it("is the tab during a run and fills in after each fight on its own", function()
    local ft = boot()
    Mock.slash("records")
    Mock.enterDungeon({ name = "Hall of Thanes" })
    local p = page(ft)
    truthy(p:IsShown(), "a run opens the window on the scoreboard")
    eq(#p.table.data, 5, "everyone in the group before the first fight")
    eq(cells(row(p, "Autumn"))[2], "-")
    truthy(contains(Mock.texts(p), "Nothing yet"))

    fight(50, { Autumn = { damage_done = 40000, interrupts = 3 }, Phineas = { healing_done = 22000 } })
    local autumn = cells(row(p, "Autumn"))
    truthy(string.find(autumn[1], "Autumn Redleaf", 1, true))
    eq(autumn[2], "40.0K")
    eq(autumn[3], "800", "40,000 damage over 50 seconds of combat")
    eq(autumn[6], "3")
    eq(cells(row(p, "Phineas"))[4], "22.0K")
    eq(p.table.data[1].name, "Autumn", "most damage first")
    truthy(contains(Mock.texts(p), "In progress"))

    fight(30, { Autumn = { damage_done = 20000 } })
    eq(cells(row(p, "Autumn"))[2], "60.0K", "the whole run so far")
    eq(cells(row(p, "Autumn"))[3], "750")
    click(p.chips.fight)
    eq(cells(row(p, "Autumn"))[2], "20.0K", "the last fight alone")
    eq(cells(row(p, "Autumn"))[3], "667")
    click(p.chips.run)
    eq(cells(row(p, "Autumn"))[2], "60.0K")

    local r = row(p, "Autumn")
    r._scripts.OnEnter(r)
    truthy(contains(Mock.tooltip, "Avoidable damage taken"), "every stat is in the row's tooltip")
  end)

  it("sorts by the column clicked", function()
    local ft = boot()
    Mock.slash("records")
    Mock.enterDungeon({})
    fight(40, {
      Autumn = { damage_done = 30000 },
      Phineas = { healing_done = 50000 },
      Mah = { damage_done = 10000, damage_taken = 90000 },
    })
    local p = page(ft)
    eq(p.table.data[1].name, "Autumn")
    click(p.table.sortButtons.healing_done)
    eq(p.table.data[1].name, "Phineas")
    click(p.table.sortButtons.damage_taken)
    eq(p.table.data[1].name, "Mah")
  end)

  it("names the boss of the last fight and counts only its deaths", function()
    local ft = boot()
    Mock.slash("records")
    Mock.enterDungeon({})
    Mock.setDead("Mah", true)
    Mock.advance(2)
    Mock.setDead("Mah", false)
    Mock.advance(30)
    Mock.fire("ENCOUNTER_START", 3001, "Thane Gorrak", 1, 5)
    Mock.startCombat()
    Mock.advance(20)
    Mock.setDead("Phineas", true)
    Mock.advance(25)
    Mock.fire("ENCOUNTER_END", 3001, "Thane Gorrak", 1, 5, 1, {})
    Mock.endCombat(45, { Autumn = { damage_done = 45000 } })
    Mock.advance(12)

    local p = page(ft)
    click(p.chips.fight)
    truthy(contains(Mock.texts(p), "Last fight: Thane Gorrak (kill)"))
    eq(row(p, "Phineas").item.deaths, 1)
    eq(row(p, "Mah").item.deaths, 0, "Mah died before this fight")
    click(p.chips.run)
    eq(row(p, "Mah").item.deaths, 1)
  end)

  it("keeps showing the run after it ends", function()
    local ft = boot()
    Mock.slash("records")
    Mock.enterDungeon({ name = "Hall of Thanes" })
    fight(40, { Autumn = { damage_done = 32000 } })
    Mock.fire("LFG_COMPLETION_REWARD")
    Mock.leaveInstance()
    local frame = ft.RecordsUI.frame()
    falsy(page(ft):IsShown(), "after the run the window goes back to the overview")
    click(frame.tabs.scoreboard)
    local p = page(ft)
    truthy(p:IsShown())
    eq(cells(row(p, "Autumn"))[2], "32.0K")
    truthy(contains(Mock.texts(p), "Ended"))
    click(p.chips.fight)
    eq(cells(row(p, "Autumn"))[2], "32.0K", "the last fight is kept until a reload")

    ft = Mock.reload()
    ft.RecordsUI.show()
    click(ft.RecordsUI.frame().tabs.scoreboard)
    p = page(ft)
    eq(cells(row(p, "Autumn"))[2], "32.0K", "the whole run is saved")
    click(p.chips.fight)
    truthy(contains(Mock.texts(p), "kept until you reload"), "the last fight was not")
  end)

  -- What a live cell shows: the secret the client formatted, revealed for the test.
  local function shown(r, column)
    local text = r.cells[column]._text
    truthy(issecretvalue(text), "a live number reaches the screen still secret")
    return Mock.reveal(text)
  end

  it("follows the fight live, in each person's row, ranked by the meter", function()
    local ft = boot()
    Mock.slash("records")
    Mock.enterDungeon({})
    Mock.meter.namesVisible = true -- names readable in combat, only the numbers secret
    Mock.startCombat()
    Mock.combatProgress({
      Autumn = { damage_done = 12000, interrupts = 1 },
      Phineas = { healing_done = 8000 },
      Mah = { damage_done = 30000, damage_taken = 50000 },
    })
    Mock.advance(10)
    local p = page(ft)
    truthy(contains(Mock.texts(p), "Live: this fight"))
    local mah = row(p, "Mah")
    eq(shown(mah, 2), "30.0K", "Mah's damage so far")
    eq(shown(mah, 3), "3.0K", "and the meter's own DPS")
    eq(shown(mah, 8), "50.0K")
    eq(shown(row(p, "Phineas"), 4), "8.0K")
    eq(shown(row(p, "Autumn"), 6), "1")
    eq(p.table.data[1].name, "Mah", "in the meter's order, without comparing secrets")
    eq(cells(row(p, "Asha"))[2], "-", "nothing yet from Asha")

    Mock.combatProgress({ Autumn = { damage_done = 45000 }, Mah = { damage_done = 31000 } })
    Mock.advance(1)
    eq(p.table.data[1].name, "Autumn", "re-ranked as the fight goes")
    eq(shown(row(p, "Autumn"), 2), "45.0K")
    click(p.table.sortButtons.name)
    eq(p.table.data[1].name, "Asha", "any column still sorts")
    click(p.table.sortButtons.damage_done)

    local r = row(p, "Autumn")
    r._scripts.OnEnter(r)
    truthy(contains(Mock.tooltip, "numbers are on the board"), "no secret goes into the tooltip")

    -- The fight ends: the live numbers stay until the meter has been read, then the run's.
    Mock.endCombat(11, { Autumn = { damage_done = 45000 }, Mah = { damage_done = 31000 } }, { secretFor = 3 })
    Mock.advance(1)
    truthy(contains(Mock.texts(p), "Live: this fight"), "still live while the numbers are secret")
    Mock.advance(12)
    falsy(contains(Mock.texts(p), "Live: this fight"))
    eq(cells(row(p, "Autumn"))[2], "45.0K", "the whole run, read after the fight")
    eq(ft.capabilities.errors.records, nil, "no secret was ever compared or added")
  end)

  it("puts a nameless number in the right row by the player's own flag or a unique class", function()
    local party = DefaultParty()
    party[5].class = "MAGE" -- Thalen is a mage like Autumn
    local ft = boot(party)
    Mock.slash("records")
    Mock.enterDungeon({})
    Mock.startCombat()
    Mock.combatProgress({
      Autumn = { damage_done = 12000 },
      Mah = { damage_done = 30000 },
      Thalen = { damage_done = 20000 },
    })
    Mock.advance(2)
    local p = page(ft)
    eq(shown(row(p, "Autumn"), 2), "12.0K", "the player's own row")
    eq(shown(row(p, "Mah"), 2), "30.0K", "the only warrior")
    eq(cells(row(p, "Thalen"))[2], "-", "a second mage cannot be told apart")
    truthy(contains(Mock.texts(p), "hides some names"))
    Mock.endCombat(2, { Autumn = { damage_done = 12000 }, Mah = { damage_done = 30000 }, Thalen = { damage_done = 20000 } })
    Mock.advance(12)
    eq(cells(row(p, "Thalen"))[2], "20.0K", "it shows up once the fight is read")
    eq(ft.capabilities.errors.records, nil)
  end)

  it("shows a picked view instead of the live one until the next fight", function()
    local ft = boot()
    Mock.slash("records")
    Mock.enterDungeon({})
    fight(20, { Autumn = { damage_done = 10000 } })
    Mock.startCombat()
    Mock.combatProgress({ Autumn = { damage_done = 5000 } })
    Mock.advance(2)
    local p = page(ft)
    click(p.chips.run)
    eq(cells(row(p, "Autumn"))[2], "10.0K", "the run so far, mid-fight")
    Mock.advance(2)
    eq(cells(row(p, "Autumn"))[2], "10.0K", "and it stays")
    Mock.endCombat(4, { Autumn = { damage_done = 5000 } })
    Mock.advance(12)
    Mock.startCombat()
    Mock.advance(1)
    truthy(contains(Mock.texts(p), "Live: this fight"), "the next fight is live again")
  end)

  it("leaves out someone who only passed through", function()
    local ft = boot()
    Mock.slash("records")
    Mock.enterDungeon({})
    Mock.advance(20)
    Mock.removeMember("Thalen") -- left as the run began
    Mock.advance(20)
    fight(40, { Autumn = { damage_done = 30000 } })
    local names = {}
    for _, r in ipairs(page(ft).table.data) do
      names[r.name] = true
    end
    truthy(names.Mah)
    falsy(names.Thalen)
  end)
end)

describe("minimap button", function()
  it("follows the cursor around the minimap and remembers where it was left", function()
    local ft = boot()
    local button = ft.MinimapButton.button()
    Mock.cursor = { 900, 600 } -- straight left of the minimap's centre
    button._scripts.OnDragStart(button)
    button._scripts.OnUpdate(button)
    button._scripts.OnDragStop(button)
    eq(math.floor(ForeverTrackerDB.settings.minimap.angle + 0.5), 180)
    Mock.reload()
    eq(math.floor(ForeverTrackerDB.settings.minimap.angle + 0.5), 180)
  end)

  it("can be hidden with /ft minimap and stays hidden", function()
    local ft = boot()
    Mock.slash("minimap")
    falsy(ft.MinimapButton.button():IsShown())
    truthy(Mock.chatContains("minimap button hidden"))
    ft = Mock.reload()
    falsy(ft.MinimapButton.button():IsShown())
    Mock.slash("minimap")
    truthy(ft.MinimapButton.button():IsShown())
  end)

  it("has a tooltip, and the addon menu entry opens the records", function()
    local ft = boot()
    local button = ft.MinimapButton.button()
    button._scripts.OnEnter(button)
    truthy(contains(Mock.tooltip, "ForeverTracker"))
    truthy(contains(Mock.tooltip, "0 dungeon runs recorded"))
    Mock.enterDungeon({ name = "Hall of Thanes" })
    button._scripts.OnEnter(button)
    truthy(contains(Mock.tooltip, "Recording Hall of Thanes"))
    Mock.leaveInstance()
    button._scripts.OnEnter(button)
    truthy(contains(Mock.tooltip, "Paused: Hall of Thanes"))
    ForeverTracker_OnAddonCompartmentClick("ForeverTracker", "LeftButton")
    truthy(ft.RecordsUI.isShown())
  end)
end)
