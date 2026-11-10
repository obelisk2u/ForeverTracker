-- The round minimap button that opens the records window, and the same entry in the minimap's
-- addon compartment menu (the TOC's AddonCompartmentFunc).
--
-- Drawn and dragged around the minimap's edge the way LibDBIcon does it, without the library.
-- Its angle and visibility are saved in ForeverTrackerDB.settings.minimap; /ft minimap hides it.
local _, FT = ...

local MB = {}
FT.MinimapButton = MB

local ICON = "Interface\\AddOns\\ForeverTracker\\Media\\Emblem"
local GOLD = { 0.886, 0.702, 0.337 }
local button
local dragging = false

local function settings()
  local s = FT.db.settings
  if type(s.minimap) ~= "table" then
    s.minimap = { hide = false, angle = 215 }
  end
  return s.minimap
end

-- Square minimaps put the button in the corners; anything else is treated as round.
local function place(angle)
  local rad = math.rad(angle)
  local x, y = math.cos(rad), math.sin(rad)
  local w = (Minimap:GetWidth() or 140) / 2 + 5
  local h = (Minimap:GetHeight() or 140) / 2 + 5
  local shape = GetMinimapShape and GetMinimapShape() or "ROUND"
  if shape == "SQUARE" then
    x = math.max(-w, math.min(x * (math.sqrt(2 * w * w) - 10), w))
    y = math.max(-h, math.min(y * (math.sqrt(2 * h * h) - 10), h))
  else
    x, y = x * w, y * h
  end
  button:ClearAllPoints()
  button:SetPoint("CENTER", Minimap, "CENTER", x, y)
end
MB.place = place

-- While dragging: follow the cursor around the minimap's centre.
local function follow()
  local mx, my = Minimap:GetCenter()
  local px, py = GetCursorPosition()
  local scale = Minimap:GetEffectiveScale()
  if not (mx and px and scale) then
    return
  end
  local angle = math.deg(math.atan2(py / scale - my, px / scale - mx)) % 360
  settings().angle = angle
  place(angle)
end

function MB.tooltip(owner)
  GameTooltip:SetOwner(owner, "ANCHOR_LEFT")
  GameTooltip:AddLine("ForeverTracker", GOLD[1], GOLD[2], GOLD[3])
  local run = FT.Storage.activeRun()
  if run and run.instance then
    local where = run.instance.name or "this dungeon"
    local st = FT.db.active_state
    if st and st.phase == "suspended" then
      GameTooltip:AddLine("Paused: " .. where, 0.62, 0.67, 0.76)
      GameTooltip:AddLine("Go back in to keep recording this run.", 0.44, 0.49, 0.6, true)
    else
      GameTooltip:AddLine("Recording " .. where, 0.42, 0.82, 0.49)
    end
  else
    local view = FT.Records.view(FT.Records.currentCharKey())
    GameTooltip:AddLine(string.format("%d dungeon run%s recorded", view.totals.runs, view.totals.runs == 1 and "" or "s"), 0.62, 0.67, 0.76)
  end
  GameTooltip:AddLine("Click to show your dungeon records", 1, 1, 1)
  GameTooltip:AddLine("Drag to move this button", 0.62, 0.67, 0.76)
  GameTooltip:Show()
end

function MB.create()
  if button or not Minimap then
    return button
  end
  button = CreateFrame("Button", "ForeverTrackerMinimapButton", Minimap)
  button:SetSize(31, 31)
  button:SetFrameStrata("MEDIUM")
  button:SetFrameLevel(8)
  if button.SetFixedFrameStrata then
    button:SetFixedFrameStrata(true)
    button:SetFixedFrameLevel(true)
  end
  button:RegisterForClicks("AnyUp")
  button:RegisterForDrag("LeftButton")
  button:SetHighlightTexture(136477) -- Interface\Minimap\UI-Minimap-ZoomButton-Highlight

  local background = button:CreateTexture(nil, "BACKGROUND")
  background:SetTexture(136467) -- Interface\Minimap\UI-Minimap-Background
  background:SetSize(24, 24)
  background:SetPoint("CENTER", 0, 1)
  local icon = button:CreateTexture(nil, "ARTWORK")
  icon:SetTexture(ICON)
  icon:SetSize(20, 20)
  icon:SetPoint("CENTER", 0, 1)
  button.icon = icon
  local border = button:CreateTexture(nil, "OVERLAY")
  border:SetTexture(136430) -- Interface\Minimap\MiniMap-TrackingBorder
  border:SetSize(50, 50)
  border:SetPoint("TOPLEFT")

  button:SetScript("OnClick", function()
    FT.RecordsUI.toggle()
  end)
  -- The icon dips while pressed, like the minimap's own buttons.
  button:SetScript("OnMouseDown", function()
    icon:ClearAllPoints()
    icon:SetPoint("CENTER", 1, 0)
  end)
  button:SetScript("OnMouseUp", function()
    icon:ClearAllPoints()
    icon:SetPoint("CENTER", 0, 1)
  end)
  button:SetScript("OnEnter", function(self)
    if not dragging then
      MB.tooltip(self)
    end
  end)
  button:SetScript("OnLeave", function()
    GameTooltip:Hide()
  end)
  button:SetScript("OnDragStart", function(self)
    dragging = true
    GameTooltip:Hide()
    self:SetScript("OnUpdate", follow)
  end)
  button:SetScript("OnDragStop", function(self)
    dragging = false
    self:SetScript("OnUpdate", nil)
    icon:ClearAllPoints()
    icon:SetPoint("CENTER", 0, 1)
  end)

  place(settings().angle)
  if settings().hide then
    button:Hide()
  else
    button:Show()
  end
  return button
end

-- /ft minimap: show or hide the button. Returns true when it is now shown.
function MB.toggle()
  local s = settings()
  s.hide = not s.hide
  local b = MB.create()
  if b then
    if s.hide then
      b:Hide()
    else
      b:Show()
    end
  end
  return not s.hide
end

function MB.button()
  return button
end

-- The minimap's addon compartment menu (TOC: AddonCompartmentFunc / OnEnter / OnLeave).
function ForeverTracker_OnAddonCompartmentClick()
  FT.RecordsUI.toggle()
end

function ForeverTracker_OnAddonCompartmentEnter(_, menuButton)
  MB.tooltip(menuButton or UIParent)
end

function ForeverTracker_OnAddonCompartmentLeave()
  GameTooltip:Hide()
end
