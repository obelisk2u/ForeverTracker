-- The records window: personal dungeon records in the game, opened from the minimap button or /ft.
--
-- Two tabs: Overview (totals, personal bests, a row per dungeon) and Runs (every run, newest
-- first, with the group in a tooltip). Colours follow forevertracker.org. Only plain frames,
-- textures and font strings are used, with a fallback wherever a template might be missing.
local _, FT = ...

local UI = {}
FT.RecordsUI = UI
local Records = FT.Records

local W, H, PAD = 680, 480, 16
local CW = W - 2 * PAD
local ROW_H, HEADER_H = 20, 18
local EMBLEM = "Interface\\AddOns\\ForeverTracker\\Media\\Emblem"
local WHITE = "Interface\\Buttons\\WHITE8X8"

-- forevertracker.org's palette.
local C = {
  ink = { 0.039, 0.055, 0.086, 0.97 },
  surface = { 0.067, 0.090, 0.141, 1 },
  surface2 = { 0.090, 0.125, 0.192, 1 },
  line = { 0.149, 0.196, 0.286, 1 },
  gold = { 0.886, 0.702, 0.337 },
  text = { 0.910, 0.925, 0.957 },
  muted = { 0.620, 0.667, 0.761 },
  faint = { 0.443, 0.494, 0.596 },
  good = { 0.416, 0.820, 0.494 },
  warn = { 0.937, 0.686, 0.353 },
  bad = { 0.918, 0.451, 0.451 },
}

-- The website's labels for a run's result.
local RESULT = {
  completed = { "Completed", C.good },
  abandoned = { "Abandoned", C.bad },
  left = { "Left early", C.warn },
  disconnected = { "Disconnected", C.warn },
  unknown = { "Outcome unknown", C.muted },
}

-- Formatting --------------------------------------------------------------------------------

local function commas(n)
  local s = tostring(math.floor(n + 0.5))
  local out = string.reverse(string.gsub(string.reverse(s), "(%d%d%d)", "%1,"))
  return (string.gsub(out, "^(%-?),", "%1"))
end

function UI.number(n)
  if n == nil then
    return "-"
  end
  if n >= 1e9 then
    return string.format("%.2fB", n / 1e9)
  elseif n >= 1e6 then
    return string.format("%.2fM", n / 1e6)
  elseif n >= 1e4 then
    return string.format("%.1fK", n / 1e3)
  end
  return commas(n)
end

function UI.duration(seconds)
  if seconds == nil then
    return "-"
  end
  local s = math.floor(seconds + 0.5)
  local h, m = math.floor(s / 3600), math.floor((s % 3600) / 60)
  if h > 0 then
    return string.format("%d:%02d:%02d", h, m, s % 60)
  end
  return string.format("%d:%02d", m, s % 60)
end

function UI.totalTime(seconds)
  local m = math.floor((seconds or 0) / 60)
  if m >= 60 then
    return string.format("%dh %dm", math.floor(m / 60), m % 60)
  end
  return m .. "m"
end

-- M/D/YY, as on the website.
function UI.day(t)
  if not t then
    return "-"
  end
  return tonumber(date("%m", t)) .. "/" .. tonumber(date("%d", t)) .. "/" .. date("%y", t)
end

local function hex(c)
  return string.format("|cff%02x%02x%02x", c[1] * 255, c[2] * 255, c[3] * 255)
end

local function classHex(classFile)
  local color = classFile and RAID_CLASS_COLORS and RAID_CLASS_COLORS[classFile]
  if color and color.r then
    return hex({ color.r, color.g, color.b })
  end
  return hex(C.text)
end

local function fullName(who)
  if not who or not who.name then
    return "Unknown"
  end
  return who.surname and (who.name .. " " .. who.surname) or who.name
end

local function dungeonLabel(name, difficulty)
  name = name or "Unknown dungeon"
  if difficulty and difficulty ~= "" and difficulty ~= "Normal" then
    return name .. " " .. hex(C.faint) .. "(" .. difficulty .. ")|r"
  end
  return name
end

-- Building blocks ---------------------------------------------------------------------------

local function create(kind, name, parent, template)
  if template then
    local ok, f = pcall(CreateFrame, kind, name, parent, template)
    if ok and f then
      return f
    end
  end
  return CreateFrame(kind, name, parent)
end

-- A flat panel with a 1px border, in the site's colours.
local function paint(frame, bg, border)
  if frame.SetBackdrop then
    frame:SetBackdrop({ bgFile = WHITE, edgeFile = WHITE, edgeSize = 1 })
    frame:SetBackdropColor(bg[1], bg[2], bg[3], bg[4] or 1)
    local b = border or bg
    frame:SetBackdropBorderColor(b[1], b[2], b[3], border and (b[4] or 1) or 0)
  else
    local t = frame:CreateTexture(nil, "BACKGROUND")
    t:SetAllPoints()
    t:SetColorTexture(bg[1], bg[2], bg[3], bg[4] or 1)
  end
end

local function panel(parent, bg, border)
  local f = create("Frame", nil, parent, "BackdropTemplate")
  paint(f, bg, border)
  return f
end

local function label(parent, font, color, justify)
  local fs = parent:CreateFontString(nil, "OVERLAY", font)
  fs:SetTextColor(color[1], color[2], color[3])
  if justify then
    fs:SetJustifyH(justify)
  end
  fs:SetWordWrap(false)
  return fs
end

local function line(parent, x1, y, x2)
  local t = parent:CreateTexture(nil, "ARTWORK")
  t:SetColorTexture(C.line[1], C.line[2], C.line[3], 1)
  t:SetPoint("TOPLEFT", x1, y)
  t:SetPoint("TOPRIGHT", x2, y)
  t:SetHeight(1)
  return t
end

-- A stat tile: a small label over a big value, with an optional detail line.
local function tile(parent, x, y, w, h, title)
  local f = panel(parent, C.surface2, C.line)
  f:SetSize(w, h)
  f:SetPoint("TOPLEFT", x, y)
  f.title = label(f, "GameFontNormalSmall", C.muted, "LEFT")
  f.title:SetPoint("TOPLEFT", 10, -8)
  f.title:SetText(title)
  f.value = label(f, "GameFontHighlightLarge", C.text, "LEFT")
  f.value:SetPoint("TOPLEFT", 10, -24)
  f.value:SetPoint("TOPRIGHT", -10, -24)
  f.detail = label(f, "GameFontDisableSmall", C.faint, "LEFT")
  f.detail:SetPoint("TOPLEFT", 10, -42)
  f.detail:SetPoint("TOPRIGHT", -10, -42)
  return f
end

local function tooltipLine(left, right, color)
  local c = color or C.text
  if right then
    GameTooltip:AddDoubleLine(left, right, C.muted[1], C.muted[2], C.muted[3], c[1], c[2], c[3])
  else
    GameTooltip:AddLine(left, c[1], c[2], c[3], true)
  end
end

-- A table with a header and a fixed number of rows; the mouse wheel scrolls through the data.
-- columns: { title, x, width, justify, cell = function(item) return text, color end }
local function makeTable(parent, y, rows, columns, onEnter)
  local t = { rows = {}, offset = 0, data = {}, columns = columns }
  for _, col in ipairs(columns) do
    local h = label(parent, "GameFontNormalSmall", C.faint, col.justify or "LEFT")
    h:SetPoint("TOPLEFT", col.x, y)
    h:SetWidth(col.width)
    h:SetText(col.title)
  end
  line(parent, 0, y - HEADER_H + 4, 0)
  for i = 1, rows do
    local row = create("Button", nil, parent)
    local top = y - HEADER_H - (i - 1) * ROW_H
    row:SetHeight(ROW_H)
    row:SetPoint("TOPLEFT", 0, top)
    row:SetPoint("TOPRIGHT", 0, top)
    if i % 2 == 0 then
      local stripe = row:CreateTexture(nil, "BACKGROUND")
      stripe:SetAllPoints()
      stripe:SetColorTexture(C.surface2[1], C.surface2[2], C.surface2[3], 0.55)
    end
    local hl = row:CreateTexture(nil, "HIGHLIGHT")
    hl:SetAllPoints()
    hl:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 0.10)
    row.cells = {}
    for c, col in ipairs(columns) do
      local fs = label(row, "GameFontHighlightSmall", C.text, col.justify or "LEFT")
      fs:SetPoint("LEFT", col.x, 0)
      fs:SetWidth(col.width)
      row.cells[c] = fs
    end
    row:SetScript("OnEnter", function(self)
      if self.item and onEnter then
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        onEnter(self.item)
        GameTooltip:Show()
      end
    end)
    row:SetScript("OnLeave", function()
      GameTooltip:Hide()
    end)
    t.rows[i] = row
  end
  t.count = label(parent, "GameFontDisableSmall", C.faint, "RIGHT")
  t.count:SetPoint("TOPRIGHT", 0, y - HEADER_H - rows * ROW_H - 4)

  function t.render()
    local max = math.max(0, #t.data - rows)
    t.offset = math.max(0, math.min(t.offset, max))
    for i, row in ipairs(t.rows) do
      local item = t.data[t.offset + i]
      row.item = item or false
      if item then
        for c, col in ipairs(t.columns) do
          local text, color = col.cell(item)
          local fs = row.cells[c]
          fs:SetText(text or "")
          local tc = color or C.text
          fs:SetTextColor(tc[1], tc[2], tc[3])
        end
        row:Show()
      else
        row:Hide()
      end
    end
    if #t.data > rows then
      t.count:SetText(string.format("%d-%d of %d  (scroll for more)", t.offset + 1, math.min(t.offset + rows, #t.data), #t.data))
    else
      t.count:SetText("")
    end
  end

  function t.set(data)
    t.data = data
    t.offset = 0
    t.render()
  end

  parent:EnableMouseWheel(true)
  parent:SetScript("OnMouseWheel", function(_, delta)
    t.offset = t.offset - delta * 3
    t.render()
  end)
  return t
end

-- Tabs --------------------------------------------------------------------------------------

local function overviewTab(content)
  local page = create("Frame", nil, content)
  page:SetAllPoints()
  local w = (CW - 3 * 8) / 4
  page.tiles = {
    runs = tile(page, 0, 0, w, 50, "Runs"),
    completed = tile(page, w + 8, 0, w, 50, "Completed"),
    bosses = tile(page, 2 * (w + 8), 0, w, 50, "Bosses killed"),
    time = tile(page, 3 * (w + 8), 0, w, 50, "Time in dungeons"),
  }
  local bestsTitle = label(page, "GameFontNormal", C.gold, "LEFT")
  bestsTitle:SetPoint("TOPLEFT", 0, -62)
  bestsTitle:SetText("Personal bests")
  page.bests = {
    fastest = tile(page, 0, -80, w, 58, "Fastest clear"),
    dps = tile(page, w + 8, -80, w, 58, "Highest DPS"),
    damage = tile(page, 2 * (w + 8), -80, w, 58, "Most damage in a run"),
    healing = tile(page, 3 * (w + 8), -80, w, 58, "Most healing in a run"),
  }
  local byTitle = label(page, "GameFontNormal", C.gold, "LEFT")
  byTitle:SetPoint("TOPLEFT", 0, -150)
  byTitle:SetText("By dungeon")
  page.table = makeTable(page, -170, 8, {
    { title = "Dungeon", x = 6, width = 236, cell = function(d) return dungeonLabel(d.name, d.difficulty) end },
    { title = "Runs", x = 248, width = 50, justify = "RIGHT", cell = function(d) return commas(d.runs) end },
    { title = "Completed", x = 304, width = 70, justify = "RIGHT", cell = function(d) return commas(d.completed) end },
    { title = "Fastest", x = 380, width = 70, justify = "RIGHT", cell = function(d) return d.fastest and UI.duration(d.fastest.value) or "-" end },
    { title = "Best DPS", x = 456, width = 80, justify = "RIGHT", cell = function(d) return d.dps and UI.number(d.dps.value) or "-" end },
    { title = "Last run", x = 542, width = 98, justify = "RIGHT", cell = function(d) return UI.day(d.last_at), C.muted end },
  }, function(d)
    tooltipLine(d.name or "Unknown dungeon", nil, C.gold)
    if d.difficulty then
      tooltipLine(d.difficulty, nil, C.faint)
    end
    tooltipLine("Runs", commas(d.runs))
    tooltipLine("Completed", commas(d.completed))
    tooltipLine("Bosses killed", commas(d.bosses))
    tooltipLine("Your deaths", commas(d.deaths))
    tooltipLine("Time inside", UI.totalTime(d.time))
    if d.damage then
      tooltipLine("Most damage", UI.number(d.damage.value))
    end
    if d.healing then
      tooltipLine("Most healing", UI.number(d.healing.value))
    end
    if d.hps then
      tooltipLine("Best HPS", UI.number(d.hps.value))
    end
  end)

  function page.update(view)
    local t = view.totals
    page.tiles.runs.value:SetText(commas(t.runs))
    page.tiles.completed.value:SetText(commas(t.completed))
    page.tiles.bosses.value:SetText(commas(t.bosses))
    page.tiles.time.value:SetText(UI.totalTime(t.time))
    for key, f in pairs(page.bests) do
      local b = view.bests[key]
      if b then
        f.value:SetText(key == "fastest" and UI.duration(b.value) or UI.number(b.value))
        f.detail:SetText((b.dungeon or "") .. "  " .. UI.day(b.at))
      else
        f.value:SetText("-")
        f.detail:SetText(key == "fastest" and "No completed run yet" or "No data yet")
      end
    end
    page.table.set(view.dungeons)
  end
  return page
end

local function runsTab(content)
  local page = create("Frame", nil, content)
  page:SetAllPoints()
  page.table = makeTable(page, 0, 15, {
    { title = "Date", x = 6, width = 58, cell = function(s) return UI.day(s.ended_at), C.muted end },
    { title = "Dungeon", x = 68, width = 196, cell = function(s) return dungeonLabel(s.dungeon, s.difficulty) end },
    { title = "Result", x = 268, width = 96, cell = function(s)
      local r = RESULT[s.result] or RESULT.unknown
      return r[1], r[2]
    end },
    { title = "Time", x = 368, width = 52, justify = "RIGHT", cell = function(s) return UI.duration(s.duration) end },
    { title = "Bosses", x = 424, width = 46, justify = "RIGHT", cell = function(s) return commas(s.bosses) end },
    { title = "Deaths", x = 474, width = 44, justify = "RIGHT", cell = function(s)
      return commas(s.deaths), s.deaths > 0 and C.bad or C.muted
    end },
    { title = "Damage", x = 522, width = 58, justify = "RIGHT", cell = function(s) return UI.number(s.damage) end },
    { title = "Healing", x = 584, width = 58, justify = "RIGHT", cell = function(s) return UI.number(s.healing) end },
  }, function(s)
    local r = RESULT[s.result] or RESULT.unknown
    tooltipLine(s.dungeon or "Unknown dungeon", nil, C.gold)
    tooltipLine(UI.day(s.ended_at) .. (s.difficulty and ("  " .. s.difficulty) or ""), nil, C.faint)
    tooltipLine("Result", r[1], r[2])
    if s.result == "completed" and s.final_boss then
      tooltipLine("The final boss was killed.", nil, C.faint)
    elseif s.result == "left" or s.result == "disconnected" then
      tooltipLine("No completion event was seen. That does not mean the group failed.", nil, C.faint)
    end
    tooltipLine("Time inside", UI.duration(s.duration))
    tooltipLine("Bosses killed", commas(s.bosses) .. (s.wipes > 0 and string.format("  (%d wipe%s)", s.wipes, s.wipes == 1 and "" or "s") or ""))
    tooltipLine("Your deaths", commas(s.deaths) .. string.format("  (group: %d)", s.party_deaths or 0))
    if s.damage then
      local dps = Records.rate(s, s.damage)
      tooltipLine("Damage", UI.number(s.damage) .. (dps and ("  (" .. UI.number(dps) .. " DPS)") or ""))
    end
    if s.healing then
      local hps = Records.rate(s, s.healing)
      tooltipLine("Healing", UI.number(s.healing) .. (hps and ("  (" .. UI.number(hps) .. " HPS)") or ""))
    end
    if s.interrupts then
      tooltipLine("Interrupts", commas(s.interrupts))
    end
    if s.party and #s.party > 0 then
      GameTooltip:AddLine(" ")
      tooltipLine("Group", nil, C.muted)
      for _, p in ipairs(s.party) do
        local role = (p.role == "TANK" and "Tank") or (p.role == "HEALER" and "Healer") or nil
        GameTooltip:AddDoubleLine(classHex(p.class_file) .. fullName(p) .. "|r", role or "", 1, 1, 1, C.faint[1], C.faint[2], C.faint[3])
      end
    end
  end)

  function page.update(view)
    page.table.set(view.history)
  end
  return page
end

-- The window --------------------------------------------------------------------------------

local frame

local function selectTab(name)
  UI.tab = name
  for key, tab in pairs(frame.tabs) do
    local active = key == name
    local c = active and C.gold or C.muted
    tab.text:SetTextColor(c[1], c[2], c[3])
    if active then
      tab.underline:Show()
      frame.pages[key]:Show()
    else
      tab.underline:Hide()
      frame.pages[key]:Hide()
    end
  end
end

local function makeTab(parent, key, text, x)
  local tab = create("Button", nil, parent)
  tab:SetSize(84, 24)
  tab:SetPoint("TOPLEFT", x, -52)
  tab.text = label(tab, "GameFontNormal", C.muted, "CENTER")
  tab.text:SetPoint("CENTER", 0, 1)
  tab.text:SetText(text)
  tab.underline = tab:CreateTexture(nil, "ARTWORK")
  tab.underline:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 1)
  tab.underline:SetPoint("BOTTOMLEFT", 8, -2)
  tab.underline:SetPoint("BOTTOMRIGHT", -8, -2)
  tab.underline:SetHeight(2)
  tab:SetScript("OnClick", function()
    selectTab(key)
  end)
  return tab
end

local function build()
  local f = create("Frame", "ForeverTrackerRecordsFrame", UIParent, "BackdropTemplate")
  paint(f, C.ink, C.line)
  f:SetSize(W, H)
  f:SetPoint("CENTER")
  f:SetFrameStrata("HIGH")
  f:SetToplevel(true)
  f:SetClampedToScreen(true)
  f:SetMovable(true)
  f:EnableMouse(true)
  f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving)
  f:SetScript("OnDragStop", f.StopMovingOrSizing)
  f:Hide()
  if UISpecialFrames then
    table.insert(UISpecialFrames, "ForeverTrackerRecordsFrame") -- Esc closes it
  end

  local emblem = f:CreateTexture(nil, "ARTWORK")
  emblem:SetTexture(EMBLEM)
  emblem:SetSize(30, 30)
  emblem:SetPoint("TOPLEFT", PAD, -12)
  local title = label(f, "GameFontNormalLarge", C.gold, "LEFT")
  title:SetPoint("TOPLEFT", emblem, "TOPRIGHT", 10, 1)
  title:SetText("ForeverTracker")
  f.subtitle = label(f, "GameFontHighlightSmall", C.muted, "LEFT")
  f.subtitle:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -3)

  local close = create("Button", nil, f, "UIPanelCloseButton")
  close:SetPoint("TOPRIGHT", -4, -4)
  close:SetScript("OnClick", function()
    f:Hide()
  end)

  -- This character / all characters.
  local scope = create("Button", nil, f, "BackdropTemplate")
  paint(scope, C.surface2, C.line)
  scope:SetSize(128, 22)
  scope:SetPoint("TOPRIGHT", -40, -16)
  scope.text = label(scope, "GameFontHighlightSmall", C.text, "CENTER")
  scope.text:SetPoint("CENTER")
  scope:SetScript("OnClick", function()
    UI.scope = (UI.scope == "all") and "character" or "all"
    UI.refresh()
  end)
  scope:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    tooltipLine("Show this character's records or every character's on this account.", nil, C.text)
    GameTooltip:Show()
  end)
  scope:SetScript("OnLeave", function()
    GameTooltip:Hide()
  end)
  f.scope = scope

  f.tabs = { overview = makeTab(f, "overview", "Overview", PAD - 8), runs = makeTab(f, "runs", "Runs", PAD + 80) }
  line(f, PAD, -79, -PAD)

  local content = create("Frame", nil, f)
  content:SetPoint("TOPLEFT", PAD, -90)
  content:SetPoint("BOTTOMRIGHT", -PAD, 34)
  f.content = content
  f.pages = { overview = overviewTab(content), runs = runsTab(content) }

  f.empty = create("Frame", nil, f)
  f.empty:SetAllPoints(content)
  local emptyTitle = label(f.empty, "GameFontHighlightLarge", C.text, "CENTER")
  emptyTitle:SetPoint("CENTER", 0, 24)
  emptyTitle:SetText("No dungeon runs yet")
  local emptyText = label(f.empty, "GameFontHighlight", C.muted, "CENTER")
  emptyText:SetPoint("TOP", emptyTitle, "BOTTOM", 0, -10)
  emptyText:SetWidth(440)
  emptyText:SetWordWrap(true)
  emptyText:SetText("Enter a dungeon and ForeverTracker records the run automatically. Your runs and personal bests show up here.")

  local footer = label(f, "GameFontDisableSmall", C.faint, "CENTER")
  footer:SetPoint("BOTTOM", 0, 13)
  footer:SetText("Every run with your whole group, and everyone you've played with: forevertracker.org")

  f:SetScript("OnShow", function()
    UI.refresh()
  end)
  return f
end

function UI.refresh()
  if not frame or not frame:IsShown() then
    return
  end
  local me = Records.currentCharKey()
  if not me then
    UI.scope = "all"
  end
  local charKey = (UI.scope ~= "all") and me or nil
  local view = Records.view(charKey)

  local who
  if charKey then
    local c = Records.character(charKey) or FT.Identity.player()
    who = c and fullName(c) or "This character"
  else
    who = "All characters"
  end
  local status = ""
  local run = FT.Storage.activeRun()
  if run and run.instance then
    local where = run.instance.name or "this dungeon"
    local st = FT.db.active_state
    if st and st.phase == "suspended" then
      -- Outside the dungeon: the run stays open a while in case the player goes back in.
      status = "   " .. hex(C.muted) .. "Paused: " .. where .. "|r"
    else
      status = "   " .. hex(C.good) .. "Recording " .. where .. "|r"
    end
  end
  frame.subtitle:SetText("Dungeon records  " .. hex(C.faint) .. "/|r  " .. who .. status)
  frame.scope.text:SetText(charKey and "This character" or "All characters")

  local hasRuns = view.totals.runs > 0
  if hasRuns then
    frame.empty:Hide()
    frame.content:Show()
  else
    frame.empty:Show()
    frame.content:Hide()
  end
  frame.pages.overview.update(view)
  frame.pages.runs.update(view)
  selectTab(UI.tab or "overview")
  return view
end

function UI.show()
  frame = frame or build()
  frame:Show()
  UI.refresh()
end

function UI.toggle()
  if frame and frame:IsShown() then
    frame:Hide()
  else
    UI.show()
  end
end

function UI.isShown()
  return frame ~= nil and frame:IsShown()
end

function UI.frame()
  return frame
end
