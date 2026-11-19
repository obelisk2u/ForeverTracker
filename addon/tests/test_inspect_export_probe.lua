describe("equipment snapshots", function()
  it("takes a self snapshot with parsed item links", function()
    Mock.itemLevels[1016] = 24
    boot()
    local snap
    for _, s in ipairs(observationsOf("character_snapshot")) do
      if s.source == "self" then
        snap = s
      end
    end
    truthy(snap, "snapshot on entering the world")
    eq(snap.subject.name, "Autumn")
    eq(snap.subject.surname, "Redleaf")
    eq(snap.equipment.average_item_level, 20)
    local weapon
    for _, item in ipairs(snap.equipment.items) do
      if item.slot == 16 then
        weapon = item
      end
    end
    eq(weapon.item_id, 1016)
    eq(weapon.enchant_id, 33)
    eq(weapon.item_level, 24)
    eq(snap.talents.status, "disabled", "talent collection ships disabled")
  end)

  it("inspects party members out of combat, one at a time", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(60)
    local inspected = observationsOf("character_snapshot")
    local sources = {}
    for _, s in ipairs(inspected) do
      sources[s.subject.name] = s.source
    end
    eq(sources.Mah, "inspect")
    eq(sources.Thalen, "inspect")
    eq(Mock.inspectRequests, 4)
  end)

  it("does not inspect in combat or while the Inspect window is open", function()
    boot()
    Mock.combat = true
    Mock.enterDungeon({})
    Mock.advance(30)
    eq(Mock.inspectRequests, nil)
    Mock.combat = false
    Mock.inspectFrameShown = true
    Mock.advance(30)
    eq(Mock.inspectRequests, nil)
  end)

  it("skips unchanged snapshots", function()
    local ft = boot()
    local before = #observationsOf("character_snapshot")
    ft.Inspect.selfSnapshot(true)
    eq(#observationsOf("character_snapshot"), before)
    Mock.unitByName("Autumn").gear[1] = { id = 9999 }
    ft.Inspect.selfSnapshot(true)
    eq(#observationsOf("character_snapshot"), before + 1)
  end)

  it("captures talents only when enabled", function()
    local ft = boot()
    ft.Config.set("talents", true)
    Mock.unitByName("Autumn").gear[2] = { id = 1234 }
    local snap = ft.Inspect.selfSnapshot(true)
    eq(snap.talents.status, "observed")
    eq(snap.talents.import_string, "CAQAAAAAAAAA")
  end)
end)

describe("export string", function()
  it("encodes the stored records as deterministic JSON", function()
    local ft = boot()
    Mock.enterDungeon({})
    local revision = activeRun().revision
    local text = ft.Export.string(false)
    truthy(string.find(text, '"format":"forevertracker.savedvariables"', 1, true))
    truthy(string.find(text, '"installation_id":"ft-', 1, true))
    truthy(string.find(text, '"active_run":{', 1, true))
    eq(activeRun().revision, revision + 1, "export bumps the in-progress revision")
    eq(ft.Json.encode({ b = 1, a = { 1, 2 }, c = {} }), '{"a":[1,2],"b":1,"c":[]}')
    eq(ft.Json.encode({ x = 0 / 0, s = 'q"\n' }), '{"s":"q\\"\\n","x":null}')
  end)

  it("opens the export window from the slash command", function()
    boot()
    Mock.slash("export")
    truthy(ForeverTrackerExportFrame and ForeverTrackerExportFrame:IsShown())
  end)
end)

describe("probe mode", function()
  it("reports capabilities and stores an uploadable report", function()
    boot()
    Mock.enterDungeon({})
    Mock.startCombat()
    Mock.endCombat(10, { Autumn = { damage_done = 100 } })
    Mock.advance(12)
    Mock.slash("probe")
    local probe = lastObservation("probe_report")
    local status = {}
    for _, r in ipairs(probe.results) do
      status[r.check] = r
    end
    eq(status["client.build"].status, "pass")
    eq(status["names.regional"].status, "pass")
    eq(status["identity.player"].status, "pass")
    eq(status["identity.party"].status, "pass")
    eq(status["meter.available"].status, "pass")
    eq(status["meter.read"].status, "pass")
    eq(status["api.CombatLogGetCurrentEventInfo"].status, "info")
    truthy(Mock.chatContains("probe:"))
  end)

  it("runs the two-step persistence test", function()
    boot()
    Mock.slash("probe persist")
    truthy(Mock.chatContains("written"))
    Mock.reload()
    Mock.chat = {}
    Mock.slash("probe persist")
    truthy(Mock.chatContains("PASS"))
  end)

  it("does not crash on an unknown command", function()
    boot()
    Mock.slash("frobnicate")
    truthy(Mock.chatContains("unknown command"))
  end)
end)

describe("item details", function()
  local function selfSnapshots()
    local out = {}
    for _, s in ipairs(observationsOf("character_snapshot")) do
      if s.source == "self" then
        out[#out + 1] = s
      end
    end
    return out
  end

  local function setUnloaded(party)
    for _, item in pairs(party[1].gear) do
      item.unloaded = true
      item.name = "Loaded Name"
    end
    return party
  end

  it("reads enchants and gems from where real links keep them", function()
    local ft = boot()
    -- Copied from a live Forever client (build 70862): no enchant, no gems, level 18 at field 9.
    local real = ft.Inspect.parseLink("|cnIQ2:|Hitem:2985::::::::18:1484::1::1:28:5240:::::|h[Inscribed Leather Breastplate]|h|r")
    eq(real.item_id, 2985)
    eq(real.enchant_id, nil)
    eq(#real.gem_ids, 0)
    local enchanted = ft.Inspect.parseLink("|cnIQ3:|Hitem:1016:33::2001:::::20:::::|h[Sword]|h|r")
    eq(enchanted.enchant_id, 33)
    eq(enchanted.gem_ids[1], 2001)
  end)

  it("waits for the player's items to load before recording them", function()
    boot(setUnloaded(DefaultParty()))
    eq(#selfSnapshots(), 0, "no snapshot of nameless items at login")
    truthy(Mock.itemLoadRequests > 0, "the items were requested")
    Mock.advance(6)
    local snap = selfSnapshots()[1]
    truthy(snap, "recorded once the items loaded")
    for _, item in ipairs(snap.equipment.items) do
      truthy(string.find(item.link, "[Loaded Name]", 1, true), item.link)
    end
  end)

  it("replaces a snapshot taken before the items loaded with a complete one", function()
    local party = setUnloaded(DefaultParty())
    local request = C_Item.RequestLoadItemDataByID
    C_Item.RequestLoadItemDataByID = function() end -- the client never answers
    local ft = boot(party)
    Mock.advance(20)
    C_Item.RequestLoadItemDataByID = request
    eq(#selfSnapshots(), 1, "recorded anyway after the last retry")
    truthy(string.find(selfSnapshots()[1].equipment.items[1].link, "[]", 1, true), "without names")
    for _, item in pairs(party[1].gear) do
      Mock.loadedItems[item.id] = true
    end
    ft.Inspect.selfSnapshot(true)
    eq(#selfSnapshots(), 2, "the same gear, now with names, is recorded again")
  end)

  it("records each item's tooltip as the game shows it", function()
    boot()
    Mock.enterDungeon({})
    Mock.advance(60)
    local snap
    for _, s in ipairs(observationsOf("character_snapshot")) do
      if s.subject.name == "Mah" then
        snap = s
      end
    end
    local lines = snap.equipment.items[1].tooltip
    eq(#lines, 5, "everything but the sell price")
    eq(lines[1].left, "Item")
    eq(lines[1].color, "0070dd")
    eq(lines[2].color, nil, "white is the default")
    eq(lines[3].left, "Head")
    eq(lines[3].right, "Plate")
    eq(lines[5].color, "00ff00")
  end)

  it("records an item's tooltip once, not in every snapshot", function()
    local ft = boot()
    local first = selfSnapshots()[1]
    for _, item in ipairs(first.equipment.items) do
      truthy(item.tooltip, "slot " .. item.slot)
    end
    local reads = Mock.tooltipReads
    Mock.unitByName("Autumn").gear[1] = { id = 9999, name = "New Helm" }
    ft.Inspect.selfSnapshot(true)
    local second = selfSnapshots()[2]
    truthy(second, "new gear is recorded")
    for _, item in ipairs(second.equipment.items) do
      if item.item_id == 9999 then
        eq(item.tooltip[1].left, "New Helm")
      else
        eq(item.tooltip, nil, "already recorded: slot " .. item.slot)
      end
    end
    eq(Mock.tooltipReads, reads + 1, "only the new item's tooltip is read")
  end)

  it("records gear without tooltips when the client has none to give", function()
    Mock.withoutApis({ "C_TooltipInfo" })
    boot()
    local snap = selfSnapshots()[1]
    truthy(snap, "the snapshot is still taken")
    eq(snap.equipment.items[1].tooltip, nil)
    eq(snap.equipment.items[1].item_id, 1001)
  end)

  it("records unchanged gear again once to add the tooltips an earlier version did not record", function()
    -- Without tooltips the signature is the one earlier versions stored.
    local tooltips = C_TooltipInfo
    Mock.withoutApis({ "C_TooltipInfo" })
    local ft = boot()
    eq(#selfSnapshots(), 1)
    eq(ForeverTrackerDB.snapshot_sigs["g:Player-4620-0000A1"], "1:1001:nil,5:1005:nil,16:1016:33|18", "what 0.2.12 stored")
    ft.Inspect.selfSnapshot(true)
    eq(#selfSnapshots(), 1, "unchanged")
    _G.C_TooltipInfo = tooltips
    ft.Inspect.selfSnapshot(true)
    eq(#selfSnapshots(), 2, "the same gear, now with tooltips")
    truthy(selfSnapshots()[2].equipment.items[1].tooltip)
    ft.Inspect.selfSnapshot(true)
    eq(#selfSnapshots(), 2, "and only once")
  end)

  it("reads no tooltip from an item that is still loading, and records it once it has", function()
    local party = setUnloaded(DefaultParty())
    local request = C_Item.RequestLoadItemDataByID
    C_Item.RequestLoadItemDataByID = function() end -- the client never answers
    local ft = boot(party)
    Mock.advance(20)
    C_Item.RequestLoadItemDataByID = request
    eq(selfSnapshots()[1].equipment.items[1].tooltip, nil)
    for _, item in pairs(party[1].gear) do
      Mock.loadedItems[item.id] = true
    end
    ft.Inspect.selfSnapshot(true)
    eq(selfSnapshots()[2].equipment.items[1].tooltip[1].left, "Loaded Name")
  end)

  it("skips a tooltip that came back without its item's name", function()
    local ft = boot()
    eq(ft.Inspect.tooltipLines({ lines = { { leftText = "Retrieving item information" } } }), nil)
    eq(ft.Inspect.tooltipLines({ lines = {} }), nil)
    eq(ft.Inspect.tooltipLines(nil), nil)
  end)

  it("keys a tooltip by the item and what changes it, not by who holds it", function()
    local ft = boot()
    local real = "|cnIQ2:|Hitem:2985::::::::18:1484::1::1:28:5240:::::|h[Inscribed Leather Breastplate]|h|r"
    eq(ft.Inspect.itemKey(real), "2985" .. string.rep(":", 11) .. "1::1:28:5240", "level and spec dropped")
    eq(ft.Inspect.itemKey("|Hitem:6591:0:0:0:0:0:772:123456:25:0|h[Battleforge Wristguards of the Whale]|h"), "6591:0:0:0:0:0:772")
    eq(ft.Inspect.itemKey("|Hitem:100:0:0:0:0:0:-12:99:25|h[X]|h"), "100:0:0:0:0:0:-12:99", "a negative suffix scales with the unique ID")
    eq(ft.Inspect.itemKey("|Hitem:7|h[Y]|h"), "7")
    eq(ft.Inspect.itemKey(nil), nil)
  end)
end)
