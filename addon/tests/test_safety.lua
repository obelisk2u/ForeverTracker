describe("unsupported or restricted APIs", function()
  it("loads when events are unknown to the client", function()
    Mock.validEvents.ENCOUNTER_START = nil
    Mock.validEvents.UNIT_DIED = nil
    Mock.validEvents.DAMAGE_METER_RESET = nil
    local ft = boot()
    eq(ft.capabilities.events.ENCOUNTER_START, false)
    Mock.enterDungeon({})
    eq(activeRun().collection.encounters, "unavailable")
  end)

  it("survives missing namespaces and functions", function()
    Mock.withoutApis({ "C_DamageMeter", "UnitNameUnmodified", "NotifyInspect", "C_EventUtils", "issecretvalue", "C_Traits", "GetServerTime" })
    local ft = boot()
    Mock.enterDungeon({})
    local run = activeRun()
    truthy(run, "a run is still recorded")
    eq(run.meter.status, "unavailable")
    eq(run.meter.reason, "api_missing")
    eq(member(run, "Autumn").surname, "Redleaf", "UnitName is the fallback")
    Mock.slash("probe")
    local probe = lastObservation("probe_report")
    truthy(probe)
    local failed = {}
    for _, r in ipairs(probe.results) do
      failed[r.check] = r.status
    end
    eq(failed["api.C_EventUtils.IsEventValid"], "fail")
    eq(failed["meter.available"], "fail")
  end)

  it("records secret identities as secret instead of guessing", function()
    local party = DefaultParty()
    party[4].secret = { name = true, guid = true }
    boot(party)
    Mock.enterDungeon({})
    local run = activeRun()
    eq(#run.roster, 4, "an unidentifiable unit has no stable key")
    eq(ForeverTrackerDB.active_state.unidentified, 1)
  end)

  it("keeps a member whose GUID is secret but name is readable", function()
    local party = DefaultParty()
    party[2].secret = { guid = true }
    boot(party)
    Mock.enterDungeon({})
    local m = member(activeRun(), "Mah")
    eq(m.guid, nil)
    eq(m.identity_status, "secret")
  end)

  it("switches off a collector that keeps failing", function()
    local ft = boot()
    Mock.enterDungeon({})
    UnitIsDeadOrGhost = function()
      error("boom")
    end
    ft.Safe.call = function(path, ...)
      if path == "UnitIsDeadOrGhost" then
        error("collector failure")
      end
      local fn = ft.Safe.api(path)
      if not fn then
        return false, "missing"
      end
      return pcall(fn, ...)
    end
    Mock.advance(40)
    truthy(ft.disabledThisSession.runtracker or ft.disabledThisSession.deaths_unit_state, "failing collector disabled")
  end)

  it("never resets the player's meter", function()
    boot()
    Mock.enterDungeon({})
    Mock.startCombat()
    Mock.endCombat(10, { Autumn = { damage_done = 1 } })
    Mock.advance(20)
    Mock.leaveInstance()
    Mock.advance(901)
    truthy(lastObservation("dungeon_run")) -- C_DamageMeter.ResetAllCombatSessions raises in the mock
  end)
end)
