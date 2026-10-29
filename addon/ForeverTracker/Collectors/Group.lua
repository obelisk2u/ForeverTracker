-- Everyone the player groups with, anywhere: name, surname, GUID, class and race.
--
-- Dungeon runs already record their roster. This also covers groups in the open world, so a
-- character becomes known even if they never ran a dungeon with an addon user. Level and role are
-- left out on purpose: they change, and runs record them where they matter. A character is
-- recorded again only when one of these fields changes, or after a week so the site sees they are
-- still around.
local _, FT = ...

local Group = {}
FT.Group = Group

local function signature(m)
  return table.concat({ m.name or "", m.surname or "", m.class_file or "", m.race_file or "" }, "|")
end

-- Store a character_snapshot (source "group") for each group member not recorded recently.
-- Returns how many were stored.
function Group.scan()
  if not FT.Config.enabled("group") then
    return 0
  end
  local seen = FT.db.group_seen
  local now = FT.Util.now()
  local refresh = FT.Config.LIMITS.group_refresh_seconds
  local player, namespace
  local stored = 0
  for _, unit in ipairs(FT.Roster.units()) do
    if unit ~= "player" then
      local m = FT.Identity.read(unit)
      local key = m and m.identity_status == "ok" and FT.Identity.key(m)
      if key then
        local sig = signature(m)
        local last = seen[key]
        if not last or last.sig ~= sig or now - last.at >= refresh then
          player = player or FT.Identity.player() or {}
          namespace = namespace or FT.Identity.namespace()
          FT.Storage.push({
            type = "character_snapshot",
            observation_id = FT.Storage.nextId("g"),
            revision = 1,
            recorded_by = { guid = player.guid, name = player.name, surname = player.surname },
            namespace = namespace,
            realm_label = FT.Identity.realmLabel(),
            client_build = FT.db.client and FT.db.client.build or nil,
            observed_at = now,
            source = "group",
            subject = {
              guid = m.guid,
              name = m.name,
              surname = m.surname,
              identity_status = m.identity_status,
              class_file = m.class_file,
              race_file = m.race_file,
            },
          })
          seen[key] = { sig = sig, at = now }
          stored = stored + 1
        end
      end
    end
  end
  return stored
end

-- Forget characters not recorded for a while, so the table cannot grow without bound.
function Group.prune()
  local cutoff = FT.Util.now() - FT.Config.LIMITS.group_refresh_seconds
  for key, last in pairs(FT.db.group_seen) do
    if last.at < cutoff then
      FT.db.group_seen[key] = nil
    end
  end
end

function Group.register()
  Group.prune()
  local E = FT.Events
  local pending = false
  E.on("GROUP_ROSTER_UPDATE", "group", function()
    if pending then
      return
    end
    pending = true
    E.after(0.5, "group", function()
      pending = false
      Group.scan()
    end)
  end)
  -- Logging in while already grouped: names may still be loading, so GROUP_ROSTER_UPDATE retries.
  E.on("PLAYER_ENTERING_WORLD", "group", function()
    Group.scan()
  end)
end
