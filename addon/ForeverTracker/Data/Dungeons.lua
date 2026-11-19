-- The boss whose kill finishes each dungeon, by instance map ID: a copy of
-- backend/app/reconciliation/final_encounters.json, kept in sync by addon/tests/test_addon.py.
-- Groups formed outside the dungeon finder never get a completion event, so the records window
-- counts a run that kills one of these bosses as completed, as the website does.
local _, FT = ...

FT.FINAL_ENCOUNTERS = {
  [33] = { [2755] = true }, -- Shadowfang Keep: Archmage Arugal
  [34] = { [2760] = true }, -- Stormwind Stockade: Bazil Thredd
  [36] = { [2747] = true }, -- Deadmines: Edwin VanCleef
  [43] = { [592] = true }, -- Wailing Caverns: Mutanus the Devourer
  [47] = { [2778] = true }, -- Razorfen Kraul: Charlga Razorflank
  [48] = { [2910] = true, [2767] = true, [2891] = true }, -- Blackfathom Deeps: Aku'mai
  [70] = { [554] = true }, -- Uldaman: Archaedas
  [90] = { [2772] = true, [2940] = true }, -- Gnomeregan: Mekgineer Thermaplugg
  [129] = { [2785] = true }, -- Razorfen Downs: Amnennar the Coldbringer
  [189] = { [2779] = true, [447] = true, [448] = true, [450] = true }, -- Scarlet Monastery: Bloodmage Thalnos, Arcanist Doan, Herod, High Inquisitor Whitemane
  [209] = { [600] = true }, -- Zul'Farrak: Chief Ukorz Sandscalp
  [229] = { [275] = true, [3069] = true }, -- Blackrock Spire: Overlord Wyrmthalak, General Drakkisath
  [230] = { [2790] = true }, -- Blackrock Depths: Emperor Dagran Thaurissan
  [289] = { [2801] = true }, -- Scholomance: Darkmaster Gandling
  [329] = { [478] = true, [484] = true }, -- Stratholme: Balnazzar, Baron Rivendare
  [349] = { [429] = true }, -- Maraudon: Princess Theradras
  [389] = { [2735] = true }, -- Ragefire Chasm: Bazzalan
  [429] = { [346] = true, [361] = true, [368] = true }, -- Dire Maul: Alzzin the Wildshaper, Prince Tortheldrin, King Gordok
  [2784] = { [3080] = true }, -- Demon Fall Canyon: Azgaloth
  [2959] = { [3303] = true }, -- City of Dalaran: Shade of the Archmage
  [2998] = { [3482] = true }, -- Excavation Site: Wetlands: Relic Guardian
  [3065] = { [3496] = true }, -- The Hall of Thanes: Durgen Dirgehammer
}

-- Dungeons whose wings share one instance map ID, by map ID: each wing's bosses. A run is in the
-- wing of the first of these bosses it pulls; one that pulls none is the whole dungeon. A copy of
-- the "wings" in backend/app/reconciliation/final_encounters.json, kept in sync by the same test.
FT.WINGS = {
  [189] = { -- Scarlet Monastery
    { key = "graveyard", name = "Graveyard", bosses = { [444] = true, [2779] = true } }, -- Interrogator Vishas, Bloodmage Thalnos
    { key = "library", name = "Library", bosses = { [446] = true, [447] = true } }, -- Houndmaster Loksey, Arcanist Doan
    { key = "armory", name = "Armory", bosses = { [448] = true } }, -- Herod
    { key = "cathedral", name = "Cathedral", bosses = { [449] = true, [450] = true } }, -- High Inquisitor Fairbanks, High Inquisitor Whitemane
  },
}

-- The wing a boss belongs to, or nil.
function FT.wingOfBoss(mapId, encounterId)
  for _, wing in ipairs((mapId and FT.WINGS[mapId]) or {}) do
    if wing.bosses[encounterId] then
      return wing
    end
  end
  return nil
end

-- The wing a run is in (that of the first wing boss it pulled), or nil.
function FT.wingOf(run)
  local mapId = type(run) == "table" and type(run.instance) == "table" and run.instance.map_id
  if not (mapId and FT.WINGS[mapId]) then
    return nil
  end
  for _, e in ipairs(run.encounters or {}) do
    local wing = FT.wingOfBoss(mapId, e.encounter_id)
    if wing then
      return wing
    end
  end
  return nil
end

-- The run's dungeon as players name it: "Scarlet Monastery: Library" once a Library boss is pulled.
function FT.dungeonName(run)
  local name = type(run) == "table" and type(run.instance) == "table" and run.instance.name or nil
  local wing = FT.wingOf(run)
  if name and wing then
    return name .. ": " .. wing.name
  end
  return name
end
