-- Boss encounters via ENCOUNTER_START / ENCOUNTER_END (success = 1 kill, 0 wipe).
local _, FT = ...

local Encounters = {}
FT.Encounters = Encounters
local Safe = FT.Safe

function Encounters.start(run, state, now, encounterId, name, difficultyId, groupSize)
  local id = Safe.num(encounterId)
  if id == nil then
    return
  end
  local list = run.encounters
  if #list >= 100 then
    return
  end
  list[#list + 1] = {
    encounter_id = id,
    name = Safe.str(name, 120),
    difficulty_id = Safe.num(difficultyId),
    group_size = Safe.num(groupSize),
    started_at = now,
  }
  state.current_encounter = id
  FT.RunTracker.mark("encounter_start", { encounter_id = id })
end

function Encounters.finish(run, state, now, encounterId, success)
  local id = Safe.num(encounterId)
  if id == nil then
    return
  end
  local flag = Safe.num(success)
  for i = #run.encounters, 1, -1 do
    local e = run.encounters[i]
    if e.encounter_id == id and e.ended_at == nil then
      e.ended_at = now
      if flag ~= nil then
        e.success = flag == 1
      end
      state.last_encounter_end = { id = id, at = now, duration = now - e.started_at }
      break
    end
  end
  state.current_encounter = nil
  FT.RunTracker.mark("encounter_end", { encounter_id = id, success = flag })
end
