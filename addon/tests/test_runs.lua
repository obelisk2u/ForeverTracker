describe("roster capture", function()
  it("records the whole party from one installation", function()
    boot()
    Mock.enterDungeon({ name = "Hall of Thanes", mapId = 990001 })
    local run = activeRun()
    eq(run.type, "dungeon_run")
    eq(run.state, "in_progress")
    eq(#run.roster, 5)
    local me = member(run, "Autumn")
    eq(me.surname, "Redleaf", "second UnitName value is a surname on Forever")
    eq(me.guid, "Player-4620-0000A1")
    truthy(me.is_observer)
    eq(member(run, "Mah").role, "TANK")
    eq(member(run, "Mah").class_file, "WARRIOR")
    falsy(member(run, "Mah").is_observer)
    eq(run.instance.map_id, 990001)
    eq(run.instance.name, "Hall of Thanes")
    eq(run.namespace.region_id, 1)
    eq(run.namespace.ruleset, "pve")
    eq(run.realm_label, "70")
    eq(run.recorded_by.name, "Autumn")
    eq(#member(run, "Asha").presence, 1)
  end)

  it("does not read the second name value as a surname when names are not regional", function()
    Mock.regionalNames = false
    Mock.setParty(DefaultParty())
    Mock.loadAddon(nil)
    Mock.fire("PLAYER_ENTERING_WORLD", true, false)
    Mock.enterDungeon({})
    local run = activeRun()
    eq(member(run, "Autumn").surname, nil)
    truthy(run.flags.non_regional_names)
    eq(run.namespace.ruleset, "unknown")
  end)

  it("derives the ruleset namespace from game rules", function()
    Mock.rules[101] = true
    boot()
    Mock.enterDungeon({})
    eq(activeRun().namespace.ruleset, "hardcore")
  end)

  it("tracks members leaving and joining", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(60)
    Mock.removeMember("Thalen")
    Mock.advance(1)
    local run = activeRun()
    truthy(member(run, "Thalen").presence[1]["end"], "presence interval closed")
    local party = DefaultParty()
    table.remove(party, 5)
    party[5] = { name = "Kira", surname = "Stonefist", guid = "Player-4620-0000B1", class = "PALADIN", race = "Dwarf", level = 18, role = "DAMAGER" }
    Mock.setParty(party)
    Mock.advance(1)
    eq(#run.roster, 6)
    eq(member(run, "Kira").ref, "u6")
    local changes = 0
    for _, e in ipairs(run.timeline) do
      if e.kind == "roster_changed" then
        changes = changes + 1
      end
    end
    eq(changes, 2)
  end)
end)

describe("run state machine", function()
  it("never treats leaving the instance as completion", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(600)
    Mock.leaveInstance()
    eq(activeRun().timeline[#activeRun().timeline].kind, "left_instance")
    Mock.advance(901)
    local run = lastObservation("dungeon_run")
    eq(run.state, "left")
    eq(run.completion.status, "none")
    eq(activeRun(), nil)
    truthy(run.timing.ended_at <= run.timing.started_at + 601)
  end)

  it("resumes the same run after a corpse run back into the dungeon", function()
    boot()
    Mock.enterDungeon({})
    local id = activeRun().observation_id
    Mock.advance(300)
    Mock.leaveInstance()
    Mock.advance(120)
    Mock.enterDungeon({})
    local run = activeRun()
    eq(run.observation_id, id)
    eq(run.timeline[#run.timeline].kind, "reentered")
    eq(#member(run, "Autumn").presence, 2, "presence split around the corpse run")
    eq(#observationsOf("dungeon_run"), 0, "still one open run, nothing finalized")
  end)

  it("marks completion only from a completion event", function()
    boot()
    Mock.enterDungeon({})
    Mock.fire("ENCOUNTER_START", 3001, "Boss", 1, 5)
    Mock.advance(90)
    Mock.fire("ENCOUNTER_END", 3001, "Boss", 1, 5, 1, {})
    Mock.advance(30)
    eq(activeRun().state, "in_progress", "a boss kill alone is not completion")
    Mock.fire("LFG_COMPLETION_REWARD")
    Mock.advance(10)
    Mock.leaveInstance()
    local run = lastObservation("dungeon_run")
    eq(run.state, "completed")
    eq(run.completion.status, "verified")
    eq(run.completion.evidence[1].kind, "lfg_completion_reward")
    eq(run.encounters[1].success, true)
    eq(run.encounters[1].ended_at - run.encounters[1].started_at, 90)
  end)

  it("records an abandon vote", function()
    boot()
    Mock.enterDungeon({})
    Mock.fire("INSTANCE_ABANDON_VOTE_FINISHED", true)
    Mock.leaveInstance()
    eq(lastObservation("dungeon_run").state, "abandoned")
  end)

  it("resumes after /reload with a newer revision and the same id", function()
    boot()
    Mock.enterDungeon({})
    local id = activeRun().observation_id
    Mock.advance(100)
    Mock.reload()
    local run = activeRun()
    eq(run.observation_id, id)
    truthy(run.revision >= 2, "revision bumped when the file was written")
    truthy(run.flags.resumed_after_reload)
    eq(Mock.saved.active_run.state, "in_progress", "the saved file holds the in-progress record")
    eq(#run.roster, 5)
  end)

  it("finishes as disconnected when the session ends inside and the player does not return", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(200)
    Mock.logout(3600)
    Mock.instance = { inInstance = false, type = "none" }
    Mock.login()
    local run = lastObservation("dungeon_run")
    eq(run.state, "disconnected")
    eq(activeRun(), nil)
  end)

  it("resumes after a quick relog inside the dungeon", function()
    boot()
    Mock.enterDungeon({})
    local id = activeRun().observation_id
    Mock.advance(200)
    Mock.logout(60)
    Mock.login()
    eq(activeRun().observation_id, id)
    truthy(activeRun().flags.resumed_after_login)
  end)

  it("loses only what happened after the last save when the client crashes", function()
    -- The client writes SavedVariables only after PLAYER_LOGOUT (logout, exit, /reload). A crash
    -- after a /reload therefore looks, on disk, exactly like a logout at that /reload.
    boot()
    Mock.enterDungeon({})
    Mock.advance(100)
    Mock.reload()
    Mock.advance(10)
    Mock.setDead("Mah", true) -- recorded in memory only...
    Mock.advance(30)
    Mock.setDead("Mah", false) -- ...and resurrected before the crash
    Mock.advance(470)
    Mock.crash(30)
    Mock.login()
    local run = activeRun()
    truthy(run, "the run resumes from the last saved copy")
    truthy(run.flags.resumed_after_login)
    eq(#run.deaths, 0, "the death after the last save was lost with the crash")
  end)

  it("re-detects a death that happened after the last save if the unit is still dead", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(100)
    Mock.reload()
    Mock.setDead("Mah", true)
    Mock.advance(60)
    Mock.crash(30)
    Mock.login()
    eq(#activeRun().deaths, 1, "alive in the saved state, dead now: counted once (timestamped at login)")
  end)

  it("finishes the previous run when a different dungeon is entered", function()
    boot()
    Mock.enterDungeon({ mapId = 990001 })
    Mock.advance(100)
    Mock.leaveInstance()
    Mock.advance(60)
    Mock.enterDungeon({ mapId = 990002, name = "Ruins of Lordaeron" })
    eq(lastObservation("dungeon_run").state, "left")
    eq(activeRun().instance.map_id, 990002)
  end)

  it("ignores raids and the open world", function()
    boot()
    Mock.enterDungeon({ type = "raid", maxPlayers = 40 })
    eq(activeRun(), nil)
  end)
end)

describe("storage", function()
  it("keeps a bounded ring buffer", function()
    local ft = boot()
    ft.Config.LIMITS.max_observations = 3
    for i = 1, 5 do
      ft.Storage.push({ type = "probe_report", observation_id = "p-" .. i, revision = 1 })
    end
    eq(#ForeverTrackerDB.observations, 3)
    eq(ForeverTrackerDB.observations[1].observation_id, "p-3")
    truthy(ForeverTrackerDB.dropped.observations >= 2)
  end)

  it("creates an installation id once and keeps it", function()
    boot()
    local id = ForeverTrackerDB.installation_id
    truthy(string.match(id, "^ft%-%x+$"))
    Mock.reload()
    eq(ForeverTrackerDB.installation_id, id)
    eq(ForeverTrackerDB.load_count, 2)
  end)

  -- Deep equality for plain data tables.
  local function same(a, b, path)
    path = path or "ForeverTrackerDB"
    if type(a) ~= "table" or type(b) ~= "table" then
      eq(a, b, path)
      return
    end
    for k, v in pairs(a) do
      same(v, b[k], path .. "." .. tostring(k))
    end
    for k in pairs(b) do
      truthy(a[k] ~= nil, path .. "." .. tostring(k) .. " was added")
    end
  end

  local function futureData(version)
    return {
      format = "forevertracker.savedvariables", schema_version = version, installation_id = "ft-future-00000001",
      load_count = 7, observations = { { type = "dungeon_run", observation_id = "r-1", revision = 3, future_field = { 1, 2 } } },
      settings = { collectors = { meter = false } }, unknown_section = { kept = true },
    }
  end

  it("leaves data written by a newer schema intact through a session and logout", function()
    local original = futureData(2)
    local ft = boot(nil, { saved = Mock.deepcopy(original) })
    truthy(ft.readOnly, "read-only session")
    truthy(Mock.chatContains("written by a newer version of ForeverTracker (data format 2"), "the player is told why")
    -- A whole dungeon run, then logout: the client writes ForeverTrackerDB back as it is.
    Mock.enterDungeon({ name = "Hall of Thanes", mapId = 990001 })
    Mock.startCombat()
    Mock.advance(30)
    Mock.endCombat(30, { Autumn = { damage_done = 1000 } })
    Mock.advance(15)
    Mock.leaveInstance()
    Mock.advance(5)
    Mock.fire("GROUP_ROSTER_UPDATE")
    Mock.advance(5)
    local written = Mock.saveVariables()
    same(written, original)
    eq(ft.Storage.activeRun(), nil, "nothing was recorded")
  end)

  it("treats a missing or non-numeric schema version as newer and keeps the data", function()
    for _, version in ipairs({ "two", false }) do
      Mock.reset()
      local original = futureData(version)
      if version == false then
        original.schema_version = nil
      end
      local ft = boot(nil, { saved = Mock.deepcopy(original) })
      truthy(ft.readOnly, "read-only for " .. tostring(version))
      same(Mock.saveVariables(), original)
    end
  end)

  it("says the session is read-only in /ft status", function()
    boot(nil, { saved = futureData(5) })
    Mock.chat = {}
    SlashCmdList.FOREVERTRACKER("status")
    truthy(Mock.chatContains("nothing is recorded or saved this session"))
  end)
end)

describe("raids", function()
  it("does not record a raid as a dungeon run", function()
    boot()
    Mock.enterDungeon({ type = "raid", name = "Onyxia's Lair", mapId = 249, maxPlayers = 40 })
    eq(activeRun(), nil)
    Mock.leaveInstance()
    eq(#observationsOf("dungeon_run"), 0)
  end)

  it("keeps the instance type the client reports", function()
    local ft = boot()
    local obs = ft.Instance.toObservation({ in_instance = true, instance_type = "raid", map_id = 249, max_players = 40 })
    eq(obs.instance_type, "raid", "never stored as a 5-player dungeon")
    eq(obs.max_players, 40)
    eq(ft.Instance.toObservation({ in_instance = true, instance_type = "party", map_id = 2970 }).instance_type, "party")
  end)
end)
