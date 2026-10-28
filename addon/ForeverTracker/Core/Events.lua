-- Event registration and dispatch.
--
-- On Forever, registering an unknown event throws and aborts the file (forever-addon-kit), so
-- every registration is checked with C_EventUtils.IsEventValid and wrapped in pcall. Handler
-- errors are caught and counted per collector; a collector that keeps failing is switched off
-- for the session so it cannot flood the client's 100-error cap.
local _, FT = ...

local Events = {}
FT.Events = Events

local frame = CreateFrame("Frame")
local handlers = {}
FT.capabilities = FT.capabilities or { events = {}, errors = {} }
FT.disabledThisSession = {}

local function recordError(owner, err)
  local errors = FT.capabilities.errors
  errors[owner] = (errors[owner] or 0) + 1
  FT.lastError = { owner = owner, message = tostring(err) }
  if errors[owner] >= FT.Config.LIMITS.max_collector_errors and FT.Config.COLLECTORS[owner] then
    FT.disabledThisSession[owner] = true
    FT.Util.print("collector '" .. owner .. "' disabled for this session after repeated errors: " .. tostring(err))
  end
end
Events.recordError = recordError

function Events.isValid(event)
  local valid = FT.Safe.api("C_EventUtils.IsEventValid")
  if valid then
    local ok, result = pcall(valid, event)
    return ok and result == true
  end
  return true -- older clients without the check: rely on pcall below
end

-- Register fn for event on behalf of owner. Returns true when the event is available.
function Events.on(event, owner, fn)
  if FT.capabilities.events[event] == false then
    return false
  end
  if not handlers[event] then
    if not Events.isValid(event) then
      FT.capabilities.events[event] = false
      return false
    end
    local ok = pcall(frame.RegisterEvent, frame, event)
    FT.capabilities.events[event] = ok
    if not ok then
      return false
    end
    handlers[event] = {}
  end
  table.insert(handlers[event], { owner = owner, fn = fn })
  return true
end

function Events.dispatch(event, ...)
  local list = handlers[event]
  if not list then
    return
  end
  for i = 1, #list do
    local h = list[i]
    if not (FT.disabledThisSession[h.owner]) then
      local ok, err = pcall(h.fn, ...)
      if not ok then
        recordError(h.owner, err)
      end
    end
  end
end

frame:SetScript("OnEvent", function(_, event, ...)
  Events.dispatch(event, ...)
end)

-- Run fn under owner's error budget (for collectors called from shared tickers/handlers).
function Events.guard(owner, fn, ...)
  if FT.disabledThisSession[owner] then
    return
  end
  local ok, err = pcall(fn, ...)
  if not ok then
    recordError(owner, err)
  end
end

-- Guarded timers.
function Events.after(seconds, owner, fn)
  C_Timer.After(seconds, function()
    if FT.disabledThisSession[owner] then
      return
    end
    local ok, err = pcall(fn)
    if not ok then
      recordError(owner, err)
    end
  end)
end

function Events.ticker(seconds, owner, fn)
  return C_Timer.NewTicker(seconds, function()
    if FT.disabledThisSession[owner] then
      return
    end
    local ok, err = pcall(fn)
    if not ok then
      recordError(owner, err)
    end
  end)
end
