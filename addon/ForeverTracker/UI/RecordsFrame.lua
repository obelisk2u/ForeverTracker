-- The records window: personal dungeon records in the game, opened from the minimap button or /ft.
--
-- Three tabs: Overview (totals, personal bests, a row per dungeon), Runs (every run, newest
-- first, with the group in a tooltip) and Scoreboard (everyone in the current or last run with
-- the damage meter's numbers, updated on its own after each fight). Colours follow
-- forevertracker.org. Only plain frames, textures and font strings are used, with a fallback
-- wherever a template might be missing.
local _, FT = ...

local UI = {}
FT.RecordsUI = UI
local Records = FT.Records
local Safe = FT.Safe
local frame -- the window, built the first time it opens

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
-- columns: { title, x, width, justify, sort, cell = function(item) return text, color end }
-- With onSort, a click on the header of a column that has `sort` calls onSort(col.sort).
local function makeTable(parent, y, rows, columns, onEnter, onSort)
  local t = { rows = {}, offset = 0, data = {}, columns = columns, headers = {}, sortButtons = {} }
  for i, col in ipairs(columns) do
    local h = label(parent, "GameFontNormalSmall", C.faint, col.justify or "LEFT")
    h:SetPoint("TOPLEFT", col.x, y)
    h:SetWidth(col.width)
    h:SetText(col.title)
    t.headers[i] = h
    if onSort and col.sort then
      local b = create("Button", nil, parent)
      b:SetPoint("TOPLEFT", col.x, y + 3)
      b:SetSize(col.width, HEADER_H - 2)
      b:SetScript("OnClick", function()
        onSort(col.sort)
      end)
      t.sortButtons[col.sort] = b
    end
  end

  -- The header of the column the data is sorted by is gold.
  function t.markSort(key)
    for i, col in ipairs(columns) do
      local c = (key and col.sort == key) and C.gold or C.faint
      t.headers[i]:SetTextColor(c[1], c[2], c[3])
    end
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
          -- A cell may hold a secret (the live scoreboard): it goes straight to SetText, never
          -- tested or compared, since even `text == nil` throws on a secret.
          local text, color = col.cell(item)
          if not Safe.isSecret(text) and text == nil then
            text = ""
          end
          local fs = row.cells[c]
          fs:SetText(text)
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

-- Scoreboard --------------------------------------------------------------------------------
-- Everyone in the run with the damage meter's numbers, for the whole run so far or the last
-- fight. Out of combat the numbers are the meter collector's (it calls UI.onFight after reading
-- each fight). During a fight the board shows that fight live: every LIVE_SECONDS it asks the
-- meter for the current session, whose numbers (and maybe names) are secret then. Secrets are
-- only handed to SetText, through the client's AbbreviateNumbers, as Details! does: never
-- compared, added or tested. Each number goes in its person's row by GUID or name when those
-- are readable, else by "this is the player" and by class when only one member has it; the
-- meter lists each type already ranked, so the rows sort by that rank.

local ROLE = { TANK = "Tank", HEALER = "Healer", DAMAGER = "Damage" }

-- The last fight of the run that just ended, kept in memory: once a run ends its per-fight
-- numbers are gone from the saved data (the whole-run totals stay).
local lastFight

local function present(entry)
  local p = entry.presence and entry.presence[#entry.presence]
  return p ~= nil and p["end"] == nil
end

UI.LIVE_SECONDS = 0.5
-- After combat the live numbers stay up until the meter collector has read the fight, or this long.
UI.LIVE_HOLD_SECONDS = 15
local LIVE_TYPES = {
  { "damage_done", "DamageDone" },
  { "healing_done", "HealingDone" },
  { "interrupts", "Interrupts" },
  { "dispels", "Dispels" },
  { "damage_taken", "DamageTaken" },
}
-- { run_id, started_at, ended_at, values = { [ref] = { [metric] = { value, rate, rank } } }, unplaced }
UI.live = nil
local liveTicker

-- The client's number format set to match UI.number (45.0K, 1.25M), as Details! sets its own;
-- false when the client has no CreateAbbreviateConfig (its default format is used then).
local liveFormat
local function abbreviateOptions()
  if liveFormat == nil then
    liveFormat = false
    local create = _G.CreateAbbreviateConfig
    if create then
      local ok, config = pcall(create, {
        { breakpoint = 1e9, abbreviation = "B", significandDivisor = 1e7, fractionDivisor = 100, abbreviationIsGlobal = false },
        { breakpoint = 1e6, abbreviation = "M", significandDivisor = 1e4, fractionDivisor = 100, abbreviationIsGlobal = false },
        { breakpoint = 1e4, abbreviation = "K", significandDivisor = 100, fractionDivisor = 10, abbreviationIsGlobal = false },
        { breakpoint = 0.000001, abbreviation = "", significandDivisor = 1, fractionDivisor = 1, abbreviationIsGlobal = false },
      })
      if ok and type(config) ~= "nil" then
        liveFormat = { config = config }
      end
    end
  end
  return liveFormat or nil
end

-- A number for a live cell: a secret goes through the client's own formatting untouched.
local function liveNumber(x, isCount)
  if Safe.isSecret(x) then
    local abbreviate = _G.AbbreviateNumbers
    if abbreviate then
      local options = abbreviateOptions()
      local ok, s = false, nil
      if options then
        ok, s = pcall(abbreviate, x, options)
      end
      if not ok then
        ok, s = pcall(abbreviate, x)
      end
      if ok then
        return s
      end
    end
    return "..."
  end
  if type(x) ~= "number" then
    return "-"
  end
  return isCount and commas(x) or UI.number(x)
end

-- Which roster entry a live meter source is, without comparing anything secret.
local function liveRef(run, st, src, observer, byClass)
  local guid, name = src.sourceGUID, src.name
  if not Safe.isSecret(guid) and type(guid) == "string" then
    local ref = FT.Roster.refForGuid(st, guid)
    if ref then
      return ref
    end
  end
  if not Safe.isSecret(name) and type(name) == "string" then
    local ref = FT.Roster.refForName(run, name)
    if ref then
      return ref
    end
  end
  local me = src.isLocalPlayer
  if not Safe.isSecret(me) and me == true then
    return observer
  end
  local class = src.classFilename
  if not Safe.isSecret(class) and type(class) == "string" then
    return byClass[class]
  end
  return nil
end

-- Read the current fight from the meter into UI.live.
local function readLive(run, st, live)
  local get = Safe.api("C_DamageMeter.GetCombatSessionFromType")
  local types = Enum and Enum.DamageMeterType
  local current = Enum and Enum.DamageMeterSessionType and Enum.DamageMeterSessionType.Current
  if not (get and types) or current == nil then
    live.unavailable = true
    return
  end
  -- A class only one member in the group has tells who a nameless source is.
  local classes, byClass = {}, {}
  for _, entry in ipairs(run.roster or {}) do
    if entry.class_file and present(entry) then
      classes[entry.class_file] = (classes[entry.class_file] or 0) + 1
      byClass[entry.class_file] = entry.ref
    end
  end
  for class, n in pairs(classes) do
    if n > 1 then
      byClass[class] = nil
    end
  end
  local observer = FT.Roster.observerRef(run)
  local values, unplaced = {}, 0
  for _, t in ipairs(LIVE_TYPES) do
    local typeId = types[t[2]]
    if typeId ~= nil then
      local ok, session = pcall(get, current, typeId)
      local sources = nil
      if ok and type(session) == "table" and not Safe.isSecretTable(session) then
        sources = session.combatSources
      end
      if type(sources) == "table" and not Safe.isSecretTable(sources) then
        for i, src in ipairs(sources) do
          if type(src) == "table" and not Safe.isSecretTable(src) then
            local ref = liveRef(run, st, src, observer, byClass)
            if ref then
              values[ref] = values[ref] or {}
              values[ref][t[1]] = { value = src.totalAmount, rate = src.amountPerSecond, rank = i }
            else
              unplaced = unplaced + 1
            end
          end
        end
      end
    end
  end
  live.values, live.unplaced = values, unplaced
end

local function presentSeconds(entry, now)
  local total = 0
  for _, p in ipairs(entry.presence or {}) do
    total = total + math.max(0, (p["end"] or now) - (p.start or now))
  end
  return total
end

-- The newest fight the meter collector has read for this run, or nil.
local function lastFightOf(run, m)
  if not (run and m and m.status) then
    return nil
  end
  local last
  for id, status in pairs(m.status) do
    if status == "captured" and type(id) == "number" and (last == nil or id > last) then
      last = id
    end
  end
  if not last then
    return nil
  end
  local seconds = m.durations and m.durations[last]
  local ended = (m.ended_at and m.ended_at[last]) or (m.captured_at and m.captured_at[last])
  local i = FT.Meter.attemptFor(run, m, last)
  local e = i and run.encounters[i]
  local name = "Trash"
  if e then
    name = (e.name or "Boss") .. ((e.success == true and " (kill)") or (e.success == false and " (wipe)") or "")
  end
  return {
    run_id = run.observation_id,
    values = (m.values and m.values[last]) or {},
    seconds = seconds,
    name = name,
    -- Deaths in the fight, with the same slack the meter collector uses to place a fight.
    from = (ended and seconds) and (ended - seconds - 2) or nil,
    to = ended and (ended + 1) or nil,
  }
end

-- Whole-run values per unit ref, from the meter collector's run totals.
local function runValues(run)
  local values = {}
  for _, t in ipairs((run.meter and run.meter.totals) or {}) do
    local v = {}
    for metric, m in pairs(t.metrics or {}) do
      if type(m) == "table" and type(m.value) == "number" then
        v[metric] = m.value
      end
    end
    if next(v) then
      values[t.unit_ref] = v
    end
  end
  return values
end

local function sortMetric(key)
  return (key == "dps" and "damage_done") or (key == "hps" and "healing_done") or key
end

local function sortValue(r, key)
  if key == "deaths" then
    return r.deaths or -1
  end
  return r.values[sortMetric(key)] or -1
end

-- Live, the meter's rank in that type's list (1 = most); rows it has not listed go last.
local function liveRank(r, key)
  local v = r.liveValues and r.liveValues[sortMetric(key)]
  return v and v.rank or math.huge
end

-- The current run (or the last one) as rows for the board, or nil before the first run.
function UI.scoreboard()
  local run = FT.Storage.activeRun()
  local active = run ~= nil
  if not run then
    local obs = (FT.db and FT.db.observations) or {}
    for i = #obs, 1, -1 do
      if type(obs[i]) == "table" and obs[i].type == "dungeon_run" then
        run = obs[i]
        break
      end
    end
  end
  if not run then
    return nil
  end
  local st = active and FT.db.active_state or nil
  local board = { run = run, active = active, view = UI.scoreView or "run", sort = UI.scoreSort or "damage_done" }
  local fight = active and lastFightOf(run, st and st.meter) or nil
  if not active and lastFight and lastFight.run_id == run.observation_id then
    fight = lastFight
  end
  board.fight = fight
  board.meterStatus = run.meter and run.meter.status
  local live = active and UI.live and UI.live.run_id == run.observation_id and UI.live or nil
  board.liveFight = live
  local values, window
  if live then
    -- Rows and deaths for the fight under way; the numbers come from live.values.
    values, board.seconds = runValues(run), nil
    window = { live.started_at, math.huge }
  elseif board.view == "fight" then
    values, board.seconds = fight and fight.values or {}, fight and fight.seconds
    window = (fight and fight.from and fight.to) and { fight.from, fight.to } or false
  else
    values, board.seconds = runValues(run), run.meter and run.meter.combat_seconds
  end
  board.hasNumbers = next(values) ~= nil

  -- Deaths come from the run's own death records, as in the run summaries.
  local deaths = {}
  if window ~= false then
    for _, d in ipairs(run.deaths or {}) do
      if not window or (d.at >= window[1] and d.at <= window[2]) then
        deaths[d.unit_ref] = (deaths[d.unit_ref] or 0) + 1
      end
    end
  end

  -- Everyone in the group now, in it for a while, or who did something; not someone who only
  -- passed through (in the group for a moment, then replaced).
  local rows = {}
  local now = FT.Util.now()
  for _, entry in ipairs(run.roster or {}) do
    local v = values[entry.ref]
    local did = deaths[entry.ref] ~= nil
    for _, n in pairs(v or {}) do
      did = did or n > 0
    end
    local liveValues = live and live.values[entry.ref] or nil
    local stayed = presentSeconds(entry, now) >= FT.Records.PASSED_THROUGH_SECONDS
    if entry.name and (did or stayed or liveValues or entry.is_observer or (active and present(entry))) then
      local dead = deaths[entry.ref]
      if dead == nil and window ~= false and (board.hasNumbers or live) then
        dead = 0
      end
      rows[#rows + 1] = {
        name = entry.name,
        surname = entry.surname,
        class_file = entry.class_file,
        role = entry.role,
        values = v or {},
        liveValues = live and (liveValues or {}) or nil,
        deaths = (window ~= false) and dead or nil,
        seconds = board.seconds,
      }
    end
  end
  local key = board.sort
  table.sort(rows, function(a, b)
    if key == "name" then
      return fullName(a) < fullName(b)
    end
    if live and key ~= "deaths" then
      local ra, rb = liveRank(a, key), liveRank(b, key)
      if ra ~= rb then
        return ra < rb
      end
      return fullName(a) < fullName(b)
    end
    local va, vb = sortValue(a, key), sortValue(b, key)
    if va ~= vb then
      return va > vb
    end
    return fullName(a) < fullName(b)
  end)
  board.rows = rows
  return board
end

-- Called after the meter collector reads the fights that just ended (Meter.capturePass). The
-- live numbers give way once nothing is left secret, or after LIVE_HOLD_SECONDS.
function UI.onFight(run, st)
  local fight = lastFightOf(run, st and st.meter)
  if fight then
    lastFight = fight
  end
  local live = UI.live
  if live and live.ended_at then
    local waiting = false
    for _, status in pairs((st and st.meter and st.meter.status) or {}) do
      waiting = waiting or status == "secret"
    end
    if not waiting or FT.Util.now() - live.ended_at >= UI.LIVE_HOLD_SECONDS then
      UI.live = nil
    end
  end
  UI.refreshScoreboard()
end

-- Re-read the fight under way, only while the scoreboard is on screen.
function UI.refreshLive()
  local live = UI.live
  local run, st = FT.Storage.activeRun(), FT.db and FT.db.active_state
  if not (live and run and st) or live.run_id ~= run.observation_id then
    return
  end
  if not (frame and frame:IsShown() and frame.pages.scoreboard:IsShown()) then
    return
  end
  readLive(run, st, live)
  frame.pages.scoreboard.update(UI.scoreboard())
end

-- PLAYER_REGEN_DISABLED during a run: the board follows the fight live.
function UI.combatStarted()
  local run = FT.Storage.activeRun()
  if not run then
    return
  end
  UI.live = { run_id = run.observation_id, started_at = FT.Util.now(), values = {}, unplaced = 0 }
  if liveTicker then
    liveTicker:Cancel()
  end
  liveTicker = FT.Events.ticker(UI.LIVE_SECONDS, "records", UI.refreshLive)
  UI.refreshLive()
  UI.refreshScoreboard()
end

-- PLAYER_REGEN_ENABLED: one last read; the numbers stay up until the fight has been read.
function UI.combatEnded()
  if liveTicker then
    liveTicker:Cancel()
    liveTicker = nil
  end
  local live = UI.live
  if live and not live.ended_at then
    UI.refreshLive()
    live.ended_at = FT.Util.now()
  end
end

local function rate(amount, seconds)
  if amount and seconds and seconds > 0 then
    return amount / seconds
  end
  return nil
end

local function stat(n)
  return n and UI.number(n) or "-"
end

local function count(n)
  return n and commas(n) or "-"
end

-- A cell's text: kind is "total", "rate" (per second) or "count". Live, the fight's own value
-- (maybe secret, see liveNumber); otherwise the board's.
local function cellText(r, metric, kind)
  if r.liveValues then
    local v = r.liveValues[metric]
    if not v then
      return "-"
    end
    local x
    if kind == "rate" then
      x = v.rate
    else
      x = v.value
    end
    return liveNumber(x, kind == "count")
  end
  local n = r.values[metric]
  if kind == "rate" then
    return stat(rate(n, r.seconds))
  elseif kind == "count" then
    return count(n)
  end
  return stat(n)
end

local function scoreboardTab(content)
  local page = create("Frame", nil, content)
  page:SetAllPoints()

  local function chip(text, x, view)
    local b = create("Button", nil, page, "BackdropTemplate")
    paint(b, C.surface2, C.line)
    b:SetSize(96, 22)
    b:SetPoint("TOPLEFT", x, 0)
    b.text = label(b, "GameFontHighlightSmall", C.muted, "CENTER")
    b.text:SetPoint("CENTER")
    b.text:SetText(text)
    b:SetScript("OnClick", function()
      UI.scoreView = view
      UI.live = nil -- picked mid-fight: that view instead of the live one, until the next fight
      UI.refreshScoreboard()
    end)
    function b.select(active)
      local c = active and C.gold or C.muted
      b.text:SetTextColor(c[1], c[2], c[3])
      if b.SetBackdropBorderColor then
        local bc = active and C.gold or C.line
        b:SetBackdropBorderColor(bc[1], bc[2], bc[3], 1)
      end
    end
    return b
  end
  page.chips = { run = chip("Whole run", 0, "run"), fight = chip("Last fight", 104, "fight") }

  -- For a run that does not end on its own: stops recording it, claiming nothing (whether it was
  -- completed is inferred as usual). The first click asks; a second within 5 seconds ends it.
  local done = create("Button", nil, page, "BackdropTemplate")
  paint(done, C.surface2, C.line)
  done:SetSize(150, 22)
  done:SetPoint("TOPRIGHT", 0, 0)
  done.text = label(done, "GameFontHighlightSmall", C.muted, "CENTER")
  done.text:SetPoint("CENTER")
  local armed -- the pending first click, if any
  function done.reset()
    armed = nil
    done.text:SetText("End run")
    done.text:SetTextColor(C.muted[1], C.muted[2], C.muted[3])
  end
  done:SetScript("OnClick", function()
    if armed then
      done.reset()
      UI.endRun()
      return
    end
    local token = {}
    armed = token
    done.text:SetText("Click again to end it")
    done.text:SetTextColor(C.gold[1], C.gold[2], C.gold[3])
    FT.Events.after(5, "records", function()
      if armed == token then
        done.reset()
      end
    end)
  end)
  done:SetScript("OnEnter", function(self)
    GameTooltip:SetOwner(self, "ANCHOR_BOTTOM")
    tooltipLine("End run", nil, C.text)
    tooltipLine("Stops recording this run now, for when it doesn't end on its own. Whether you finished it is worked out as usual, from the dungeon's last boss. It uploads after your next /reload or logout.", nil, C.faint)
    GameTooltip:Show()
  end)
  done:SetScript("OnLeave", function()
    GameTooltip:Hide()
  end)
  done.reset()
  done:Hide()
  page.complete = done

  page.summary = label(page, "GameFontHighlightSmall", C.muted, "LEFT")
  page.summary:SetPoint("TOPLEFT", 0, -32)
  page.summary:SetPoint("TOPRIGHT", 0, -32)

  page.table = makeTable(page, -52, 12, {
    { title = "Name", x = 6, width = 150, sort = "name", cell = function(r)
      return classHex(r.class_file) .. fullName(r) .. "|r"
    end },
    { title = "Damage", x = 160, width = 62, justify = "RIGHT", sort = "damage_done", cell = function(r)
      return cellText(r, "damage_done", "total")
    end },
    { title = "DPS", x = 226, width = 52, justify = "RIGHT", sort = "dps", cell = function(r)
      return cellText(r, "damage_done", "rate"), C.muted
    end },
    { title = "Healing", x = 282, width = 62, justify = "RIGHT", sort = "healing_done", cell = function(r)
      return cellText(r, "healing_done", "total")
    end },
    { title = "HPS", x = 348, width = 52, justify = "RIGHT", sort = "hps", cell = function(r)
      return cellText(r, "healing_done", "rate"), C.muted
    end },
    { title = "Interrupts", x = 404, width = 62, justify = "RIGHT", sort = "interrupts", cell = function(r)
      return cellText(r, "interrupts", "count")
    end },
    { title = "Dispels", x = 470, width = 48, justify = "RIGHT", sort = "dispels", cell = function(r)
      return cellText(r, "dispels", "count")
    end },
    { title = "Dmg taken", x = 522, width = 66, justify = "RIGHT", sort = "damage_taken", cell = function(r)
      return cellText(r, "damage_taken", "total")
    end },
    { title = "Deaths", x = 592, width = 48, justify = "RIGHT", sort = "deaths", cell = function(r)
      return count(r.deaths), (r.deaths or 0) > 0 and C.bad or C.muted
    end },
  }, function(r)
    tooltipLine(classHex(r.class_file) .. fullName(r) .. "|r", nil, C.text)
    if ROLE[r.role] then
      tooltipLine(ROLE[r.role], nil, C.faint)
    end
    if r.liveValues then
      -- Live numbers may be secret; they never go into the shared tooltip.
      tooltipLine("This fight's numbers are on the board. Absorbs and avoidable damage show once it ends.", nil, C.faint)
      return
    end
    local v = r.values
    local dps, hps = rate(v.damage_done, r.seconds), rate(v.healing_done, r.seconds)
    tooltipLine("Damage", stat(v.damage_done) .. (dps and ("  (" .. UI.number(dps) .. " DPS)") or ""))
    tooltipLine("Healing", stat(v.healing_done) .. (hps and ("  (" .. UI.number(hps) .. " HPS)") or ""))
    tooltipLine("Absorbs", stat(v.absorbs))
    tooltipLine("Interrupts", count(v.interrupts))
    tooltipLine("Dispels", count(v.dispels))
    tooltipLine("Damage taken", stat(v.damage_taken))
    tooltipLine("Avoidable damage taken", stat(v.avoidable_damage_taken))
    tooltipLine("Deaths", count(r.deaths))
  end, function(key)
    UI.scoreSort = key
    UI.refreshScoreboard()
  end)

  page.note = label(page, "GameFontDisableSmall", C.faint, "LEFT")
  page.note:SetPoint("TOPLEFT", 0, -334)
  page.note:SetPoint("TOPRIGHT", 0, -334)

  function page.update(board)
    local view = (board and board.view) or UI.scoreView or "run"
    local liveFight = board and board.liveFight
    page.chips.run.select(view == "run" and not liveFight)
    page.chips.fight.select(view == "fight" and not liveFight)
    page.table.markSort((board and board.sort) or UI.scoreSort or "damage_done")
    if board and board.active then
      page.complete:Show()
    else
      page.complete.reset()
      page.complete:Hide()
    end
    if not board then
      page.summary:SetText("")
      page.table.set({})
      page.note:SetText("Enter a dungeon: everyone in your group shows up here, with their numbers live during each fight.")
      return
    end
    local run = board.run
    local parts = { dungeonLabel(FT.dungeonName(run), run.instance and run.instance.difficulty_name) }
    if liveFight then
      parts[#parts + 1] = hex(C.good) .. "Live: this fight|r"
    elseif board.active then
      parts[#parts + 1] = hex(C.good) .. "In progress|r"
    else
      parts[#parts + 1] = "Ended " .. UI.day(run.timing and run.timing.ended_at)
    end
    if liveFight then
      -- Nothing more: the fight's length is not known until it ends.
    elseif view == "fight" then
      if board.fight then
        parts[#parts + 1] = "Last fight: " .. board.fight.name .. "  " .. UI.duration(board.fight.seconds)
      end
    elseif board.seconds and board.seconds > 0 then
      parts[#parts + 1] = UI.duration(board.seconds) .. " in combat"
    end
    page.summary:SetText(table.concat(parts, "   " .. hex(C.faint) .. "/|r   "))
    page.table.set(board.rows)

    local note
    if board.meterStatus == "unavailable" or board.meterStatus == "disabled" then
      note = "The game's damage meter isn't available, so there are no numbers to show."
    elseif liveFight and liveFight.unavailable then
      note = "The game doesn't share this fight's numbers live; they appear a few seconds after it ends."
    elseif liveFight and (liveFight.unplaced or 0) > 0 then
      note = "Live. The game hides some names during combat; their numbers show up once the fight ends."
    elseif liveFight then
      note = "Live: this fight so far. Whole run and Last fight catch up a few seconds after it ends."
    elseif view == "fight" and not board.fight then
      note = board.active and "Nothing yet: the numbers appear when the first fight starts."
        or "The last fight is kept until you reload; Whole run still has every fight."
    elseif not board.hasNumbers then
      note = "Nothing yet: the numbers appear when the first fight starts."
    elseif board.active then
      note = "Live during each fight. Click a column to sort; hover a name for every stat."
    else
      note = "Click a column to sort; hover a name for every stat."
    end
    page.note:SetText(note)
  end
  return page
end

-- The window --------------------------------------------------------------------------------

-- UI.tab is the tab the player picked; until they pick one, the scoreboard opens during a run
-- and the overview otherwise.
local function selectTab(name)
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
    UI.tab = key
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

  f.tabs = {
    overview = makeTab(f, "overview", "Overview", PAD - 8),
    runs = makeTab(f, "runs", "Runs", PAD + 80),
    scoreboard = makeTab(f, "scoreboard", "Scoreboard", PAD + 168),
  }
  line(f, PAD, -79, -PAD)

  local content = create("Frame", nil, f)
  content:SetPoint("TOPLEFT", PAD, -90)
  content:SetPoint("BOTTOMRIGHT", -PAD, 34)
  f.content = content
  f.pages = { overview = overviewTab(content), runs = runsTab(content), scoreboard = scoreboardTab(content) }

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
    local where = FT.dungeonName(run) or "this dungeon"
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

  -- The first run fills the scoreboard before there are any finished runs to show.
  local board = UI.scoreboard()
  local hasRuns = view.totals.runs > 0
  if hasRuns or board then
    frame.empty:Hide()
    frame.content:Show()
  else
    frame.empty:Show()
    frame.content:Hide()
  end
  frame.pages.overview.update(view)
  frame.pages.runs.update(view)
  frame.pages.scoreboard.update(board)
  local tab = UI.tab or ((run or not hasRuns) and "scoreboard" or "overview")
  if not hasRuns and board then
    tab = "scoreboard"
  end
  selectTab(tab)
  return view
end

-- Stop recording the open run: the scoreboard's "End run" and /ft end.
function UI.endRun()
  local ok, why = FT.RunTracker.endRun()
  if ok then
    FT.Util.print("run ended. It uploads after your next /reload or logout.")
  elseif why == "in_combat" then
    FT.Util.print("finish the fight first, then end the run.")
  else
    FT.Util.print("there is no dungeon run to end.")
  end
  UI.refresh()
  return ok
end

-- Only the scoreboard, after a fight or a roster change; cheap enough to call often.
function UI.refreshScoreboard()
  if frame and frame:IsShown() then
    frame.pages.scoreboard.update(UI.scoreboard())
  end
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
