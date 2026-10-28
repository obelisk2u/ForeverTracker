-- Dungeon-run state machine.
--
--            enter dungeon                  leave instance
--   (none) ---------------> ACTIVE ------------------------> SUSPENDED --(grace expires)--> left
--                            ^  |  logout / reload / exit       |  |
--                            |  +-------------------------------+  +--(other dungeon)-----> left
--                            +---- re-enter same dungeon within grace (corpse run, relog, /reload)
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
  FT.Util.debug("run finished: " .. name)
  FT.Inspect.selfSnapshot(true)
  return run
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
    -- Suspended.
    if sameDungeon and not expired(st, t) then
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
      else
        -- Back in the world outside the dungeon within the grace period (e.g. ported out on
        -- login): wait it out like a normal exit; RT.tick finalizes it when the grace expires.
        st.suspend.reason = "left_instance"
        RT.mark("left_instance", {})
        return
      end
    elseif expired(st, t) or inDungeon then
      RT.finalize("left", st.suspend.at)
    else
      return -- still outside, within the grace period
    end
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
  if active() then
    RT.mark("group_left", {})
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
