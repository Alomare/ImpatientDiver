-- HD2-Addon: mods/alomare/skip_intro_animation
-- Impatient Diver by Alomare.
--
-- Skips three ship sequences. Each is set in Mod Options Menu (escape menu > MODS) to Off, Manual (spacebar,
-- plus an optional Mod Bindings Menu binding) or Automatic; without that mod all three are Automatic:
--   Log-in ship intro    ship_intro, then ship_bridge_intro
--   Cryo pod transition  ship_teleporter_arrival (the game itself places the Helldiver at the pod exit)
--   FTL transition       ship_planet_departure, ship_planet_arrival and ship_teleporter_network_join
--                        (joining a lobby), with the FTL screen fades held clear
-- Every skip is a fast-forward: each scene's phases wait on timers, and the mod moves the running phase's
-- timer on so the game's own update changes phase, with everything that phase change normally does.
-- Loading waits are never skipped. (Version 1 ended the log-in intro through the game's interrupt, whose
-- abort path left cinematic state behind that crashed the next hellpod launch.)
--
-- Everything native is found in game.dll by code signature (first at this build's addresses, else by a
-- search of its executable sections spread over frames, where a signature must match exactly once), and scene
-- ids come from the game's own id-to-name table. Anything not found, or found more than once, disables only
-- what depends on it, and that sequence plays normally. Memory is read and written with
-- ReadProcessMemory / WriteProcessMemory on the game's own process, which fail instead of crashing.
-- Status: %LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\ImpatientDiver_STATUS.log (first line = verdict).
if rawget(_G, 'ImpatientDiver') then return end

local ffi = require('ffi')

local M = {version = '4', frames = 0, errors = 0}
rawset(_G, 'ImpatientDiver', M)

local S = rawget(_G, 'stingray')
local loader = rawget(_G, 'CowboyBingusModLoader')

---------------------------------------------------------------------------------------
-- Configuration

-- Each feature is a Mod Options Menu choice; the value is the index into MODES.
local OPTION_PREFIX = 'alomare.skip_intro_animation.'
local MENU_CATEGORY = 'Impatient Diver'
local CHOICES, MODES = {'Off', 'Manual', 'Automatic'}, {'off', 'key', 'auto'}
local MODE_NAMES = {off = 'Off', key = 'Manual', auto = 'Automatic'}
local DEFAULT_CHOICE = 3
local HOW = ' Manual: press spacebar (or your Mod Bindings Menu key) while it plays. Automatic: skipped as soon as it starts.'
local FEATURES = {
    {id = 'login', label = 'Log-in ship intro', option = 'Log-in Ship Intro',
     description = 'The camera flying into the ship and your Helldiver walking to the bridge after you log in.' .. HOW,
     scenes = {'ship_intro', 'ship_bridge_intro'}},
    {id = 'pod', label = 'Cryo pod transition', option = 'Cryo Pod Transition',
     description = 'Your cryo pod rolling in and your Helldiver stepping out when you arrive on a ship. '
                   .. 'You take control at the pod exit.' .. HOW,
     scenes = {'ship_teleporter_arrival'}},
    {id = 'ftl', label = 'FTL transition', option = 'FTL Transition',
     description = 'The FTL jump when the ship travels to another planet and when you join a lobby. '
                   .. 'Loading still happens.' .. HOW .. ' When joining a lobby, one Manual press also '
                   .. 'skips the cryo pod after it, unless that is Off.',
     scenes = {'ship_planet_departure', 'ship_planet_arrival', 'ship_teleporter_network_join'}},
}
local BINDING = 'alomare.skip_intro_animation.skip'
local TIMEOUT_FRAMES = 1200  -- per scene, for a fast-forward
local CHAIN_FRAMES = 900     -- how long an ended scene waits for a follow-up one (joining a lobby: 15 12 11 15 13)
local SCAN_CHUNK = 0x400000  -- bytes of game.dll searched per frame when signatures have moved

-- Code signatures ('??' = any byte), with where this build (Steam 25480438) has them.
local SIGS = {
    -- `if (manager->current != 0) interrupt_current_scene(manager, 0)`: the cutscene manager global
    -- (rip-relative load) and its current-scene field. (The interrupt itself is not used.)
    interrupt_site = {rva = 0xad6ca2, text = '48 8B 0D ?? ?? ?? ?? 39 91 0C 19 00 00 0F 84 ?? ?? ?? ?? 48 83 C4 30 5B E9 ?? ?? ?? ??'},
    -- Scene timer checks: mov reg,[ctx+88h/90h]; add reg,wait; cmp [clock+18h],reg. The first one's
    -- rip-relative load is the scene clock.
    t13p2 = {rva = 0x1178030, text = '48 8B 05 ?? ?? ?? ?? 49 8B 88 90 00 00 00 48 81 C1 60 E3 16 00 48 39 48 18'},
    t13p3 = {rva = 0x1177f9b, text = '48 8B 8A 88 00 00 00 48 81 C1 E0 70 72 00 48 39 48 18'},
    t13p4 = {rva = 0x1177ec4, text = '49 8B 88 88 00 00 00 48 81 C1 35 82 00 00 48 39 48 18'},
    t12p3 = {rva = 0x117df3d, text = '48 8B 8A 88 00 00 00 48 81 C1 25 A0 33 00 48 39 48 18'},
    t11p2 = {rva = 0x117dee2, text = '48 8B 81 88 00 00 00 48 05 1A E9 61 00 48 39 42 18'},
    t15p3 = {rva = 0x1179efb, text = '48 8B 81 88 00 00 00 48 05 40 4B 4C 00 49 39 40 18'},
    t7p1 = {rva = 0x117dbb1, text = '48 8B 81 88 00 00 00 48 05 C0 C6 2D 00 48 39 42 18'},
    t7p2 = {rva = 0x117db78, text = '48 8B 81 88 00 00 00 48 05 15 16 05 00 48 39 42 18'},
    -- ship_bridge_intro's update (game.dll + 0x116d7a0): each phase waits 1 to 2.5 s.
    t3_2s = {rva = 0x116d7d8, text = '48 8B 8A 88 00 00 00 48 81 C1 80 84 1E 00 48 39 48 18'},
    t3_125 = {rva = 0x116d809, text = '48 8B 8A 88 00 00 00 48 81 C1 D0 12 13 00 48 39 48 18'},
    t3_175 = {rva = 0x116d8bb, text = '48 8B 8A 88 00 00 00 48 81 C1 F0 B3 1A 00 48 39 48 18'},
    t3_25 = {rva = 0x116d92f, text = '48 8B 8A 88 00 00 00 48 81 C1 A0 25 26 00'},
    t3_1s = {rva = 0x116d949, text = '48 8B 8A 88 00 00 00 48 81 C1 40 42 0F 00 48 39 48 18'},
    t3_15 = {rva = 0x116d97a, text = '48 8B 8A 88 00 00 00 48 81 C1 60 E3 16 00 48 39 48 18'},
    -- The screen fade setter: loads the fader global, + 0x128, then alpha/start/target at +0x794/79c/7a0.
    fader = {rva = 0x11d66c0, text = '48 83 EC 38 48 8B 0D ?? ?? ?? ?? 33 D2 48 81 C1 28 01 00 00 48 89 54 24 20 F2 0F 10 44 24 20 '
                                  .. '0F 28 D1 0F 57 C9 0F 2E D1 8B 81 94 07 00 00 89 81 9C 07 00 00 C7 81 A0 07 00 00 00 00 80 3F'},
    -- The scene id-to-name switch: dec ecx; cmp ecx,max; ja; lea rdx,[image]; mov ecx,[rdx+rcx*4+table]
    names = {rva = 0x117e950, text = 'FF C9 83 F9 ?? 0F 87 ?? ?? ?? ?? 48 8D 15 ?? ?? ?? ?? 8B 8C 8A ?? ?? ?? ?? 48 03 CA FF E1'},
}

-- Scene layout: ids at manager + 0x1908 (previous, current, queued); the scene context at manager + 0x60
-- starts with the phase; its timer stamps (u64 microseconds) at the offsets below; the clock at
-- [clock global] + 0x18.
local SCENE = {ids = 0x1908, context = 0x60, clock = 0x18, max_id = 64, max_phase = 32}
local WARP_PLANS = {
    ship_intro = {[1] = {stamp = 0x88, wait = 3000000, sig = 't7p1'}, [2] = {stamp = 0x88, wait = 0x51615, sig = 't7p2'}},
    ship_bridge_intro = {
        [2] = {stamp = 0x88, wait = 2000000, sig = 't3_2s'}, [3] = {stamp = 0x88, wait = 0x1312d0, sig = 't3_125'},
        [4] = {stamp = 0x88, wait = 0x1ab3f0, sig = 't3_175'}, [5] = {stamp = 0x88, wait = 2500000, sig = 't3_25'},
        [6] = {stamp = 0x88, wait = 1000000, sig = 't3_1s'}, [7] = {stamp = 0x88, wait = 1500000, sig = 't3_15'},
        [8] = {stamp = 0x88, wait = 1000000, sig = 't3_1s'}, [9] = {stamp = 0x88, wait = 1000000, sig = 't3_1s'},
        [10] = {stamp = 0x88, wait = 1000000, sig = 't3_1s'}, [11] = {stamp = 0x88, wait = 2000000, sig = 't3_2s'},
        [12] = {stamp = 0x88, wait = 2000000, sig = 't3_2s'},
    },
    ship_teleporter_arrival = {
        [2] = {stamp = 0x90, wait = 1500000, sig = 't13p2'},
        [3] = {stamp = 0x88, wait = 7500000, sig = 't13p3', hold_frames = 30},  -- the game places the body
        [4] = {stamp = 0x88, wait = 0x8235, sig = 't13p4'},
    },
    ship_planet_departure = {[3] = {stamp = 0x88, wait = 0x33a025, sig = 't12p3'}},
    ship_planet_arrival = {[2] = {stamp = 0x88, wait = 0x61e91a, sig = 't11p2'}},
    ship_teleporter_network_join = {[3] = {stamp = 0x88, wait = 5000000, sig = 't15p3'}},
}
local FADE_SCENES = {ship_planet_departure = true, ship_planet_arrival = true}
local FADER = {offset = 0x128, duration = 0x784, alpha = 0x794, start = 0x79c, target = 0x7a0}

---------------------------------------------------------------------------------------
-- Logging and status

local function open_log(name)
    if loader and type(loader.open_log) == 'function' then
        local ok, f = pcall(loader.open_log, name)
        if ok then return f end
    end
end

local log_file = open_log('ImpatientDiver.log')
local log_lines = 0

local function note(msg)
    if not log_file or log_lines >= 2000 then return end
    log_lines = log_lines + 1
    pcall(function()
        log_file:write(string.format('[f%d t%.1f] %s\n', M.frames, os.clock(), msg))
        log_file:flush()
    end)
end

local function write_status(lines)
    local f = open_log('ImpatientDiver_STATUS.log')
    if not f then return end
    pcall(function()
        f:write(table.concat(lines, '\n') .. '\n')
        f:close()
    end)
end

---------------------------------------------------------------------------------------
-- Native memory

local native = {}

local function init_native()
    -- Declared one by one: another mod may already have declared some of them.
    for _, decl in ipairs({
        'void *GetCurrentProcess(void);',
        'void *GetModuleHandleA(const char *name);',
        'int ReadProcessMemory(void *process, const void *address, void *buffer, size_t size, size_t *read);',
        'int WriteProcessMemory(void *process, void *address, const void *buffer, size_t size, size_t *written);',
    }) do pcall(ffi.cdef, decl) end
    local ok, k32 = pcall(ffi.load, 'kernel32')
    if not ok then return false, 'kernel32 unavailable' end
    native.k32, native.process = k32, k32.GetCurrentProcess()
    local game = k32.GetModuleHandleA('game.dll')
    if game == nil then return false, 'game.dll not loaded' end
    native.base = tonumber(ffi.cast('uint64_t', game))
    return true
end

local function read(address, size)
    local buf, got = ffi.new('uint8_t[?]', size), ffi.new('size_t[1]')
    if native.k32.ReadProcessMemory(native.process, ffi.cast('const void *', address), buf, size, got) == 0
       or tonumber(got[0]) ~= size then
        return nil
    end
    return ffi.string(buf, size)
end

local function write(address, bytes)
    local got = ffi.new('size_t[1]')
    local ok = native.k32.WriteProcessMemory(native.process, ffi.cast('void *', address), bytes, #bytes, got)
    return ok ~= 0 and tonumber(got[0]) == #bytes
end

local function u32(blob, offset)
    offset = offset or 0
    if not blob or #blob < offset + 4 then return nil end
    local v = ffi.new('uint32_t[1]')
    ffi.copy(v, blob:sub(offset + 1, offset + 4), 4)
    return tonumber(v[0])
end

local function i32(blob, offset)
    local v = u32(blob, offset)
    if v and v >= 2147483648 then v = v - 4294967296 end
    return v
end

local function u64(blob)
    if not blob or #blob ~= 8 then return nil end
    local v = ffi.new('uint64_t[1]')
    ffi.copy(v, blob, 8)
    return v[0]
end

local function pointer(blob)
    local v = u64(blob)
    if not v then return nil end
    local a = tonumber(v)
    if a < 0x10000 or a >= 0x800000000000 then return nil end
    return a
end

local ZERO32 = string.rep('\0', 4)

---------------------------------------------------------------------------------------
-- Signatures

local function parse(text)
    local bytes = {}
    for part in text:gmatch('%S+') do bytes[#bytes + 1] = part ~= '??' and tonumber(part, 16) or false end
    -- The longest run of fixed bytes is searched for; the rest is compared around it.
    local best_at, best_len, at, len = 1, 0, nil, 0
    for i = 1, #bytes + 1 do
        if bytes[i] then
            if not at then at, len = i, 0 end
            len = len + 1
            if len > best_len then best_at, best_len = at, len end
        else
            at = nil
        end
    end
    local anchor = {}
    for i = best_at, best_at + best_len - 1 do anchor[#anchor + 1] = string.char(bytes[i]) end
    return {bytes = bytes, anchor = table.concat(anchor), anchor_at = best_at - 1}
end

local function matches(blob, pos, sig)  -- pos: 1-based start in blob
    if pos < 1 or pos + #sig.bytes - 1 > #blob then return false end
    for i, b in ipairs(sig.bytes) do
        if b and blob:byte(pos + i - 1) ~= b then return false end
    end
    return true
end

local function rip_target(rva, instruction_length)  -- the rip-relative target of the instruction at rva
    local disp = i32(read(native.base + rva + instruction_length - 4, 4))
    return disp and rva + instruction_length + disp
end

local found = {}       -- signature name -> rva
local derived = {}     -- manager/clock/fader globals (rva), scene ids by name

-- Reads the scene names from the id-to-name switch at rva (pure reads); nil if it isn't that switch.
local function scene_names(rva)
    local head = read(native.base + rva, 30)
    if not head then return nil end
    local count = head:byte(5) + 1
    local table_rva = u32(head, 21)
    local image_disp = i32(head, 14)
    if count > SCENE.max_id or not table_rva or not image_disp or rva + 18 + image_disp ~= 0 then return nil end
    local jumps = read(native.base + table_rva, count * 4)
    if not jumps then return nil end
    local ids = {}
    for id = 1, count do
        local code = u32(jumps, (id - 1) * 4)
        local lea = code and read(native.base + code, 8)
        if not lea or lea:sub(1, 3) ~= '\x48\x8d\x05' or lea:byte(8) ~= 0xc3 then return nil end
        local text = read(native.base + code + 7 + i32(lea, 3), 48)
        local name = text and text:match('^([%w_]+)%z')
        if not name then return nil end
        ids[name] = id
    end
    return ids
end

-- Extra checks a candidate match must pass.
local VALIDATE = {
    names = function(rva) local ids = scene_names(rva); return ids and ids.ship_teleporter_arrival ~= nil end,
}

local sigs = {}
for name, s in pairs(SIGS) do sigs[name] = parse(s.text); sigs[name].rva = s.rva end

local function check_at(name, rva)
    local sig = sigs[name]
    local blob = read(native.base + rva, #sig.bytes)
    if not blob or not matches(blob, 1, sig) then return false end
    return not VALIDATE[name] or VALIDATE[name](rva)
end

local scan = nil  -- state of the fallback search, when something was not at this build's address

local function u16(blob, offset)
    if not blob or #blob < offset + 2 then return nil end
    return blob:byte(offset + 1) + 256 * blob:byte(offset + 2)
end

-- game.dll's executable sections: {rva, size}.
local function code_sections()
    local dos = read(native.base, 0x40)
    local pe = dos and dos:sub(1, 2) == 'MZ' and u32(dos, 0x3c)
    local nt = pe and pe < 0x10000 and read(native.base + pe, 0x18)
    if not nt or nt:sub(1, 4) ~= 'PE\0\0' then return nil end
    local count, opt = u16(nt, 6), u16(nt, 20)
    local headers = count and count <= 96 and read(native.base + pe + 24 + opt, count * 40)
    if not headers then return nil end
    local sections = {}
    for i = 0, count - 1 do
        local size, rva, flags = u32(headers, i * 40 + 8), u32(headers, i * 40 + 12), u32(headers, i * 40 + 36)
        if size > 0 and math.floor(flags / 0x20000000) % 2 == 1 then sections[#sections + 1] = {rva = rva, size = size} end
    end
    return #sections > 0 and sections or nil
end

-- One chunk of the search; every match is collected (a signature must match exactly once). True when done.
local function scan_step()
    local overlap = 256
    local s = scan.sections[scan.section]
    local from = scan.offset
    local size = math.min(SCAN_CHUNK + overlap, s.size - from)
    local blob = read(native.base + s.rva + from, size)
    local pieces = {}
    if blob then
        pieces[1] = {from, blob}
    else
        for off = from, from + size - 1, 0x10000 do  -- skip unreadable pages
            local piece = read(native.base + s.rva + off, math.min(0x10000 + overlap, s.size - off))
            if piece then pieces[#pieces + 1] = {off, piece} end
        end
    end
    for _, piece in ipairs(pieces) do
        local piece_from, data = piece[1], piece[2]
        for name, hits in pairs(scan.hits) do
            local sig, init = sigs[name], 1
            while true do
                local at = data:find(sig.anchor, init, true)
                if not at then break end
                local start = at - sig.anchor_at
                local offset = piece_from + start - 1
                -- Matches starting in the overlap belong to the next chunk.
                if offset >= from and offset < from + SCAN_CHUNK and matches(data, start, sig)
                   and (not VALIDATE[name] or VALIDATE[name](s.rva + offset)) then
                    hits[#hits + 1] = s.rva + offset
                end
                init = at + 1
            end
        end
    end
    scan.offset = from + SCAN_CHUNK
    if scan.offset >= s.size then scan.section, scan.offset = scan.section + 1, 0 end
    if scan.sections[scan.section] then return false end
    for name, hits in pairs(scan.hits) do
        if #hits == 1 then
            found[name] = hits[1]
        else
            note(string.format('Signature %s %s', name, #hits == 0 and 'not found' or ('found ' .. #hits .. ' times: ignored')))
        end
    end
    return true
end

---------------------------------------------------------------------------------------
-- Resolution: signatures -> what each feature can use

local state = {ready = false, started = false, menu = nil, scene_feature = {}, plans = {}}

local function derive()
    if found.interrupt_site then derived.manager = rip_target(found.interrupt_site, 7) end
    if found.t13p2 then derived.clock = rip_target(found.t13p2, 7) end
    if found.fader then derived.fader = rip_target(found.fader + 4, 7) end
    if found.names then derived.scene_ids = scene_names(found.names) end
end

-- Writes the status file from the current modes and, once resolved, what each feature can use.
local function report()
    local lines, working, broken = {}, 0, 0
    for _, feature in ipairs(FEATURES) do
        local text
        if feature.mode == 'off' then
            text = feature.label .. ': Off'
        elseif not state.ready then
            return  -- still resolving; finish_resolution reports
        elseif feature.usable then
            working = working + 1
            text = string.format('%s: %s (%s)', feature.label, MODE_NAMES[feature.mode], table.concat(feature.found, ', '))
        else
            broken = broken + 1
            text = feature.label .. ': NOT AVAILABLE, plays normally (' .. feature.why .. ')'
        end
        lines[#lines + 1] = text
    end
    local verdict
    if broken > 0 then
        verdict = 'PARTIAL - ' .. broken .. ' selected skip(s) not available after a game update; those play normally'
    elseif working > 0 then
        verdict = 'OK - ' .. working .. ' skip(s) active'
    else
        verdict = 'IDLE - every skip is set to Off'
    end
    table.insert(lines, 1, verdict)
    table.insert(lines, 2, 'Impatient Diver ' .. M.version)
    table.insert(lines, 3, state.menu and 'Settings: Mod Options Menu (escape menu > MODS > Impatient Diver)'
                           or 'Settings: defaults, all Automatic (Mod Options Menu not found)')
    if scan then lines[#lines + 1] = 'Signatures were searched for (game updated since build 25480438).' end
    write_status(lines)
    note(verdict)
end

-- Decides, per feature and scene, what is usable, and writes the status file.
local function finish_resolution()
    derive()
    local ids = derived.scene_ids
    local core = derived.manager and ids
    for _, feature in ipairs(FEATURES) do
        local usable, why = core, core and '' or 'cutscene system not found'
        if usable and not derived.clock then usable, why = false, 'scene clock not found' end
        local scenes = {}
        if usable then
            for _, scene in ipairs(feature.scenes) do
                local id = ids[scene]
                local ok = id ~= nil
                if ok then
                    for _, step in pairs(WARP_PLANS[scene]) do
                        if not found[step.sig] then ok = false end
                    end
                    if ok then state.plans[id] = WARP_PLANS[scene] end
                end
                if ok then
                    state.scene_feature[id] = {feature = feature, name = scene}
                    scenes[#scenes + 1] = scene
                end
            end
            if #scenes == 0 then usable, why = false, 'its scenes were not found' end
        end
        if not usable then
            for _, scene in ipairs(feature.scenes) do
                local id = ids and ids[scene]
                if id then state.scene_feature[id], state.plans[id] = nil, nil end
            end
        end
        feature.usable, feature.why, feature.found = usable and true or false, why, scenes
        note(feature.label .. ': ' .. (usable and table.concat(scenes, ', ') or 'not available (' .. why .. ')'))
    end
    state.fader = derived.fader
    state.names = {}
    for name, id in pairs(ids or {}) do state.names[id] = name end
    state.ready = true
    report()
end

---------------------------------------------------------------------------------------
-- Scene state

local function manager()
    return derived.manager and pointer(read(native.base + derived.manager, 8))
end

-- current scene id and phase, or nil
local function scene_now(mgr)
    local ids = mgr and read(mgr + SCENE.ids, 12)
    local current = u32(ids, 4)
    if not current or current > SCENE.max_id then return nil end
    local phase = current ~= 0 and u32(read(mgr + SCENE.context, 4)) or 0
    if not phase or phase > SCENE.max_phase then return nil end
    return current, phase
end

local function clock_now()
    local clock = derived.clock and pointer(read(native.base + derived.clock, 8))
    local now = clock and u64(read(clock + SCENE.clock, 8))
    if now and now ~= 0 then return now end
end

local function hold_fade_clear()
    local base = state.fader and pointer(read(native.base + state.fader, 8))
    local fader = base and base + FADER.offset
    local alpha, target = fader and u32(read(fader + FADER.alpha, 4)), fader and u32(read(fader + FADER.target, 4))
    if not alpha or not target or (alpha == 0 and target == 0) then return end
    local _ = write(fader + FADER.duration, ZERO32) and write(fader + FADER.alpha, ZERO32)
              and write(fader + FADER.start, ZERO32) and write(fader + FADER.target, ZERO32)
end

---------------------------------------------------------------------------------------
-- Skips

local run = {warp = nil, scene = nil, since = 0}

-- Fast-forward: each frame, moves the timed phase's stamp back so the game's own update sees the wait as
-- over. Follows the scene chain; stops when an unskippable scene starts, on a timeout, or if a timer looks
-- wrong. by_key: started by a key press (then Manual scenes are followed too).
local function warp_step(mgr, current, phase)
    local w = run.warp
    local function stop(why) note('Fast-forward ' .. why); run.warp = nil end
    if current == 0 then
        w.idle_since = w.idle_since or M.frames
        if M.frames > w.idle_since + CHAIN_FRAMES then stop('ended') end
        return
    end
    local owner = state.scene_feature[current]
    local plan = state.plans[current]
    local mode = owner and owner.feature.mode
    if not plan or not owner or mode == 'off' or (mode ~= 'auto' and not w.by_key) then return stop('ended') end
    w.idle_since = nil
    if current ~= w.scene or phase ~= w.phase then
        if current ~= w.scene then
            w.deadline = M.frames + TIMEOUT_FRAMES
            note('Fast-forwarding ' .. owner.name)
        end
        w.scene, w.phase, w.since = current, phase, M.frames
    end
    if M.frames > w.deadline then return stop('timed out') end
    if FADE_SCENES[owner.name] then hold_fade_clear() end
    local step = plan[phase]
    if not step or (step.hold_frames and M.frames < w.since + step.hold_frames) then return end
    local now = clock_now()
    local address = mgr + SCENE.context + step.stamp
    local stamp = u64(read(address, 8))
    if not now or not stamp then return stop('stopped: timer unreadable') end
    if stamp > now then return stop('stopped: timer ahead of the clock') end
    if now - stamp >= step.wait then return end  -- due; the game changes phase itself
    if not write(address, ffi.string(ffi.new('uint64_t[1]', now - step.wait), 8)) then stop('stopped: write failed') end
end

---------------------------------------------------------------------------------------
-- Skip key: spacebar (raw keyboard), plus an optional Mod Bindings Menu binding

local key = {space = nil, space_down = false, menu = nil, menu_down = false, registered = false, wanted = false}

local function poll_key()
    local pressed = false
    local keyboard = S and S.Keyboard
    if keyboard and type(keyboard.pressed) == 'function' and type(keyboard.button_id) == 'function' then
        if key.space == nil then
            local ok, id = pcall(keyboard.button_id, 'space')
            key.space = ok and id or false
        end
        if key.space then
            local ok, down = pcall(keyboard.pressed, key.space)
            down = ok and down and true or false
            if down and not key.space_down then pressed = true end
            key.space_down = down
        end
    end
    local menu = rawget(_G, 'ModBindingsMenu')
    if menu and menu.api == 1 then
        if not key.registered then
            key.registered = true
            local ok, res = pcall(menu.register_binding, BINDING, 'Skip cutscene', nil, {category = 'Impatient Diver'})
            note('Mod Bindings Menu binding: ' .. ((ok and res) and 'registered' or 'not registered'))
        end
        local ok, down = pcall(menu.is_down, BINDING)
        down = ok and down and true or false
        if down and not key.menu_down then pressed = true end
        key.menu_down = down
    end
    return pressed
end

---------------------------------------------------------------------------------------
-- Frame step

local function step()
    if not state.ready then
        if scan then
            if scan_step() then finish_resolution() end
        end
        return
    end
    local mgr = manager()
    if not mgr then return end
    local current, phase = scene_now(mgr)
    if not current then return end
    local pressed = key.wanted and poll_key()

    if current ~= run.scene then
        run.scene, run.since = current, M.frames
        note('Scene ' .. (current == 0 and 'none' or (state.names[current] or tostring(current))))
    end
    local owner = current ~= 0 and state.scene_feature[current]
    if owner and not run.warp then
        local mode = owner.feature.mode
        local go = (mode == 'auto' and run.auto_done ~= run.since) or (mode == 'key' and pressed)
        if go then
            if mode == 'auto' then run.auto_done = run.since end  -- once per scene instance
            local why = mode == 'auto' and 'automatic' or 'key press'
            run.warp = {by_key = mode == 'key'}
            note('Skip started (' .. why .. ')')
        end
    end
    if run.warp then warp_step(mgr, current, phase) end
end

-- Native access and signatures, resolved the first time any skip is on (never while all are Off).
local function start()
    state.started = true
    local ok, why = init_native()
    if not ok then
        write_status({'NOT AVAILABLE - ' .. why .. '; everything plays normally', 'Impatient Diver ' .. M.version})
        note('Native access unavailable: ' .. why)
        M.retired = true
        return
    end
    local hits = {}
    for name, sig in pairs(sigs) do
        if check_at(name, sig.rva) then found[name] = sig.rva else hits[name] = {} end
    end
    local sections = next(hits) and code_sections()
    if sections then
        note('Searching game.dll for moved code (game updated?)')
        scan = {sections = sections, section = 1, offset = 0, hits = hits}
    else
        finish_resolution()
    end
end

---------------------------------------------------------------------------------------
-- Settings: Mod Options Menu, which may load before or after this addon. Without it, every skip is Automatic.

for _, feature in ipairs(FEATURES) do feature.mode = MODES[DEFAULT_CHOICE] end

local function any_enabled()
    for _, feature in ipairs(FEATURES) do
        if feature.mode ~= 'off' then return true end
    end
    return false
end

local function modes_changed()
    key.wanted = false
    for _, feature in ipairs(FEATURES) do
        if feature.mode == 'key' then key.wanted = true end
    end
    report()
end

local function set_mode(feature, value)  -- true if the mode changed
    local mode = MODES[value] or MODES[DEFAULT_CHOICE]
    if feature.mode == mode then return false end
    note(feature.label .. ' set to ' .. MODE_NAMES[mode])
    feature.mode = mode
    return true
end

local function connect_menu()
    local menu = rawget(_G, 'ModOptionsMenu')
    if type(menu) ~= 'table' or menu.api ~= 1 then return false end
    state.menu = menu
    for _, feature in ipairs(FEATURES) do
        local id = OPTION_PREFIX .. feature.id
        local ok, done, why = pcall(menu.register_option, id, {
            type = 'choice', label = feature.option, mod = MENU_CATEGORY, choices = CHOICES,
            default = DEFAULT_CHOICE, description = feature.description})
        if ok and done then
            pcall(menu.on_change, id, function(value)
                if set_mode(feature, value) then modes_changed() end
            end)
            local got, value = pcall(menu.get, id)
            set_mode(feature, got and value)
        else
            note('Option ' .. id .. ' not registered: ' .. tostring(ok and why or done))
        end
    end
    note('Mod Options Menu connected')
    return true
end

---------------------------------------------------------------------------------------
-- Frame hook

local original_update = rawget(_G, 'update')
update = function(dt, ...)
    if not M.retired then
        local ok, err = xpcall(function()
            M.frames = M.frames + 1
            if not state.menu and connect_menu() then modes_changed() end
            if state.started then
                step()
            elseif any_enabled() then
                start()
            end
        end, debug.traceback)
        if not ok then
            M.errors = M.errors + 1
            note('Error: ' .. tostring(err))
            if M.errors >= 5 then
                M.retired = true
                write_status({'STOPPED - repeated errors; everything plays normally (see ImpatientDiver.log)',
                              'Impatient Diver ' .. M.version})
            end
        end
    end
    if type(original_update) == 'function' then return original_update(dt, ...) end
end

note('Impatient Diver ' .. M.version .. ' loaded')
M._test = {state = state, found = found, derived = derived, run = run, sigs = sigs, features = FEATURES}  -- offline tests
return M
