-- Dungeon-run state machine.
--
--            enter dungeon                  leave instance
--   (none) ---------------> ACTIVE ------------------------> SUSPENDED --(grace expires)--> left
--                            ^  |  logout / reload / exit       |  |
--                            |  +-------------------------------+  +--(other dungeon)-----> left
--                            +---- re-enter same dungeon within grace (corpse run, relog, /reload)
--
--   The run ends FINISH_DELAY_SECONDS after the dungeon's final boss dies (time for the damage
--   meter to read the fight), with state "unknown" unless a completion event came: the final-boss
--   kill makes it a completion in the records and on the website. Staying inside afterwards
--   (looting, /reload, a corpse run back in) does not start a new run. Leaving alive before that
--   ends it at once ("left"). Leaving the group while outside also ends the run, and going back in
--   with a different group starts a new one.
--
--   Final states (observation `state`):
--     completed     only with a completion event (LFG_COMPLETION_REWARD, SCENARIO_COMPLETED,
--                   CHALLENGE_MODE_COMPLETED). Leaving an instance is NEVER a completion.
--     abandoned     an instance-abandon vote passed.
--     left          the observer left the dungeon and did not come back within the grace period.
--     disconnected  the observer's game session ended inside the dungeon (logout, disconnect or
--                   crash) and they did not return within the grace period.
--     unknown       anything else.
--   Boss kills are recorded as encounters; they are not completion evidence on their own.
local _, FT = ...

local RT = {}
FT.RunTracker = RT
local Safe = FT.Safe

local function now()
  return FT.Util.now()
end

local function active()
  return FT.Storage.activeRun()
end

local function state()
  return FT.db and FT.db.active_state
end

function RT.mark(kind, detail)
  local run = active()
  if not run then
    return
  end
  local tl = run.timeline
  if #tl >= FT.Config.LIMITS.max_timeline then
    run.flags.timeline_truncated = true
    return
  end
  tl[#tl + 1] = { at = now(), kind = kind, detail = detail or {} }
end

local function touch(run)
  local t = now()
  if t > run.timing.last_updated_at then
    run.timing.last_updated_at = t
  end
end

local function collection(run, st)
  local C = FT.Config
  local events = FT.capabilities.events
  local meterStatus = run.meter and run.meter.status or "unavailable"
  run.collection = {
    identity = C.enabled("identity") and "active" or "disabled",
    roster = "active",
    encounters = (not C.enabled("encounters") and "disabled") or (events.ENCOUNTER_START == false and "unavailable") or "active",
    deaths_unit_state = FT.Deaths.status(st),
    deaths_unit_died = (not C.enabled("deaths_unit_died") and "disabled")
      or (events.UNIT_DIED ~= true and "unavailable")
      or (st.unit_died_secret and "partial")
      or "active",
    meter = (meterStatus == "disabled" and "disabled")
      or (meterStatus == "unavailable" and "unavailable")
      or (meterStatus == "observed" and "active")
      or "partial",
    inspect = C.enabled("inspect") and "active" or "disabled",
    talents = C.enabled("talents") and "active" or "disabled",
  }
end
RT.updateCollection = collection

-- The records window shows whether a run is being recorded.
local function refreshWindow()
  FT.Events.guard("records", function()
    FT.RecordsUI.refresh()
  end)
end

function RT.start(info)
  local t = now()
  local player = FT.Identity.player() or {}
  local run = {
    type = "dungeon_run",
    observation_id = FT.Storage.nextId("r"),
    revision = 1,
    recorded_by = {
      guid = player.guid,
      name = player.name,
      surname = player.surname,
      identity_status = player.identity_status or "unavailable",
    },
    namespace = FT.Identity.namespace(),
    realm_label = FT.Identity.realmLabel(),
    client_build = FT.db.client and FT.db.client.build or nil,
    instance = FT.Instance.toObservation(info),
    party_guid = FT.db.group and FT.db.group.party_guid or nil,
    timing = { started_at = t, last_updated_at = t, clock = "server", local_clock_offset = FT.Util.clockOffset() },
    state = "in_progress",
    completion = { status = "none", evidence = {} },
    timeline = {},
    roster = {},
    encounters = {},
    deaths = {},
    collection = {},
    flags = {},
  }
  if not FT.Util.isForeverClient() then
    run.flags.non_forever_client = true
  end
  if not FT.Identity.regionalNames() then
    run.flags.non_regional_names = true
  end
  local st = { phase = "active", refs = {}, dead = {}, connected = {} }
  FT.db.active_state = st
  FT.Storage.setActiveRun(run)
  RT.mark("entered", { map_id = info.map_id })
  FT.Roster.scan(run, st, t)
  FT.Deaths.poll(run, st, t)
  FT.Meter.startRun(run, st)
  collection(run, st)
  FT.Inspect.queueGroup()
  refreshWindow()
  FT.Util.debug("run started: " .. tostring(run.instance.name))
  return run
end

function RT.finalize(final, endedAt)
  local run, st = active(), state()
  if not run then
    return nil
  end
  local t = now()
  st = st or {}
  if st.phase == "active" then
    if st.meter and not FT.Meter.inCombat() then
      FT.Meter.capturePass(run, st)
    end
    FT.Roster.closeAll(run, endedAt or t)
  end
  local name = final
  if run.completion.status == "verified" then
    name = "completed"
  elseif st.abandoned then
    name = "abandoned"
  end
  run.state = name
  local ended = endedAt or t
  if ended < run.timing.started_at then
    ended = run.timing.started_at
  end
  run.timing.ended_at = ended
  if run.meter and run.meter.status == "observed" and #run.meter.sessions == 0 then
    run.meter.status = "unavailable"
    run.meter.reason = "no_sessions_observed"
  end
  collection(run, st)
  run.revision = run.revision + 1
  touch(run)
  FT.Storage.push(run)
  FT.Storage.setActiveRun(nil)
  FT.db.active_state = nil
  -- The player's own records (the records window); a failure there never loses the run.
  FT.Events.guard("records", function()
    FT.Records.addRun(run)
    FT.RecordsUI.refresh()
  end)
  FT.Util.debug("run finished: " .. name)
  FT.Inspect.selfSnapshot(true)
  return run
end

-- Splitting a merged run -------------------------------------------------------------------------
-- Addon 0.2.2 and earlier resumed the open run when the player went back into the same dungeon
-- within the grace period, even after leaving the group outside: the next group's run was added
-- to the previous one. RT.splitMerged separates such a run where the player went back in.

-- When the player left the first run and when they went back in for the second, or nil.
local function mergedAt(run)
  local leftAt, groupLeft = nil, false
  for _, e in ipairs(run.timeline or {}) do
    if e.kind == "left_instance" then
      leftAt, groupLeft = e.at, false
    elseif e.kind == "group_left" then
      groupLeft = leftAt ~= nil
    elseif e.kind == "reentered" then
      if leftAt and groupLeft then
        return leftAt, e.at
      end
      leftAt, groupLeft = nil, false
    end
  end
  return nil
end

local function filter(list, keep)
  local out = {}
  for _, v in ipairs(list or {}) do
    if keep(v) then
      out[#out + 1] = v
    end
  end
  return out
end

local function copy(t)
  local out = {}
  for k, v in pairs(t or {}) do
    out[k] = v
  end
  return out
end

-- Roster entries with only their presence before (after = false) or from (after = true) `at`.
-- Zero-length presence (seen and gone in the same instant) is dropped.
local function rosterSide(roster, at, after)
  local out = {}
  for _, entry in ipairs(roster or {}) do
    local presence = filter(entry.presence, function(p)
      return (p.start >= at) == after and p["end"] ~= p.start
    end)
    if #presence > 0 then
      local e = copy(entry)
      e.presence = presence
      if after then
        e.connection_drops = 0
      end
      out[#out + 1] = e
    end
  end
  return out
end

local METER_KEYS = { "status", "values", "deaths", "durations", "captured_at", "ended_at" }

-- The meter bookkeeping for the sessions on one side of `at`. Each side treats the other side's
-- sessions as baseline, so they are never captured into it.
local function meterSide(m, at, after)
  local side = copy(m)
  side.baseline = copy(m.baseline)
  for _, key in ipairs(METER_KEYS) do
    side[key] = {}
  end
  for id in pairs(m.status) do
    local t = (m.ended_at and m.ended_at[id]) or (m.captured_at and m.captured_at[id])
    if (t == nil or t >= at) == after then
      for _, key in ipairs(METER_KEYS) do
        side[key][id] = m[key] and m[key][id]
      end
    else
      side.baseline[id] = true
    end
  end
  return side
end

local function metered(run)
  return run.meter and run.meter.status ~= "disabled" and run.meter.status ~= "unavailable"
end

function RT.splitMerged()
  local run, st = active(), state()
  if not run or not st then
    return nil
  end
  local leftAt, backAt = mergedAt(run)
  if not backAt then
    return nil
  end
  local function before(t)
    return t ~= nil and t < backAt
  end

  -- Build both halves before changing anything: an error leaves the run as it was.
  local first = copy(run)
  first.timeline = filter(run.timeline, function(e)
    return before(e.at)
  end)
  first.encounters = filter(run.encounters, function(e)
    return before(e.started_at)
  end)
  first.deaths = filter(run.deaths, function(d)
    return before(d.at)
  end)
  first.roster = rosterSide(run.roster, backAt, false)
  local firstEvidence = filter(run.completion.evidence, function(ev)
    return before(ev.at)
  end)
  first.completion = { status = #firstEvidence > 0 and "verified" or "none", evidence = firstEvidence }
  first.flags = copy(run.flags)
  first.flags.party_guid_changed = nil
  first.flags.split_from_merged = true
  first.timing = copy(run.timing)
  first.timing.ended_at = leftAt
  first.timing.last_updated_at = leftAt
  first.meter = copy(run.meter)
  first.state = first.completion.status == "verified" and "completed" or "left"
  first.revision = run.revision + 1

  local timeline = filter(run.timeline, function(e)
    return not before(e.at) and not (e.kind == "reentered" and e.at == backAt)
  end)
  table.insert(timeline, 1, { at = backAt, kind = "entered", detail = { map_id = run.instance.map_id } })
  local encounters = filter(run.encounters, function(e)
    return not before(e.started_at)
  end)
  local deaths = filter(run.deaths, function(d)
    return not before(d.at)
  end)
  local roster = rosterSide(run.roster, backAt, true)
  local evidence = filter(run.completion.evidence, function(ev)
    return not before(ev.at)
  end)

  local secondMeter
  if st.meter and metered(run) then
    secondMeter = meterSide(st.meter, backAt, true)
    FT.Meter.rebuild(first, { meter = meterSide(st.meter, backAt, false) })
    if #first.meter.sessions == 0 then
      first.meter.status = "unavailable"
      first.meter.reason = "no_sessions_observed"
    end
  end
  collection(first, st)

  -- The first run is finished.
  FT.Storage.push(first)
  FT.Events.guard("records", function()
    FT.Records.addRun(first)
  end)

  -- The open run continues as the second one.
  run.observation_id = FT.Storage.nextId("r")
  run.revision = 1
  run.timing.started_at = backAt
  run.timing.ended_at = nil
  run.timeline = timeline
  run.encounters = encounters
  run.deaths = deaths
  run.roster = roster
  run.completion = { status = #evidence > 0 and "verified" or "none", evidence = evidence }
  run.flags.party_guid_changed = nil
  run.flags.split_from_merged = true
  run.party_guid = FT.db.group and FT.db.group.party_guid or nil
  local refs = {}
  for _, entry in ipairs(roster) do
    refs[entry.ref] = true
  end
  for key, ref in pairs(st.refs or {}) do
    if not refs[ref] then
      st.refs[key] = nil
    end
  end
  st.finishing = nil
  if secondMeter then
    st.meter = secondMeter
    FT.Meter.rebuild(run, st)
  end
  collection(run, st)
  touch(run)
  refreshWindow()
  FT.Util.debug("split a merged run")
  return first, run
end

-- The dungeon's final boss died in this run and the player is alive: nothing left to come back for.
local function killedFinal(run)
  local finals = FT.FINAL_ENCOUNTERS and FT.FINAL_ENCOUNTERS[run.instance.map_id]
  if not finals then
    return false
  end
  for _, e in ipairs(run.encounters or {}) do
    if e.success == true and finals[e.encounter_id] then
      return true
    end
  end
  return false
end

local function playerAlive()
  local ok, dead = Safe.call("UnitIsDeadOrGhost", "player")
  return ok and Safe.bool(dead) == false
end

local function finishedAlive(run)
  return killedFinal(run) and playerAlive()
end

-- Outside the dungeon with nothing to go back for: the player left the group after leaving the
-- dungeon, or the final boss is dead and the player alive. (Checked again on load, for a run
-- left while an earlier version was running.)
local function overOutside(run, st)
  local leftAt = st.suspend and st.suspend.at
  for _, e in ipairs(run.timeline or {}) do
    if e.kind == "group_left" and leftAt and e.at >= leftAt then
      return true
    end
  end
  return finishedAlive(run)
end

RT.FINISH_DELAY_SECONDS = 20
RT.FINISH_RETRY_SECONDS = 5
RT.FINISH_MAX_TRIES = 12

-- The final boss died: end the run once the meter has read the fight (out of combat).
function RT.afterBossKill(run)
  local st = state()
  if not st or st.finishing or not killedFinal(run) then
    return
  end
  st.finishing = true
  local tries = 0
  local function finish()
    tries = tries + 1
    local st2 = state()
    if active() ~= run or not st2 or st2.phase ~= "active" then
      return -- already over, or outside (the leaving rules apply)
    end
    if FT.Meter.inCombat() and tries < RT.FINISH_MAX_TRIES then
      FT.Events.after(RT.FINISH_RETRY_SECONDS, "runtracker", finish)
      return
    end
    RT.finalize("unknown", now())
    if not active() then
      FT.db.finished_here = { map_id = run.instance.map_id, at = now() }
    end
  end
  FT.Events.after(RT.FINISH_DELAY_SECONDS, "runtracker", finish)
end

-- After a run ended at its final boss the player may stay inside (loot, /reload, relog) or, as a
-- ghost, go back in for their corpse: none of that is a new run. Leaving alive, entering another
-- dungeon or the grace period passing clears it.
local function stillFinished(info, inDungeon)
  local done = FT.db.finished_here
  if not done then
    return false
  end
  if now() - (done.at or 0) > FT.Config.LIMITS.resume_grace_seconds then
    FT.db.finished_here = nil
    return false
  end
  if inDungeon then
    if info.map_id == done.map_id then
      return true
    end
    FT.db.finished_here = nil
    return false
  end
  if playerAlive() then
    FT.db.finished_here = nil
  end
  return false
end

function RT.suspend(reason)
  local run, st = active(), state()
  if not run or not st or st.phase ~= "active" then
    return
  end
  local t = now()
  FT.Meter.suspend(run, st)
  FT.Roster.closeAll(run, t)
  st.phase = "suspended"
  st.finishing = nil -- a pending end at the final boss restarts on resume
  st.suspend = { reason = reason, at = t, id = ((st.suspend_seq or 0) + 1) }
  st.suspend_seq = st.suspend.id
  RT.mark(reason == "session_end" and "logout" or "left_instance", {})
  touch(run)
  collection(run, st)
  if reason == "left_instance" then
    if run.completion.status == "verified" or st.abandoned then
      RT.finalize("unknown", t)
      return
    end
    if finishedAlive(run) then
      RT.finalize("left", t)
      return
    end
    refreshWindow()
    local sid = st.suspend.id
    FT.Events.after(FT.Config.LIMITS.resume_grace_seconds, "runtracker", function()
      local st2 = state()
      if active() == run and st2 and st2.phase == "suspended" and st2.suspend and st2.suspend.id == sid then
        RT.finalize("left", st2.suspend.at)
      end
    end)
  else
    run.revision = run.revision + 1 -- the file is about to be written
  end
end

function RT.resume(kind)
  local run, st = active(), state()
  if not run or not st then
    return
  end
  st.phase = "active"
  st.suspend = nil
  RT.mark(kind, {})
  if kind == "login" or kind == "reload" then
    run.flags["resumed_after_" .. kind] = true
  end
  FT.Meter.resume(run, st)
  local t = now()
  FT.Roster.scan(run, st, t)
  FT.Deaths.poll(run, st, t)
  touch(run)
  collection(run, st)
  refreshWindow()
  RT.afterBossKill(run)
end

local function expired(st, t)
  return st.suspend and (t - st.suspend.at) > FT.Config.LIMITS.resume_grace_seconds
end

-- PLAYER_ENTERING_WORLD: login, /reload and every loading screen.
function RT.onEnteringWorld(isInitialLogin, isReloadingUi)
  local info = FT.Instance.current()
  local inDungeon = FT.Instance.isDungeon(info)
  local run, st = active(), state()
  local t = now()
  local sessionStart = (Safe.bool(isInitialLogin) == true) or (Safe.bool(isReloadingUi) == true)
  if sessionStart and run and st then
    FT.Events.guard("runtracker", RT.splitMerged)
  end

  if run and not st then
    -- Run saved without its bookkeeping (should not happen): keep the data, mark it partial.
    st = { phase = "suspended", suspend = { reason = "session_end", at = run.timing.last_updated_at, id = 1 }, refs = {}, dead = {} }
    st.resumed_without_state = true
    FT.db.active_state = st
  end

  if run and sessionStart and st.phase == "active" then
    -- No logout was recorded: the previous session ended abruptly (crash or lost connection
    -- before the client could save). Treat it as a session end at the last saved time.
    run.flags.abrupt_session_end = true
    st.phase = "suspended"
    st.suspend = { reason = "session_end", at = run.timing.last_updated_at, id = (st.suspend_seq or 0) + 1 }
    st.suspend_seq = st.suspend.id
  end

  if run then
    local sameDungeon = inDungeon and info.map_id == run.instance.map_id
    if st.phase == "active" then
      if sameDungeon then
        return -- loading screen inside the same instance
      end
      if inDungeon then
        RT.finalize("left", t)
        RT.start(info)
      else
        RT.suspend("left_instance")
      end
      return
    end
    -- Suspended. Going back in with a different group is a new run.
    local group = FT.db.group and FT.db.group.party_guid
    local sameGroup = not (run.party_guid and group and group ~= run.party_guid)
    if sameDungeon and sameGroup and not expired(st, t) then
      local kind = "reentered"
      if Safe.bool(isReloadingUi) == true then
        kind = "reload"
      elseif Safe.bool(isInitialLogin) == true then
        kind = "login"
      end
      RT.resume(kind)
      return
    end
    if st.suspend.reason == "session_end" then
      if expired(st, t) or inDungeon then
        RT.finalize("disconnected", st.suspend.at)
      elseif overOutside(run, st) then
        RT.finalize("left", st.suspend.at)
      else
        -- Back in the world outside the dungeon within the grace period (e.g. ported out on
        -- login): wait it out like a normal exit; RT.tick finalizes it when the grace expires.
        st.suspend.reason = "left_instance"
        RT.mark("left_instance", {})
        return
      end
    elseif expired(st, t) or inDungeon or overOutside(run, st) then
      RT.finalize("left", st.suspend.at)
    else
      return -- still outside, within the grace period
    end
  end
  if stillFinished(info, inDungeon) then
    return
  end
  if inDungeon then
    RT.start(info)
  end
end

function RT.onLogout()
  if active() then
    RT.suspend("session_end")
  end
end

function RT.onRosterUpdate()
  local run, st = active(), state()
  if not run or not st or st.phase ~= "active" then
    return
  end
  local joined, left = FT.Roster.scan(run, st, now())
  if joined > 0 or left > 0 then
    RT.mark("roster_changed", { joined = joined, left = left })
  end
  FT.Deaths.poll(run, st, now())
  touch(run)
  FT.Inspect.queueGroup()
end

function RT.onGroupJoined(category, partyGuid)
  local g = Safe.str(partyGuid, 96)
  if g and not string.match(g, "^[%w%-]+$") then
    g = nil
  end
  FT.db.group = { party_guid = g, joined_at = now() }
  local run = active()
  if run then
    RT.mark("group_joined", {})
    if run.party_guid == nil then
      run.party_guid = g
    elseif g and run.party_guid ~= g then
      run.flags.party_guid_changed = true
    end
  end
end

function RT.onGroupLeft()
  FT.db.group = nil
  local run, st = active(), state()
  if run then
    RT.mark("group_left", {})
    if st and st.phase == "suspended" and st.suspend and st.suspend.reason == "left_instance" then
      RT.finalize("left", st.suspend.at) -- left the group outside the dungeon: that run is over
      return
    end
    RT.onRosterUpdate()
  end
end

function RT.onCompletion(kind)
  local run, st = active(), state()
  if not run or not st or st.phase ~= "active" then
    return
  end
  local t = now()
  if #run.completion.evidence < 10 then
    run.completion.evidence[#run.completion.evidence + 1] = { kind = kind, at = t }
  end
  run.completion.status = "verified"
  RT.mark("completed", { source = kind })
  touch(run)
end

function RT.onAbandonVote(votePassed)
  local run, st = active(), state()
  if not run or not st then
    return
  end
  local passed = Safe.bool(votePassed)
  RT.mark("abandon_vote", { passed = passed })
  if passed == true then
    st.abandoned = true
  end
end

function RT.tick()
  local run, st = active(), state()
  if run and st then
    local t = now()
    if st.phase == "active" then
      FT.Events.guard("deaths_unit_state", FT.Deaths.poll, run, st, t)
    elseif expired(st, t) and st.suspend.reason == "left_instance" then
      RT.finalize("left", st.suspend.at)
    end
  end
  FT.Events.guard("inspect", FT.Inspect.step)
end

function RT.withActive(fn)
  return function(...)
    local run, st = active(), state()
    if run and st and st.phase == "active" then
      fn(run, st, now(), ...)
    end
  end
end

-- Wire events once the SavedVariables are loaded.
function RT.register()
  local E = FT.Events
  E.on("PLAYER_ENTERING_WORLD", "runtracker", function(isInitialLogin, isReloadingUi)
    RT.onEnteringWorld(isInitialLogin, isReloadingUi)
    FT.Inspect.selfSnapshot(false)
  end)
  E.on("PLAYER_LOGOUT", "runtracker", RT.onLogout)
  local pendingRoster = false
  E.on("GROUP_ROSTER_UPDATE", "runtracker", function()
    if pendingRoster then
      return
    end
    pendingRoster = true
    E.after(0.5, "runtracker", function()
      pendingRoster = false
      RT.onRosterUpdate()
    end)
  end)
  E.on("GROUP_JOINED", "runtracker", RT.onGroupJoined)
  E.on("GROUP_LEFT", "runtracker", RT.onGroupLeft)
  E.on("LFG_COMPLETION_REWARD", "runtracker", function()
    RT.onCompletion("lfg_completion_reward")
  end)
  E.on("SCENARIO_COMPLETED", "runtracker", function()
    RT.onCompletion("scenario_completed")
  end)
  E.on("CHALLENGE_MODE_COMPLETED", "runtracker", function()
    RT.onCompletion("challenge_mode_completed")
  end)
  E.on("INSTANCE_ABANDON_VOTE_FINISHED", "runtracker", RT.onAbandonVote)

  if FT.Config.enabled("encounters") then
    E.on("ENCOUNTER_START", "encounters", RT.withActive(FT.Encounters.start))
    E.on("ENCOUNTER_END", "encounters", RT.withActive(function(run, st, t, id, _, _, _, success)
      FT.Encounters.finish(run, st, t, id, success)
      RT.afterBossKill(run)
    end))
  end
  E.on("PLAYER_DEAD", "deaths_unit_state", RT.withActive(FT.Deaths.playerDead))
  local lastPoll = 0
  local function unitChanged(run, st, t, unit)
    local clock = GetTime()
    if clock - lastPoll >= 0.2 then
      lastPoll = clock
      FT.Deaths.poll(run, st, t)
    end
  end
  E.on("UNIT_FLAGS", "deaths_unit_state", RT.withActive(unitChanged))
  E.on("UNIT_HEALTH", "deaths_unit_state", RT.withActive(unitChanged))
  if FT.Config.enabled("deaths_unit_died") then
    E.on("UNIT_DIED", "deaths_unit_died", RT.withActive(FT.Deaths.unitDied))
  end

  local function meterNow(run, st)
    FT.Meter.schedule(run, st)
  end
  E.on("PLAYER_REGEN_ENABLED", "meter", RT.withActive(function(run, st)
    meterNow(run, st)
    FT.Inspect.queueGroup()
  end))
  E.on("DAMAGE_METER_COMBAT_SESSION_UPDATED", "meter", RT.withActive(meterNow))
  E.on("DAMAGE_METER_CURRENT_SESSION_UPDATED", "meter", RT.withActive(meterNow))
  E.on("DAMAGE_METER_RESET", "meter", RT.withActive(FT.Meter.reset))
  E.on("INSPECT_READY", "inspect", FT.Inspect.ready)

  E.ticker(FT.Config.LIMITS.death_poll_seconds, "runtracker", RT.tick)
end
