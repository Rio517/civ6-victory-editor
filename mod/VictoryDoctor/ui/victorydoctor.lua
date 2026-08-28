-- Victory Doctor: read-only diagnostic. Writes to Logs/Lua.log.
-- Open the World Rankings screen, or wait ~3s after load, to trigger.

-- print() lands in Logs/Lua.log; UI.DataError also lands in UIWarnings.csv and
-- UserInterface.log, which we know this install writes. Belt and braces.
local function L(s)
    local line = "[VDOC] " .. tostring(s)
    print(line)
    pcall(function() UI.DataError(line) end)
end

local function SafeCall(fn, ...)
    local ok, a, b = pcall(fn, ...)
    if not ok then return nil, nil, tostring(a) end
    return a, b, nil
end

local function Dump()
    L("================ VICTORY DOCTOR ================")
    L("turn " .. tostring(Game.GetCurrentGameTurn()))

    -- 1. Does the game core still think somebody won?
    local team, vtype, err = SafeCall(Game.GetWinningTeam)
    if err then
        L("Game.GetWinningTeam ERROR: " .. err)
    else
        L(string.format("Game.GetWinningTeam -> team=%s victoryType=%s  (IsEndGame=%s)",
            tostring(team), tostring(vtype), tostring(team ~= nil)))
    end

    -- 2. Which victory types are enabled, per the config we edited
    for row in GameInfo.Victories() do
        local en = SafeCall(Game.IsVictoryEnabled, row.VictoryType)
        L(string.format("victory %-20s enabled=%s", row.VictoryType, tostring(en)))
    end

    -- 3. Per-team progress for every victory type. nil == "Victory Not Completable"
    local teams, seen = {}, {}
    for _, p in ipairs(PlayerManager.GetAliveMajors()) do
        local t = p:GetTeam()
        if not seen[t] then seen[t] = true; table.insert(teams, t); end
    end
    L("alive major teams: " .. table.concat(teams, ","))
    for row in GameInfo.Victories() do
        local parts = {}
        for _, t in ipairs(teams) do
            local prog, _, e = SafeCall(Game.GetVictoryProgressForTeam, row.VictoryType, t)
            table.insert(parts, string.format("T%d=%s", t, e and ("ERR:" .. e) or tostring(prog)))
        end
        L(string.format("progress %-20s %s", row.VictoryType, table.concat(parts, " ")))
    end

    -- 4. Domination specifics: where is every original capital and who holds it?
    L("---- original capitals ----")
    local held = 0
    local total = 0
    for _, pid in ipairs(PlayerManager.GetAliveMajorIDs()) do
        pcall(function()
            local p = Players[pid]
            local cfg = PlayerConfigurations[pid]
            L(string.format("player %d civ=%s alive=%s hasCapital=%s cities=%d",
                pid, cfg and tostring(cfg:GetCivilizationTypeName()) or "?",
                tostring(p:IsAlive()),
                tostring(p:GetCities():GetCapitalCity() ~= nil),
                p:GetCities():GetCount()))
        end)
    end
    for pid = 0, 63 do
        pcall(function()
            local p = Players[pid]
            if p == nil then return end
            local cities = p:GetCities()
            if cities == nil then return end
            for _, city in cities:Members() do
                if city:IsOriginalCapital() then
                    total = total + 1
                    L(string.format("  originalCapital '%s' originalOwner=%s currentOwner=%s",
                        Locale.Lookup(city:GetName()), tostring(city:GetOriginalOwner()),
                        tostring(city:GetOwner())))
                end
            end
        end)
    end
    L("original capitals found on the map: " .. tostring(total))
    L("NOTE: domination needs every major civ's original capital to still exist AND be held.")
    L("================ END ================")
end

local function Kick()
    local ok, err = pcall(Dump)
    if not ok then L("FATAL: " .. tostring(err)); end
end

-- fire on load, and again on the first turn begin, in case the first is too early
Events.LoadGameViewStateDone.Add(Kick)
Events.LoadScreenClose.Add(Kick)
Events.LocalPlayerTurnBegin.Add(Kick)
LuaEvents.VictoryDoctor_Run.Add(Kick)
