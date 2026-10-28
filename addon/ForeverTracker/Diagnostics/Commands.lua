-- Slash commands: /ft and /forevertracker.
local _, FT = ...

local Commands = {}
FT.Commands = Commands

local HELP = {
  "/ft status - what is being recorded right now",
  "/ft probe - test which game APIs work on this client (saved as an uploadable report)",
  "/ft probe persist - two-step test that saved data survives /reload or a restart",
  "/ft export [all] - show an export string to paste on the ForeverTracker website",
  "/ft collectors - list collectors; /ft enable <name> | /ft disable <name>",
  "/ft debug on|off",
  "/ft purge confirm - delete all stored ForeverTracker data on this account",
}

local function status()
  local db = FT.db
  local run = FT.Storage.activeRun()
  local st = db.active_state
  FT.Util.print(string.format("v%s, %d stored record(s), %d dropped, load #%d, installation %s",
    FT.version, #db.observations, db.dropped.observations or 0, db.load_count or 0, db.installation_id))
  if run then
    FT.Util.print(string.format("recording %s (%s): %d member(s), %d encounter(s), %d death(s), meter %s",
      tostring(run.instance.name), st and st.phase or "?", #run.roster, #run.encounters, #run.deaths,
      run.meter and run.meter.status or "n/a"))
  else
    FT.Util.print("not in a dungeon run.")
  end
  FT.Util.print("Data is written to disk when you log out, exit or /reload.")
end

local function collectors()
  local names = {}
  for name in pairs(FT.Config.COLLECTORS) do
    names[#names + 1] = name
  end
  table.sort(names)
  for _, name in ipairs(names) do
    local def = FT.Config.COLLECTORS[name]
    FT.Util.print(string.format("%s: %s (%s) - %s", name, FT.Config.enabled(name) and "on" or "off", def[3], def[2]))
  end
end

function Commands.handle(msg)
  local cmd, rest = string.match(string.lower(msg or ""), "^%s*(%S*)%s*(.-)%s*$")
  if cmd == "" or cmd == "help" then
    for _, line in ipairs(HELP) do
      FT.Util.print(line)
    end
  elseif cmd == "status" then
    status()
  elseif cmd == "probe" then
    if rest == "persist" then
      FT.Probe.persist(false)
    elseif rest == "persist reset" then
      FT.Probe.persist(true)
    else
      local results = FT.Probe.run()
      FT.Probe.store(results)
      FT.Probe.print(results)
    end
  elseif cmd == "export" then
    FT.Export.show(rest == "all")
  elseif cmd == "collectors" then
    collectors()
  elseif cmd == "enable" or cmd == "disable" then
    if FT.Config.set(rest, cmd == "enable") then
      FT.Util.print(rest .. " " .. cmd .. "d. Some collectors take effect after /reload.")
    else
      FT.Util.print("unknown collector '" .. rest .. "'. Try /ft collectors.")
    end
  elseif cmd == "debug" then
    FT.db.settings.debug = rest == "on"
    FT.Util.print("debug " .. (FT.db.settings.debug and "on" or "off"))
  elseif cmd == "purge" then
    if rest == "confirm" then
      FT.Storage.purge()
      FT.Util.print("all stored ForeverTracker records deleted.")
    else
      FT.Util.print("this deletes every stored record. Type /ft purge confirm to proceed.")
    end
  else
    FT.Util.print("unknown command. /ft help")
  end
end

function Commands.register()
  SLASH_FOREVERTRACKER1 = "/ft"
  SLASH_FOREVERTRACKER2 = "/forevertracker"
  SlashCmdList.FOREVERTRACKER = function(msg)
    local ok, err = pcall(Commands.handle, msg)
    if not ok then
      FT.Events.recordError("commands", err)
      FT.Util.print("command failed: " .. tostring(err))
    end
  end
end
