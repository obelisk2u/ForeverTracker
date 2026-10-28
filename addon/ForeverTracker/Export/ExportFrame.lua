-- /ft export: show a copyable export string, so data can be submitted on the website without
-- locating the SavedVariables file (and without waiting for logout).
local _, FT = ...

local Export = {}
FT.Export = Export

-- Build the export payload. It has the same shape as ForeverTrackerDB, which the website and
-- the backend already understand.
function Export.payload(all)
  local db = FT.db
  local observations = db.observations
  local selected = {}
  local first = all and 1 or math.max(1, #observations - 49)
  for i = first, #observations do
    selected[#selected + 1] = observations[i]
  end
  local run = FT.Storage.activeRun()
  if run then
    -- Bump the revision so a later save of this still-running record is a newer revision.
    run.revision = run.revision + 1
    run.timing.last_updated_at = math.max(run.timing.last_updated_at, FT.Util.now())
  end
  return {
    format = FT.EXPORT_FORMAT,
    schema_version = FT.SCHEMA_VERSION,
    installation_id = db.installation_id,
    addon_version = FT.version,
    client = db.client,
    observations = selected,
    active_run = run,
  }
end

function Export.string(all)
  return FT.Json.encode(Export.payload(all))
end

local frame

local function build()
  local ok, f = pcall(CreateFrame, "Frame", "ForeverTrackerExportFrame", UIParent, "BasicFrameTemplateWithInset")
  if not ok then
    f = CreateFrame("Frame", "ForeverTrackerExportFrame", UIParent)
  end
  f:SetSize(560, 420)
  f:SetPoint("CENTER")
  f:SetFrameStrata("DIALOG")
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  local title = f:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
  title:SetPoint("TOP", 0, -6)
  title:SetText("ForeverTracker export: Ctrl+A, Ctrl+C, then paste on the website")
  local scroll = CreateFrame("ScrollFrame", nil, f, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 12, -32)
  scroll:SetPoint("BOTTOMRIGHT", -32, 12)
  local edit = CreateFrame("EditBox", nil, scroll)
  edit:SetMultiLine(true)
  edit:SetAutoFocus(true)
  edit:SetFontObject("ChatFontSmall")
  edit:SetWidth(500)
  edit:SetScript("OnEscapePressed", function()
    f:Hide()
  end)
  scroll:SetScrollChild(edit)
  f.edit = edit
  return f
end

function Export.show(all)
  local text = Export.string(all)
  frame = frame or build()
  frame.edit:SetText(text)
  frame.edit:HighlightText()
  frame:Show()
  return text
end
