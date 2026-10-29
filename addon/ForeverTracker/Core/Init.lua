-- Bootstrap: wait for our SavedVariables, then wire collectors and commands.
local addonName, FT = ...

FT.Events.on("ADDON_LOADED", "init", function(name)
  if name ~= addonName or FT.db then
    return
  end
  FT.Storage.init()
  FT.RunTracker.register()
  FT.Group.register()
  FT.Commands.register()
end)

FT.Events.on("PLAYER_ENTERING_WORLD", "init", function(isInitialLogin, isReloadingUi)
  if FT.lastLoadKind == nil then
    FT.lastLoadKind = (FT.Safe.bool(isReloadingUi) == true and "reload") or (FT.Safe.bool(isInitialLogin) == true and "login") or "zone"
  end
end)
