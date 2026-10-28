-- Instance detection via IsInInstance() and GetInstanceInfo().
--
-- instanceID (8th return of GetInstanceInfo) is the dungeon's MAP ID, not an ID of the
-- specific instance copy; there is no documented per-copy ID for 5-player dungeons.
local _, FT = ...

local Instance = {}
FT.Instance = Instance
local Safe = FT.Safe

function Instance.current()
  local okIn, inInstance, instanceType = Safe.call("IsInInstance")
  local info = { in_instance = false }
  if not okIn then
    return info
  end
  info.in_instance = Safe.bool(inInstance) == true
  info.instance_type = Safe.str(instanceType, 16)
  if not info.in_instance then
    return info
  end
  local ok, name, kind, difficultyId, difficultyName, maxPlayers, _, _, mapId, _, lfgDungeonId = Safe.call("GetInstanceInfo")
  if not ok then
    return info
  end
  info.name = Safe.str(name, 120)
  info.instance_type = Safe.str(kind, 16) or info.instance_type
  info.difficulty_id = Safe.num(difficultyId)
  info.difficulty_name = Safe.str(difficultyName, 120)
  info.max_players = Safe.num(maxPlayers)
  info.map_id = Safe.num(mapId)
  info.lfg_dungeon_id = Safe.num(lfgDungeonId)
  return info
end

-- 5-player dungeons only. Raids, scenarios and battlegrounds are out of scope for v1.
function Instance.isDungeon(info)
  return info and info.in_instance and info.instance_type == "party" and info.map_id ~= nil
end

function Instance.toObservation(info)
  local maxPlayers = info.max_players
  if maxPlayers ~= nil and (maxPlayers < 1 or maxPlayers > 80) then
    maxPlayers = nil
  end
  return {
    map_id = info.map_id,
    name = info.name,
    instance_type = "party",
    difficulty_id = info.difficulty_id,
    difficulty_name = info.difficulty_name,
    max_players = maxPlayers,
    lfg_dungeon_id = (info.lfg_dungeon_id and info.lfg_dungeon_id > 0) and info.lfg_dungeon_id or nil,
  }
end
