local function deathsOf(run, name)
  local ref = member(run, name).ref
  local out = {}
  for _, d in ipairs(run.deaths) do
    if d.unit_ref == ref then
      out[#out + 1] = d
    end
  end
  return out
end

describe("party deaths", function()
  it("counts alive-to-dead transitions of party members", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(10)
    Mock.setDead("Mah", true)
    Mock.advance(2)
    local run = activeRun()
    local deaths = deathsOf(run, "Mah")
    eq(#deaths, 1)
    eq(deaths[1].source, "unit_state")
    eq(run.collection.deaths_unit_state, "active")
  end)

  it("does not count a ghost twice, but counts a second death after resurrection", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(5)
    Mock.setDead("Asha", true)
    Mock.advance(30)
    Mock.unitByName("Asha").ghost = true
    Mock.advance(30)
    eq(#deathsOf(activeRun(), "Asha"), 1)
    Mock.unitByName("Asha").ghost = false
    Mock.setDead("Asha", false)
    Mock.advance(20)
    Mock.setDead("Asha", true)
    Mock.advance(2)
    eq(#deathsOf(activeRun(), "Asha"), 2)
  end)

  it("ignores Feign Death", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(5)
    local hunter = Mock.unitByName("Thalen")
    hunter.dead, hunter.feign = true, true
    Mock.advance(3)
    eq(#deathsOf(activeRun(), "Thalen"), 0)
  end)

  it("does not count someone already dead when tracking starts", function()
    local party = DefaultParty()
    party[3].dead = true
    boot(party)
    Mock.enterDungeon({})
    Mock.advance(5)
    eq(#deathsOf(activeRun(), "Phineas"), 0)
  end)

  it("deduplicates PLAYER_DEAD with the unit-state transition", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(5)
    Mock.setDead("Autumn", true) -- fires UNIT_FLAGS and PLAYER_DEAD
    Mock.advance(2)
    eq(#deathsOf(activeRun(), "Autumn"), 1)
  end)

  it("records the encounter a death happened in", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(5)
    Mock.fire("ENCOUNTER_START", 3002, "Boss", 1, 5)
    Mock.advance(20)
    Mock.setDead("Mah", true)
    Mock.advance(1)
    eq(deathsOf(activeRun(), "Mah")[1].encounter_id, 3002)
  end)

  it("does not double count after /reload while someone is dead", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(5)
    Mock.setDead("Mah", true)
    Mock.advance(2)
    Mock.reload()
    Mock.advance(5)
    eq(#deathsOf(activeRun(), "Mah"), 1)
  end)

  it("reports partial coverage when death state is secret", function()
    boot()
    Mock.enterDungeon({})
    local original = UnitIsDeadOrGhost
    UnitIsDeadOrGhost = function(u)
      if u == "party2" then
        return Mock.secret(true)
      end
      return original(u)
    end
    Mock.advance(3)
    eq(activeRun().deaths[1], nil)
    Mock.leaveInstance()
    Mock.advance(901)
    eq(lastObservation("dungeon_run").collection.deaths_unit_state, "partial")
  end)
end)
