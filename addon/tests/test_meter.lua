local function fight(duration, values, opts)
  Mock.startCombat()
  Mock.advance(duration)
  local id = Mock.endCombat(duration, values, opts)
  Mock.advance(12) -- capture retries run after combat
  return id
end

local function totals(run, name)
  local ref = member(run, name).ref
  for _, t in ipairs(run.meter.totals) do
    if t.unit_ref == ref then
      return t.metrics
    end
  end
end

describe("native damage meter", function()
  it("captures sessions after combat and sums them per party member", function()
    boot()
    Mock.enterDungeon({})
    fight(30, { Autumn = { damage_done = 9000, interrupts = 1 }, Mah = { damage_done = 4000 }, Phineas = { healing_done = 7000 } })
    fight(45, { Autumn = { damage_done = 12000 }, Mah = { damage_done = 6000, interrupts = 2 }, Phineas = { healing_done = 9000 } })
    local run = activeRun()
    eq(run.meter.status, "observed")
    eq(#run.meter.sessions, 2)
    eq(run.meter.combat_seconds, 75)
    local mage = totals(run, "Autumn")
    eq(mage.damage_done.value, 21000)
    eq(mage.damage_done.status, "observed")
    eq(mage.damage_done.sessions, 2)
    eq(totals(run, "Mah").interrupts.value, 2)
    eq(totals(run, "Phineas").healing_done.value, 16000)
    eq(totals(run, "Asha").damage_done.value, 0, "a member absent from every source did no damage")
    eq(run.collection.meter, "active")
  end)

  it("excludes sessions that existed before the run", function()
    boot()
    Mock.startCombat()
    Mock.endCombat(20, { Autumn = { damage_done = 99999 } })
    Mock.enterDungeon({})
    fight(30, { Autumn = { damage_done = 100 } })
    eq(totals(activeRun(), "Autumn").damage_done.value, 100)
  end)

  it("retries while values are still secret after combat", function()
    boot()
    Mock.enterDungeon({})
    fight(30, { Autumn = { damage_done = 500 } }, { secretFor = 1.5 })
    local run = activeRun()
    eq(run.meter.sessions[1].status, "captured")
    eq(totals(run, "Autumn").damage_done.value, 500)
  end)

  it("never invents numbers when the meter stays secret", function()
    boot()
    Mock.enterDungeon({})
    fight(30, { Autumn = { damage_done = 500 } }, { secretFor = 3600 })
    local run = activeRun()
    eq(run.meter.status, "secret")
    eq(run.meter.sessions[1].status, "secret")
    local m = totals(run, "Autumn").damage_done
    eq(m.value, nil)
    eq(m.status, "secret")
  end)

  it("marks partial coverage when only some sessions were readable", function()
    boot()
    Mock.enterDungeon({})
    fight(30, { Autumn = { damage_done = 500 } })
    fight(30, { Autumn = { damage_done = 700 } }, { secretFor = 3600 })
    local run = activeRun()
    eq(run.meter.status, "partial")
    local m = totals(run, "Autumn").damage_done
    eq(m.value, 500)
    eq(m.status, "partial")
  end)

  it("excludes combat that happens outside the instance during a corpse run", function()
    boot()
    Mock.enterDungeon({})
    fight(30, { Autumn = { damage_done = 500 } })
    Mock.leaveInstance()
    fight(10, { Autumn = { damage_done = 50000 } })
    Mock.enterDungeon({})
    fight(30, { Autumn = { damage_done = 600 } })
    eq(totals(activeRun(), "Autumn").damage_done.value, 1100)
  end)

  it("records death entries from the Deaths meter type", function()
    boot()
    Mock.enterDungeon({})
    fight(30, { Mah = { damage_done = 10, deaths = 2 } })
    local run = activeRun()
    eq(#run.meter.death_entries, 2)
    eq(run.meter.death_entries[1].unit_ref, member(run, "Mah").ref)
    eq(totals(run, "Mah").deaths.value, 2)
  end)

  it("handles an unavailable meter without numbers", function()
    Mock.meter.available, Mock.meter.reason = false, "Damage meter is disabled"
    boot()
    Mock.enterDungeon({})
    fight(30, { Autumn = { damage_done = 500 } })
    local run = activeRun()
    eq(run.meter.status, "unavailable")
    eq(run.meter.reason, "Damage meter is disabled")
    eq(#run.meter.totals, 0)
    eq(run.collection.meter, "unavailable")
  end)

  it("respects the disabled collector flag", function()
    local ft = boot()
    ft.Config.set("meter", false)
    Mock.enterDungeon({})
    fight(30, { Autumn = { damage_done = 500 } })
    eq(activeRun().meter.status, "disabled")
  end)

  it("treats a secret session table as secret", function()
    boot()
    Mock.enterDungeon({})
    local get = C_DamageMeter.GetCombatSessionFromID
    C_DamageMeter.GetCombatSessionFromID = function()
      return Mock.secretTable()
    end
    fight(30, { Autumn = { damage_done = 500 } })
    eq(activeRun().meter.sessions[1].status, "secret")
    C_DamageMeter.GetCombatSessionFromID = get
  end)

  it("reports a run without any combat as having no meter data", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(60)
    Mock.fire("LFG_COMPLETION_REWARD")
    Mock.leaveInstance()
    local run = lastObservation("dungeon_run")
    eq(run.meter.status, "unavailable")
    eq(run.meter.reason, "no_sessions_observed")
  end)
end)

describe("damage meter per boss fight", function()
  local function attempt(run, name, n)
    local seen = 0
    for _, e in ipairs(run.encounters) do
      if e.name == name then
        seen = seen + 1
        if seen == (n or 1) then
          return e
        end
      end
    end
  end

  local function value(e, name, metric)
    local ref = member(activeRun() or lastObservation("dungeon_run"), name).ref
    for _, t in ipairs(e.meter.totals) do
      if t.unit_ref == ref then
        return t.metrics[metric]
      end
    end
  end

  it("gives each boss attempt the totals of the fight it overlaps", function()
    boot()
    Mock.enterDungeon({ name = "Deadmines", mapId = 36 })
    fight(25, { Autumn = { damage_done = 1000 } }) -- trash just before the boss
    Mock.fire("ENCOUNTER_START", 2741, "Rhahk'Zor", 1, 5)
    Mock.startCombat()
    Mock.advance(80)
    Mock.fire("ENCOUNTER_END", 2741, "Rhahk'Zor", 1, 5, 1, {})
    Mock.endCombat(80, { Autumn = { damage_done = 9000, interrupts = 2 }, Phineas = { healing_done = 6000 } })
    Mock.advance(12)
    fight(30, { Autumn = { damage_done = 1500 } }) -- trash after

    local run = activeRun()
    local boss = attempt(run, "Rhahk'Zor")
    eq(boss.meter.status, "observed")
    eq(boss.meter.sessions, 1)
    eq(boss.meter.combat_seconds, 80)
    eq(value(boss, "Autumn", "damage_done"), 9000, "neither trash pull is counted")
    eq(value(boss, "Autumn", "interrupts"), 2)
    eq(value(boss, "Phineas", "healing_done"), 6000)
    eq(value(boss, "Mah", "damage_done"), 0)
    local tagged = {}
    for _, s in ipairs(run.meter.sessions) do
      tagged[#tagged + 1] = s.encounter_id or 0
    end
    eq(table.concat(tagged, ","), "0,2741,0")
  end)

  it("keeps a boss pulled straight from trash, and a fight the player died in", function()
    boot()
    Mock.enterDungeon({ name = "Deadmines", mapId = 36 })
    -- Greenskin: combat starts on trash and runs into the boss (a 71s session for a 54s fight).
    Mock.startCombat()
    Mock.advance(17)
    Mock.fire("ENCOUNTER_START", 2744, "Captain Greenskin", 1, 5)
    Mock.advance(54)
    Mock.fire("ENCOUNTER_END", 2744, "Captain Greenskin", 1, 5, 1, {})
    Mock.endCombat(71, { Autumn = { damage_done = 7000 } })
    Mock.advance(60)
    -- VanCleef: the player dies 20s in; the group kills him 25s later.
    Mock.fire("ENCOUNTER_START", 2747, "Edwin VanCleef", 1, 5)
    Mock.startCombat()
    Mock.advance(20)
    Mock.setDead("Autumn", true)
    Mock.endCombat(20, { Autumn = { damage_done = 3000 } })
    Mock.advance(25)
    Mock.fire("ENCOUNTER_END", 2747, "Edwin VanCleef", 1, 5, 1, {})
    Mock.advance(12)

    local run = activeRun()
    eq(value(attempt(run, "Captain Greenskin"), "Autumn", "damage_done"), 7000)
    local vancleef = attempt(run, "Edwin VanCleef")
    eq(value(vancleef, "Autumn", "damage_done"), 3000)
    eq(vancleef.meter.status, "partial", "the player died, so the rest of the fight is missing")
    truthy(vancleef.meter.observer_died)
  end)

  it("keeps a wipe and the kill as separate attempts", function()
    boot()
    Mock.enterDungeon({})
    for _, kill in ipairs({ false, true }) do
      Mock.fire("ENCOUNTER_START", 3001, "Thane Gorrak", 1, 5)
      Mock.startCombat()
      Mock.advance(40)
      Mock.fire("ENCOUNTER_END", 3001, "Thane Gorrak", 1, 5, kill and 1 or 0, {})
      Mock.endCombat(40, { Autumn = { damage_done = kill and 8000 or 2000 } })
      Mock.advance(120)
    end
    local run = activeRun()
    eq(value(attempt(run, "Thane Gorrak", 1), "Autumn", "damage_done"), 2000)
    eq(value(attempt(run, "Thane Gorrak", 2), "Autumn", "damage_done"), 8000)
  end)

  it("leaves a boss without meter data when no session overlaps it", function()
    boot()
    Mock.enterDungeon({})
    Mock.fire("ENCOUNTER_START", 3001, "Thane Gorrak", 1, 5)
    Mock.advance(30)
    Mock.fire("ENCOUNTER_END", 3001, "Thane Gorrak", 1, 5, 1, {})
    Mock.advance(120)
    fight(20, { Autumn = { damage_done = 500 } })
    eq(attempt(activeRun(), "Thane Gorrak").meter, nil)
  end)
end)
