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
}
