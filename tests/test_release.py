"""Offline test of the release script under LuaJIT, with the real game.dll code as fake process memory.

The Ghidra-ready dump (_research/game_25480438.dll, offsets == RVAs) is mapped at a fake base, so the
signatures, rip-relative targets and the scene-name table are checked against the game's own code; only
the heap objects (cutscene manager, clock, fader, presenter manager) and the per-frame scene update are simulated.

Run from the mod folder:  python -B tests/test_release.py
"""
import re
import sys
import tempfile
from pathlib import Path

from lupa.luajit21 import LuaRuntime

MOD = Path(__file__).resolve().parent.parent
ROOT = MOD.parents[1]
MAIN = (MOD / 'skip_intro_animation.lua').read_text(encoding='utf-8')
DUMP = ROOT / '_research' / 'game_25480438.dll'
sys.path.insert(0, str(MOD / 'research'))
sys.path.insert(0, str(ROOT / 'tools'))
import signatures  # noqa: E402
import sigspec  # noqa: E402
from entry import entry_text  # noqa: E402

SOURCE = entry_text(MOD, 'skip_intro_animation.lua')  # what ships: the texts ahead of the script
ROWS = {name: (rva, text_, fields) for name, rva, text_, fields, _ in sigspec.build(signatures.SPECS)}

HARNESS = r'''
local logdir, image = ...
local real_ffi = require('ffi')
local ffi = real_ffi
BASE = 0x40000000
MGR, CLK, FB, UI, HOLO = 0x20000000, 0x21000000, 0x22000000, 0x23000000, 0x24000000
GAME, REQ = 0x25000000, 0x26000000

fake = {space = false, menu = false, calls = {}, frame = 0}
-- Like loader-v17: only [%w_-]+.log names, opened for writing (truncated).
CowboyBingusModLoader = {api = 1, open_log = function(name)
    if type(name) ~= 'string' or not name:match('^[%w_-]+%.log$') then return nil end
    return io.open(logdir .. '/' .. name, 'w')
end}

-- Memory: the game.dll image with patches on top, plus small heap blobs.
local patches, heap = {}, {}
local function le64(v) return ffi.string(ffi.new('uint64_t[1]', v), 8) end
local function le32(v) return ffi.string(ffi.new('uint32_t[1]', v), 4) end
local function f32(v) return ffi.string(ffi.new('float[1]', v), 4) end
fake.le64, fake.le32, fake.f32 = le64, le32, f32
local function read_mem(a, n)
    if a >= BASE and a + n <= BASE + #image then
        local s = image:sub(a - BASE + 1, a - BASE + n)
        for _, p in ipairs(patches) do
            local lo, hi = math.max(a, p[1]), math.min(a + n, p[1] + #p[2])
            if lo < hi then
                s = s:sub(1, lo - a) .. p[2]:sub(lo - p[1] + 1, hi - p[1]) .. s:sub(hi - a + 1)
            end
        end
        return s
    end
    for k, v in pairs(heap) do
        if k <= a and a + n <= k + #v then return v:sub(a - k + 1, a - k + n) end
    end
end
local function write_mem(a, bytes)
    if a >= BASE and a < BASE + #image then patches[#patches + 1] = {a, bytes}; return true end
    for k, v in pairs(heap) do
        if k <= a and a + #bytes <= k + #v then
            heap[k] = v:sub(1, a - k) .. bytes .. v:sub(a - k + #bytes + 1)
            return true
        end
    end
    return false
end
fake.patch = function(rva, bytes) patches[#patches + 1] = {BASE + rva, bytes} end
fake.heap = function(a, bytes) heap[a] = bytes end
fake.read = read_mem
fake.write = write_mem
fake.reads = 0

local k32 = {
    GetCurrentProcess = function() return nil end,
    GetModuleHandleA = function(name) return ffi.cast('void *', BASE) end,
    ReadProcessMemory = function(p, addr, buf, size, got)
        fake.reads = fake.reads + 1
        local s = read_mem(tonumber(ffi.cast('uint64_t', addr)), tonumber(size))
        if not s then return 0 end
        ffi.copy(buf, s, #s); got[0] = #s; return 1
    end,
    WriteProcessMemory = function(p, addr, buf, size, got)
        local ok = write_mem(tonumber(ffi.cast('uint64_t', addr)), ffi.string(buf, tonumber(size)))
        if not ok then return 0 end
        got[0] = size; return 1
    end,
}
package.loaded.ffi = setmetatable({load = function(name) return k32 end}, {__index = real_ffi})

stingray = {
    Keyboard = {button_id = function(n) return (n == 'space' and 44) or (n == 'esc' and 27) or nil end,
                pressed = function(id) return (id == 44 and fake.space) or (id == 27 and fake.escape) end},
}
-- Mod Options Menu v1.0.1's API, validating specs by its rules (mod_options_menu.lua new_option).
fake.values, fake.options, fake.callbacks = {}, {}, {}
local function plain(v, limit) return type(v) == 'string' and v:gsub('%c', ' '):match('%S') ~= nil and #v <= limit end
fake.option_menu = {api = 1,
    register_option = function(id, spec)
        if type(id) ~= 'string' or id == '' or #id > 96 or id:find('%c') or not plain(spec.label, 64) then
            return false, 'invalid option registration'
        end
        if spec.mod ~= nil and not plain(spec.mod, 40) then return false, 'invalid mod name' end
        if spec.description ~= nil and not plain(spec.description, 400) then return false, 'invalid description' end
        if spec.type == 'toggle' then
            if spec.default ~= nil and type(spec.default) ~= 'boolean' then return false, 'invalid default' end
            fake.options[id] = spec
            return true
        end
        if spec.type ~= 'choice' or #spec.choices < 2 or #spec.choices > 16 then return false, 'bad choices' end
        for _, c in ipairs(spec.choices) do if not plain(c, 48) then return false, 'invalid choice name' end end
        local d = spec.default or 1
        if type(d) ~= 'number' or d % 1 ~= 0 or d < 1 or d > #spec.choices then return false, 'invalid default' end
        fake.options[id] = spec
        return true
    end,
    get = function(id)
        if not fake.options[id] then return nil end
        local v = fake.values[id:match('[^.]+$')]
        if v == nil then v = fake.options[id].default end
        if v == nil then v = fake.options[id].type == 'toggle' and false or 1 end
        return v
    end,
    on_change = function(id, fn) fake.callbacks[id] = fn; return true end,
}
ModOptionsMenu = fake.option_menu
function fake.apply(short, value)  -- the player applies a change in the MODS tab
    fake.values[short] = value
    local id = 'alomare.skip_intro_animation.' .. short
    if fake.callbacks[id] then fake.callbacks[id](value, id) end
end
-- Mod Bindings Menu: the skip binding is fake.bound / fake.menu, the map binding fake.map_bound / fake.map_key.
local function bind(id, text) if id:match('%.map$') then fake.map_bound = id .. '|' .. text else fake.bound = id .. '|' .. text end end
fake.bind = bind
ModBindingsMenu = {api = 1, register_binding = function(id, label) bind(id, label); return true end,
                   is_down = function(id) if id:match('%.map$') then return fake.map_key end return fake.menu end}
update = function(dt) fake.base_updates = (fake.base_updates or 0) + 1 end

-- Globals the mod finds in the image: point them at simulated objects.
fake.patch(0x346d530, le64(MGR))
fake.patch(0x3326348, le64(CLK))
fake.patch(0x347cda8, le64(FB))
fake.heap(MGR + 0x1900, string.rep('\0', 0x20))
fake.heap(MGR + 0x60, string.rep('\0', 0xa0))
fake.heap(CLK, string.rep('\0', 0x20))
fake.heap(FB + 0x128 + 0x780, string.rep('\0', 0x30))
-- The presenter manager (UI state + 0x4288): current presenter +0xc, close requests from +0xd8 (Hologram at +0x98).
fake.patch(0x347ce28, le64(UI))
fake.heap(UI + 0x4280, string.rep('\0', 0x200))
fake.heap(HOLO, string.rep('\0', 0x18))
write_mem(UI + 0x4288 + 0xd8 + 0x98, le64(HOLO))
function fake.set_presenter(id) write_mem(UI + 0x4288 + 0xc, le32(id)) end
function fake.close_request() return read_mem(HOLO + 0x10, 1):byte() end
function fake.clear_request() write_mem(HOLO + 0x10, '\0') end
-- MissionEnd (13) and MissionSummary (23): their close requests at [collection + 0x88] / [collection + 0xd8]; the
-- presenter manager closes the current menu when its request is set (as game.dll 0x14bf750).
local MENU_SLOT = {[13] = 0x88, [23] = 0xd8}
fake.heap(REQ, string.rep('\0', 0x100))
function fake.open_menu(id)
    write_mem(REQ + MENU_SLOT[id], '\0')
    write_mem(UI + 0x4288 + 0xd8 + MENU_SLOT[id], le64(REQ + MENU_SLOT[id]))
    write_mem(UI + 0x4288 + 0xc, le32(id)); write_mem(UI + 0x4288 + 0x14, le32(id)); write_mem(UI + 0x4288 + 0x28, le32(1))
end
function fake.menu_open(id)
    local v = ffi.new('uint32_t[1]'); ffi.copy(v, read_mem(UI + 0x4288 + 0xc, 4), 4); return tonumber(v[0]) == id
end
function fake.menu_update()
    for id, slot in pairs(MENU_SLOT) do
        if fake.menu_open(id) and read_mem(REQ + slot, 1):byte() == 1 then
            fake.calls[#fake.calls + 1] = 'close menu ' .. id
            write_mem(UI + 0x4288 + 0xc, le32(0)); write_mem(UI + 0x4288 + 0x28, le32(0))
        end
    end
end
-- The game state (game global + 0xac21c).
fake.patch(0x3326340, le64(GAME))
fake.heap(GAME + 0xac210, string.rep('\0', 0x20))
function fake.set_game_state(v) write_mem(GAME + 0xac21c, le32(v)) end

function fake.set_scene(current, phase)
    write_mem(MGR + 0x1908, le32(0) .. le32(current) .. le32(0))
    write_mem(MGR + 0x60, le32(phase or 1))
end
function fake.scene()
    local s = read_mem(MGR + 0x1908, 8); local v = ffi.new('uint32_t[2]'); ffi.copy(v, s, 8)
    local p = ffi.new('uint32_t[1]'); ffi.copy(p, read_mem(MGR + 0x60, 4), 4)
    return tonumber(v[1]), tonumber(p[0])
end
function fake.stamp(off)
    local v = ffi.new('uint64_t[1]'); ffi.copy(v, read_mem(MGR + 0x60 + off, 8), 8); return tonumber(v[0])
end
function fake.set_stamp(off, v) write_mem(MGR + 0x60 + off, le64(v)) end
function fake.now() local v = ffi.new('uint64_t[1]'); ffi.copy(v, read_mem(CLK + 0x18, 8), 8); return tonumber(v[0]) end
function fake.set_now(v) write_mem(CLK + 0x18, le64(v)) end
function fake.fader(alpha, target)
    write_mem(FB + 0x128 + 0x784, f32(0.25) .. string.rep('\0', 12) .. f32(alpha) .. f32(0) .. f32(0.5) .. f32(target))
end
function fake.fade()
    local v = ffi.new('float[2]'); ffi.copy(v, read_mem(FB + 0x128 + 0x794, 4), 4); ffi.copy(v + 1, read_mem(FB + 0x128 + 0x7a0, 4), 4)
    return string.format('%.2f/%.2f', v[0], v[1])
end

-- The scenes' own per-frame update (as game.dll 0x117d830/0x1177e80): timed phases change when due.
local PLANS = {
    [13] = {timers = {[2] = {0x90, 1500000}, [3] = {0x88, 7500000}, [4] = {0x88, 0x8235}}, final = 5},
    [12] = {timers = {[3] = {0x88, 0x33a025}}, final = 4, next = 11, start = 2},
    [11] = {timers = {[2] = {0x88, 0x61e91a}}, final = 3},
    [15] = {timers = {[3] = {0x88, 5000000}}, final = 4},
    [7] = {timers = {[1] = {0x88, 3000000}, [2] = {0x88, 0x51615}}, final = 3, next = 3, start = 2},
    [3] = {timers = {[2] = {0x88, 2000000}, [3] = {0x88, 0x1312d0}, [4] = {0x88, 0x1ab3f0}, [5] = {0x88, 2500000},
                     [6] = {0x88, 1000000}, [7] = {0x88, 1500000}, [8] = {0x88, 1000000}, [9] = {0x88, 1000000},
                     [10] = {0x88, 1000000}, [11] = {0x88, 2000000}, [12] = {0x88, 2000000}}, final = 13},
    -- Mission extraction (not skipped any more): phase 1 1 s; its other phases are left out.
    [1] = {timers = {[1] = {0x88, 1000000}}, final = 2},
    -- Mission return (never skipped): menus opened on a phase change (opens) or inside a phase (open_in); `menu`
    -- waits for it to close.
    [9] = {timers = {[1] = {0x88, 0x590275}, [2] = {0x88, 0x65b9aa, opens = 13}, [3] = {0x88, 0xcb735, menu = 13}},
           final = 4},
    [8] = {timers = {[1] = {0x88, 0x196e6a, open_in = 13, menu = 13}}, final = 2},
}
function fake.game_update()
    fake.menu_update()
    local current, phase = fake.scene()
    local plan = PLANS[current]
    local tm = plan and plan.timers[phase]
    if fake.frozen or not tm then return end
    if tm[1] and fake.stamp(tm[1]) + tm[2] > fake.now() then return end
    if tm.open_in and fake.opened ~= current then fake.opened = current; fake.open_menu(tm.open_in); return end
    if tm.menu and fake.menu_open(tm.menu) then return end
    if tm.until_ and not fake[tm.until_] then return end
    fake.calls[#fake.calls + 1] = string.format('update %d %d->%d', current, phase, phase + 1)
    write_mem(MGR + 0x60, le32(phase + 1))
    if not plan.keep88 then fake.set_stamp(0x88, fake.now()) end
    fake.set_stamp(0x90, fake.now())
    if tm.opens then fake.open_menu(tm.opens) end
    if phase + 1 == plan.final then fake.opened = nil; fake.set_scene(plan.next or 0, plan.start or 1) end
end

-- Hellpod entry. The local Helldiver: the player manager (+0x88 active, +0x3a8 avatar reference), resolved through
-- the entity manager's reference map (+0xf22ec8 buckets, +0xf22ed0 capacity, +0xf22ed4 empty, +0xf22ed8 multiplier)
-- to the id at manager + 0x1e65e4 * 8 + index * 24. Its seat: the seater component's map (+0x20 .. +0x30) and 64-byte
-- records (+0x48). The ship's hellpods: the hellpod manager's count (+8) and entity pointers (+0x68, id at +8).
PLAYERS, EM, SEATS, SEATMAP, RECS = 0x27000000, 0x28000000, 0x29000000, 0x29100000, 0x29200000
PODS, POD1, POD2 = 0x2a000000, 0x2a100000, 0x2a200000
STK, SCR = 0x2b000000, 0x2c000000
AVATAR, REF, MULT = 0xa0a0, 0x1234, 0x9E3779B1
fake.POD1, fake.POD2 = 0xb0b1, 0xb0b2
local function slot_of(key, cap) return tonumber(ffi.cast('uint32_t', ffi.new('uint64_t', MULT) * key)) % cap end
fake.patch(0x3326468, le64(PLAYERS)); fake.heap(PLAYERS, string.rep('\0', 0x400))
write_mem(PLAYERS + 0x88, le32(1)); write_mem(PLAYERS + 0x3a8, le32(REF))
fake.patch(0x346bf98, le64(EM))
EMAP = EM + 0xf22ec0 + 0x1000
fake.heap(EM + 0xf22ec0, string.rep('\0', 0x40)); fake.heap(EMAP, string.rep('\0', 8 * 8))
write_mem(EM + 0xf22ec8, le64(EMAP) .. le32(8) .. le32(0xffffffff) .. le32(MULT))
for i = 0, 7 do write_mem(EMAP + i * 8, le32(0xffffffff) .. le32(0)) end
write_mem(EMAP + slot_of(REF, 8) * 8, le32(REF) .. le32(2))
fake.heap(EM + 0x1e65e4 * 8, string.rep('\0', 24 * 4)); write_mem(EM + 0x1e65e4 * 8 + 2 * 24, le32(AVATAR))
fake.patch(0x3326d78, le64(SEATS)); fake.heap(SEATS, string.rep('\0', 0x60))
fake.heap(SEATMAP, string.rep('\0', 8 * 8)); fake.heap(RECS, string.rep('\0', 0x40 * 4))
write_mem(SEATS + 0x20, le64(SEATMAP) .. le32(8) .. le32(0xffffffff) .. le32(MULT)); write_mem(SEATS + 0x48, le64(RECS))
for i = 0, 7 do write_mem(SEATMAP + i * 8, le32(0xffffffff) .. le32(0)) end
write_mem(SEATMAP + slot_of(AVATAR, 8) * 8, le32(AVATAR) .. le32(1))
REC = RECS + 0x40
fake.patch(0x3326428, le64(PODS)); fake.heap(PODS, string.rep('\0', 0x80))
fake.heap(POD1, string.rep('\0', 0x10)); fake.heap(POD2, string.rep('\0', 0x10))
write_mem(PODS + 8, le32(2)); write_mem(PODS + 0x68, le64(POD1) .. le64(POD2))
write_mem(POD1 + 8, le32(fake.POD1)); write_mem(POD2 + 8, le32(fake.POD2))
-- The loadout screen: the screen stack (type at +0, screen at +0xb0), the intro timer (+0x273988) and phase (+0x27398c).
fake.patch(0x347ce38, le64(STK)); fake.heap(STK, string.rep('\0', 0xc0)); fake.heap(SCR + 0x273980, string.rep('\0', 0x10))
local function u32_at(a) local v = ffi.new('uint32_t[1]'); ffi.copy(v, read_mem(a, 4), 4); return tonumber(v[0]) end
local function f32_at(a) local v = ffi.new('float[1]'); ffi.copy(v, read_mem(a, 4), 4); return tonumber(v[0]) end
fake.u32_at = u32_at
-- A seat move as the seater update runs it (game.dll 0x639b40): each step waits until the clock reaches the record's
-- deadline (+0x28), then the next one starts 1 s later; after the last, the seat is reached (moving +0x30 cleared,
-- target +0x18 = -1) and, for a hellpod, the briefing opens with its 2 s intro (as the seat completion does).
function fake.seat_move(collection, steps)
    write_mem(REC, le32(collection)); write_mem(REC + 0x18, le32(5)); write_mem(REC + 0x30, '\1')
    write_mem(REC + 0x28, le64(fake.now() + 1000000))
    fake.seat_steps, fake.seat_started, fake.seat_frames, fake.ui_frames = steps or 3, fake.frame, nil, nil
end
function fake.seat_free() write_mem(REC, le32(0)); write_mem(REC + 0x30, '\0'); fake.seat_steps = nil end
function fake.seat_update()
    if fake.seat_steps then
        local v = ffi.new('uint64_t[1]'); ffi.copy(v, read_mem(REC + 0x28, 8), 8)
        if fake.now() >= tonumber(v[0]) then
            fake.seat_steps = fake.seat_steps - 1
            if fake.seat_steps == 0 then
                fake.seat_steps = nil
                write_mem(REC + 0x18, le32(0xffffffff)); write_mem(REC + 0x30, '\0'); write_mem(REC + 0x28, le64(0))
                fake.calls[#fake.calls + 1] = 'seat reached'
                fake.seat_frames = fake.frame - fake.seat_started
                if u32_at(REC) == fake.POD1 or u32_at(REC) == fake.POD2 then
                    fake.set_presenter(14); write_mem(STK, le32(11)); write_mem(STK + 0xb0, le64(SCR))
                    write_mem(SCR + 0x27398c, le32(1)); write_mem(SCR + 0x273988, f32(2.0))
                end
            else
                write_mem(REC + 0x28, le64(fake.now() + 1000000))
            end
        end
    end
    if u32_at(STK) == 11 and u32_at(SCR + 0x27398c) == 1 then
        local t = f32_at(SCR + 0x273988) - 0.016
        write_mem(SCR + 0x273988, f32(t))
        if t <= 0 then
            write_mem(SCR + 0x27398c, le32(0))
            fake.calls[#fake.calls + 1] = 'briefing ui'
            fake.ui_frames = fake.frame - (fake.seat_started or 0)
        end
    end
end

function fake.frame_step(n)
    for _ = 1, n or 1 do
        fake.frame = fake.frame + 1
        if fake.tick then fake.set_now(fake.now() + 16000) end
        update(0.016)
        fake.game_update()
        fake.seat_update()
    end
end
function fake.calls_text() local s = table.concat(fake.calls, ';'); fake.calls = {}; return s end
'''

results = []


def check(cond, what):
    results.append(bool(cond))
    print(('PASS ' if cond else 'FAIL ') + what)


CHOICE = {'off': 1, 'key': 2, 'auto': 3}


def new_game(settings, image, prepare='', menu=True):
    """settings: '<feature>_<off|key|auto>' names set in Mod Options Menu; unnamed features are Off.
    menu=False: Mod Options Menu is not installed."""
    logdir = tempfile.mkdtemp(prefix='sia_rel_')
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(HARNESS, logdir, image)
    values = {'login': 1, 'pod': 1, 'ftl': 1, 'hellpod': 1}
    for name in settings:
        feature, mode = name.split('_')
        values[feature] = CHOICE[mode]
    for feature, value in values.items():
        lua.execute(f"fake.values['{feature}'] = {value}")
    if not menu:
        lua.execute('ModOptionsMenu = nil')
    lua.execute(prepare)
    lua.execute(SOURCE)
    return lua, Path(logdir)


def text(path):
    return path.read_text(encoding='utf-8') if path.exists() else ''


def sig_bytes(image, name):
    rva, text_, _ = ROWS[name]
    return rva, image[rva:rva + len(text_.split())]


def lua_bytes(data):
    return ''.join('\\%d' % b for b in data)


def main():
    for pattern in (r'//', r'\bgoto\b', r'&(?!&)', r'~(?!=)', r'<<', r'>>'):
        check(not re.search(pattern, MAIN.split('\n', 1)[1].replace('-->', '')), f'no Lua 5.3+ construct {pattern!r}')
    check(SOURCE.startswith('-- HD2-Addon: mods/alomare/skip_intro_animation\n'), 'declaration line first')
    check(not sigspec.check(MOD / 'skip_intro_animation.lua', sigspec.build(signatures.SPECS)),
          'the script carries the current signatures and signature engine')
    image = DUMP.read_bytes()
    fake = lambda lua: lua.globals().fake
    version = re.search(r"local M = {version = '([^']+)'", MAIN).group(1)

    # 1. Every skip Off: only the map exit (always on) runs; then turning one on in the menu starts it live.
    lua, logs = new_game([], image)
    f = fake(lua)
    f.frame_step(3)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 1 feature(s) active') and 'Galactic map quick exit: On' in status
          and 'Hellpod to loadout: Off' in status and f.base_updates == 3,
          'every skip Off: the map exit alone, update chained: %r' % (status.splitlines()[:1],))
    opts = f.options
    ids = sorted(opts.keys()) if opts else []
    skips = ['alomare.skip_intro_animation.' + k for k in ('ftl', 'login', 'pod', 'hellpod')]
    check(ids == sorted(skips)
          and all(opts[i].mod == 'Impatient Diver' and opts[i].default == 3 and opts[i].type == 'choice'
                  and list(opts[i].choices.values()) == ['Off', 'Manual', 'Automatic'] for i in skips)
          and [opts['alomare.skip_intro_animation.' + k].label for k in ('login', 'pod', 'ftl', 'hellpod')]
          == ['Log-in Ship Intro', 'Cryo Pod Transition', 'FTL Transition', 'Hellpod to Loadout'],
          'four Off/Manual/Automatic options (no map toggle), Automatic by default')
    check(f.map_bound == 'alomare.skip_intro_animation.map|Close galactic map',
          'the map key is a Mod Bindings Menu binding: %r' % f.map_bound)
    f.apply('login', 3)
    f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 2 feature(s) active') and 'Log-in ship intro: Automatic (ship_intro' in status
          and 'Cryo pod transition: Off' in status and 'Galactic map quick exit: On' in status,
          'turning a skip on in the menu reports it: %r' % (status,))
    NOW = 100000000
    f.set_now(NOW); f.set_stamp(0x88, NOW - 100000)
    f.set_scene(7, 1)
    f.frame_step(3)
    check(f.calls_text().startswith('update 7 1->2'), 'the skip turned on in the menu works at once')
    f.set_scene(0, 0); f.frame_step(1000); f.calls_text()
    f.apply('login', 1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    f.set_stamp(0x88, NOW - 100000); f.set_scene(7, 1)
    f.space = True; f.frame_step(1); f.space = False; f.frame_step(30)
    check(status.startswith('OK - 1 feature(s) active') and 'Log-in ship intro: Off' in status
          and f.calls_text() == '' and f.stamp(0x88) == NOW - 100000,
          'switching it back Off leaves the scene alone and says so')
    f.apply('login', 2)
    f.frame_step(1)
    f.space = True; f.frame_step(1); f.space = False; f.frame_step(2)
    check(f.calls_text().startswith('update 7 1->2') and 'Log-in ship intro: Manual' in text(logs / 'ImpatientDiver_STATUS.log'),
          'switched to Manual: spacebar skips it')

    # 1b. Mod Options Menu not installed: every skip at its default, the map exit on.
    lua, logs = new_game([], image, menu=False)
    f = fake(lua)
    f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 5 feature(s) active') and 'Settings: defaults, every feature on' in status
          and status.count(': Automatic (') == 4 and ': Manual (' not in status
          and 'Hellpod to loadout: Automatic (seat transition, briefing intro)' in status
          and 'Galactic map quick exit: On' in status,
          'without Mod Options Menu: every skip Automatic, the map exit on: %r' % (status,))

    # 1c. Mod Options Menu loaded after this addon: connected on a later frame, its values take over.
    lua, logs = new_game(['pod_key'], image, menu=False)
    f = fake(lua)
    f.frame_step(2)
    lua.execute('ModOptionsMenu = fake.option_menu')
    f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 2 feature(s) active') and 'Settings: Mod Options Menu' in status
          and 'Cryo pod transition: Manual' in status and 'Log-in ship intro: Off' in status,
          'a menu that loads later is connected and its values apply: %r' % (status,))

    # 1d. A menu that gives no value (or registration fails): that feature stays on.
    lua, logs = new_game([], image, "fake.option_menu.get = function() return nil end; "
                                    "local reg = fake.option_menu.register_option; fake.option_menu.register_option = "
                                    "function(id, spec) if id:find('pod') then return false, 'full' end return reg(id, spec) end")
    f = fake(lua)
    f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 5 feature(s) active') and 'not registered: full' in text(logs / 'ImpatientDiver.log'),
          'no value from the menu, or a failed registration, keeps the defaults: %r' % (status,))

    # 1e. Mod Options Menu v1.1 (version 2): texts are functions in the game's language (English here); OFF stays the
    #     game's own word. Mod Bindings Menu v2.1 (version 3): the binding's texts are functions too.
    lua, logs = new_game([], image, "fake.option_menu.version = 2; fake.option_menu.register_option = "
                                    "function(id, spec) fake.options[id] = spec; return true end; "
                                    "ModBindingsMenu.version = 3; ModBindingsMenu.register_binding = function(id, label, slot, o) "
                                    "fake.bind(id, label() .. '|' .. o.category()); return true end")
    f = fake(lua)
    f.apply('pod', 2)
    f.frame_step(2)
    o = f.options['alomare.skip_intro_animation.pod']
    check(callable(o.label) and o.label() == 'Cryo Pod Transition' and o.mod() == 'Impatient Diver'
          and o.choices[1] == 'Off' and o.choices[2]() == 'Manual' and o.choices[3]() == 'Automatic'
          and len(o.description()) <= 400, 'v1.1 menu: texts passed as functions, OFF plain')
    check(f.bound == 'alomare.skip_intro_animation.skip|Skip cutscene|Impatient Diver'
          and f.map_bound == 'alomare.skip_intro_animation.map|Close galactic map|Impatient Diver',
          'v2.1 bindings: labels and section passed as functions: %r %r' % (f.bound, f.map_bound))

    # 2. All three selected, this build: fast path resolves everything from the real code.
    lua, logs = new_game(['login_auto', 'pod_key', 'ftl_auto'], image)
    f = fake(lua)
    f.frame_step(1)
    t = lua.globals().ImpatientDiver._test
    d = t.derived
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(d.manager == 0x346d530 and d.clock == 0x3326348 and d.fader == 0x347cda8,
          'globals derived from the code: %r' % ([hex(d[k]) if d[k] else None for k in ('manager', 'clock', 'fader')],))
    v = t['values']
    check(v.current == 0x190c and v.clock_now == 0x18 and v.t13p3_wait == 7500000 and v.t13p2_stamp == 0x90
          and v.t3_25_wait == 2500000 and v.fader_duration == 0x784,
          'offsets and waits read from the code (current 0x%x, pod walk-out %d us)' % (v.current, v.t13p3_wait))
    ids = d.scene_ids
    check(ids and ids['ship_intro'] == 7 and ids['ship_bridge_intro'] == 3 and ids['ship_teleporter_arrival'] == 13
          and ids['ship_planet_departure'] == 12 and ids['ship_planet_arrival'] == 11
          and ids['ship_teleporter_network_join'] == 15, 'scene ids read from the game\'s name table')
    check(status.splitlines()[:6] == ['OK - 4 feature(s) active', 'Impatient Diver ' + version,
                                      'Settings: Mod Options Menu (escape menu > MODS > Impatient Diver)',
                                      'Log-in ship intro: Automatic (ship_intro, ship_bridge_intro)',
                                      'Cryo pod transition: Manual (ship_teleporter_arrival)',
                                      'FTL transition: Automatic (ship_planet_departure, ship_planet_arrival, ship_teleporter_network_join)'],
          'status file: verdict first, then each skip: %r' % (status,))
    check(f.bound == 'alomare.skip_intro_animation.skip|Skip cutscene' or f.bound is None, 'binding id and label')

    # Log-in intro, automatic: both scenes fast-forwarded; the game changes every phase itself, through the
    # bridge intro's own done phase (no interrupt, no posted audio).
    f.set_now(NOW)
    f.set_stamp(0x88, NOW - 100000)
    f.set_scene(7, 1)
    f.frame_step(40)
    login = f.calls_text()
    expected = ['update 7 1->2', 'update 7 2->3'] + ['update 3 %d->%d' % (p, p + 1) for p in range(2, 13)]
    check(login == ';'.join(expected) and f.scene()[0] == 0,
          'log-in intro fast-forwarded through every phase of both scenes: %r' % (login,))
    check(f.bound == 'alomare.skip_intro_animation.skip|Skip cutscene', 'Mod Bindings Menu binding registered for key mode')

    # Cryo pod, key mode: nothing until spacebar; then the game's own update runs every phase.
    f.frame_step(950)  # let the log-in chain run out
    f.calls_text()
    f.set_stamp(0x88, NOW - 1000000); f.set_stamp(0x90, NOW - 200000)
    f.set_scene(13, 2)
    f.frame_step(20)
    untouched = (f.calls_text(), f.stamp(0x90))
    f.space = True; f.frame_step(1); f.space = False
    f.frame_step(1)
    moved = f.calls_text()
    f.frame_step(28)
    held = f.calls_text()
    f.frame_step(5)
    finished = f.calls_text()
    check(untouched == ('', NOW - 200000), 'pod in key mode waits for the key: %r' % (untouched,))
    check(moved == 'update 13 2->3' and held == '' and finished == 'update 13 3->4;update 13 4->5' and f.scene()[0] == 0,
          'spacebar fast-forwards the pod; phase 3 held for the body placement: %r %r %r' % (moved, held, finished))

    # FTL, automatic: departure then arrival, fades held clear; the chain does not enter a key-mode pod.
    f.frame_step(950)  # let the pod's key-press chain run out
    f.calls_text()
    f.set_stamp(0x88, NOW - 1000000); f.fader(0.5, 1.0)
    f.set_scene(12, 3)
    f.frame_step(1)
    fade_during = f.fade()
    f.frame_step(3)
    ftl = f.calls_text()
    f.set_scene(13, 2); f.set_stamp(0x90, NOW - 200000)
    f.frame_step(5)
    pod_after_auto = (f.calls_text(), f.stamp(0x90))
    check(ftl == 'update 12 3->4;update 11 2->3' and fade_during == '0.00/0.00',
          'FTL departure and arrival fast-forwarded automatically, fade held clear: %r %r' % (ftl, fade_during))
    log = text(logs / 'ImpatientDiver.log')
    check('Scene ship_planet_departure' in log and 'Scene ship_planet_arrival' in log and 'Scene none' in log,
          'scene changes are logged by name')
    check(pod_after_auto == ('', NOW - 200000), 'an automatic FTL does not carry on into a key-mode pod: %r' % (pod_after_auto,))
    f.fader(0.5, 1.0)
    f.set_scene(13, 2); f.frame_step(1)
    check(f.fade() == '0.50/1.00', 'fades are left alone outside the FTL scenes too')
    f.set_scene(0, 0); f.frame_step(2); f.calls_text()

    # A timer ahead of the clock (wrong layout) stops without writing.
    f.set_stamp(0x88, NOW + 5)
    f.set_scene(12, 3)
    f.frame_step(3)
    check(f.stamp(0x88) == NOW + 5 and 'timer ahead of the clock' in text(logs / 'ImpatientDiver.log'),
          'a timer ahead of the clock is never written')
    f.set_scene(0, 0); f.frame_step(1000)

    # Scenes outside the list are never touched, whatever the key.
    f.set_scene(5, 1); f.set_stamp(0x88, NOW - 1000000)
    f.space = True; f.frame_step(1); f.space = False; f.frame_step(30)
    check(f.calls_text() == '' and f.stamp(0x88) == NOW - 1000000, 'unlisted scene (cryogenic intro) untouched')

    # 3. Key-mode FTL: one press follows the lobby join chain into a selected pod.
    lua, logs = new_game(['pod_key', 'ftl_key'], image)
    f = fake(lua)
    f.frame_step(1)
    f.set_now(NOW)
    f.set_stamp(0x88, NOW - 1000000)
    f.set_scene(15, 3)
    f.frame_step(5)
    waiting = f.calls_text()
    f.space = True; f.frame_step(1); f.space = False; f.frame_step(2)
    join = f.calls_text()
    f.frame_step(100)
    f.set_scene(13, 2); f.set_stamp(0x90, NOW - 200000)
    f.frame_step(40)
    chain = f.calls_text()
    check(waiting == '' and join == 'update 15 3->4' and chain == 'update 13 2->3;update 13 3->4;update 13 4->5',
          'a key press on the lobby join also skips the pod that follows: %r %r %r' % (waiting, join, chain))
    f.set_scene(7, 1); f.space = True; f.frame_step(1); f.space = False; f.frame_step(30)
    check(f.calls_text() == '', 'a feature switched off (log-in intro) is left alone')

    # 4. Moved code: this build's address no longer matches, so the scan finds it elsewhere.
    moved_at = 0x500000  # inside the code section (the search only covers executable sections)
    rva, code = sig_bytes(image, 't11p2')
    prepare = ("fake.patch(%d, string.rep('\\0', %d)); fake.patch(%d, '%s')"
               % (rva, len(code), moved_at, lua_bytes(code)))
    lua, logs = new_game(['ftl_auto'], image, prepare)
    f = fake(lua)
    f.frame_step(1)
    t = lua.globals().ImpatientDiver._test
    during = t.state.ready
    f.frame_step(40)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(not during and t.code().found['t11p2'] == moved_at and status.startswith('OK - 2 feature(s) active')
          and 'ship_planet_arrival' in status and 'searched for' in status,
          'moved code is found by a scan spread over frames: %r' % (status.splitlines()[:3],))
    f.set_now(NOW); f.set_stamp(0x88, NOW - 1000000)
    f.set_scene(11, 2)
    f.frame_step(3)
    check(f.calls_text() == 'update 11 2->3', 'the moved timer check is used (its wait read from the moved code)')

    # 5. Missing code: the arrival check is gone, the FTL still works for the scenes it can verify.
    lua, logs = new_game(['ftl_auto', 'login_key'], image, "fake.patch(0x117dee2, string.rep('\\0', 17)); "
                                                          "fake.patch(0x117dbb1, string.rep('\\0', 17)); "
                                                          "fake.patch(0x116d809, string.rep('\\0', 18))")
    f = fake(lua)
    f.frame_step(40)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('PARTIAL - 1 selected feature(s) not available')
          and 'Log-in ship intro: NOT AVAILABLE, plays normally (its scenes were not found)' in status
          and 'FTL transition: Automatic (ship_planet_departure, ship_teleporter_network_join)' in status,
          'missing code disables only what depends on it, and says so: %r' % (status.splitlines(),))
    f.set_now(NOW); f.set_stamp(0x88, NOW - 100000)
    f.set_scene(7, 1); f.space = True; f.frame_step(1); f.space = False; f.frame_step(2)
    check(f.stamp(0x88) == NOW - 100000, 'an unavailable skip never writes')

    # 5b. A scene whose timers changed is left to play; the rest of its option still works.
    lua, logs = new_game(['login_auto'], image, "fake.patch(0x116d809, string.rep('\\0', 18))")
    f = fake(lua)
    f.frame_step(40)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check('Log-in ship intro: Automatic (ship_intro)' in status, 'bridge intro timers changed: only ship_intro skipped')

    # 5c. Scene names: a decoy switch found first by the scan is rejected; the real (moved) table is used.
    real = image[0x117e950:0x117e950 + 30]

    def switch_at(rva, table):
        b = bytearray(real)
        b[14:18] = (-(rva + 18)).to_bytes(4, 'little', signed=True)   # lea rdx,[image base]
        b[21:25] = table.to_bytes(4, 'little')
        return lua_bytes(b)
    prepare = ("fake.patch(0x117e950, string.rep('\\0', 30)); fake.patch(%d, '%s'); fake.patch(%d, '%s')"
               % (0x100000, switch_at(0x100000, 0x10), 0x500000, switch_at(0x500000, int.from_bytes(real[21:25], 'little'))))
    lua, logs = new_game(['pod_auto'], image, prepare)
    f = fake(lua)
    f.frame_step(40)
    t = lua.globals().ImpatientDiver._test
    check(t.code().found["names"] == 0x500000 and t.derived.scene_ids['ship_teleporter_arrival'] == 13,
          'a decoy scene-name switch is rejected, the moved real one is used')

    # 5d. A moved signature found twice is not trusted: that skip plays normally.
    rva, code = sig_bytes(image, 't11p2')
    prepare = ("fake.patch(%d, string.rep('\\0', %d)); fake.patch(0x500000, '%s'); fake.patch(0x600000, '%s')"
               % (rva, len(code), lua_bytes(code), lua_bytes(code)))
    lua, logs = new_game(['ftl_auto'], image, prepare)
    f = fake(lua)
    f.frame_step(40)
    status = (logs / 'ImpatientDiver_STATUS.log').read_text(encoding='utf-8')
    t = lua.globals().ImpatientDiver._test
    check(t.code().found['t11p2'] is None and 'ship_planet_arrival' not in status
          and 'Signature t11p2 (found 2 times)' in (logs / 'ImpatientDiver.log').read_text(encoding='utf-8'),
          'a signature matching twice is ignored: %r' % (status.splitlines()[:1],))

    # 5e. Key-press chain into a scene whose option is off: stopped there; fades outside the FTL untouched.
    lua, logs = new_game(['ftl_key'], image)
    f = fake(lua)
    f.frame_step(1)
    f.set_now(NOW); f.set_stamp(0x88, NOW - 1000000)
    f.set_scene(15, 3)
    f.space = True; f.frame_step(1); f.space = False; f.frame_step(2)
    f.calls_text()
    f.fader(0.5, 1.0)
    f.set_scene(13, 2); f.set_stamp(0x90, NOW - 200000)
    f.frame_step(40)
    check(f.calls_text() == '' and f.stamp(0x90) == NOW - 200000, 'a key chain never enters a scene whose option is off')
    lua, logs = new_game(['ftl_key', 'pod_key'], image)
    f = fake(lua)
    f.frame_step(1)
    f.set_now(NOW); f.set_stamp(0x90, NOW - 200000); f.fader(0.5, 1.0)
    f.set_scene(13, 2)
    f.space = True; f.frame_step(1); f.space = False; f.frame_step(3)
    check(f.fade() == '0.50/1.00', 'the fade is not touched during the pod either')

    # 5f. A long loading wait (a phase without a step) never times out; a timed phase that doesn't move on does, and
    #     an automatic skip that timed out is not restarted for the same scene.
    lua, logs = new_game(['ftl_auto'], image)
    f = fake(lua)
    f.frame_step(1)
    f.set_now(NOW)
    f.set_scene(15, 1)
    f.frame_step(2600)
    log = text(logs / 'ImpatientDiver.log')
    loading = log.count('Skip started (automatic)') == 1 and 'timed out' not in log
    f.frozen = True
    f.set_stamp(0x88, NOW - 1000000); f.write(0x20000060, f.le32(3))
    f.frame_step(2600)
    log = text(logs / 'ImpatientDiver.log')
    check(loading and log.count('Skip started (automatic)') == 1
          and log.count('Fast-forward timed out (ship_teleporter_network_join phase 3)') == 1,
          'loading waits never time out; a stuck timed phase does once, and is not restarted')

    # 6. Galactic Map Quick Exit (always on): Escape or the Mod Bindings Menu key on the map sets the Hologram
    #    presenter's close request (the game's presenter manager then closes it); nothing elsewhere.
    lua, logs = new_game([], image)
    f = fake(lua)
    f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 1 feature(s) active') and 'Galactic map quick exit: On' in status,
          'map exit on: status says so: %r' % (status.splitlines()[:1],))
    reads = f.reads
    f.frame_step(100)
    check((f.reads - reads) / 100 <= 0.3, 'map closed: %.2f reads per frame' % ((f.reads - reads) / 100))
    f.set_presenter(15)
    f.frame_step(11)
    f.escape = True; f.frame_step(1); f.escape = False; f.frame_step(1)
    check(f.close_request() == 1 and 'close requested' in text(logs / 'ImpatientDiver.log'),
          'Escape on the galactic map: close request set')
    f.clear_request()
    f.frame_step(5)
    check(f.close_request() == 0, 'one request per press')
    f.set_presenter(0)
    f.frame_step(11)
    f.escape = True
    f.set_presenter(15)
    f.frame_step(12)
    f.escape = False; f.frame_step(1)
    check(f.close_request() == 0, 'an Escape held while the map opens does not close it')
    f.escape = True; f.frame_step(1); f.escape = False; f.frame_step(1)
    check(f.close_request() == 1, 'the next press does')
    f.clear_request()
    f.set_presenter(3)
    f.frame_step(11)
    f.escape = True; f.frame_step(1); f.escape = False; f.frame_step(11)
    check(f.close_request() == 0, 'Escape in another menu: nothing written')
    f.map_key = True; f.frame_step(1); f.map_key = False; f.frame_step(11)
    check(f.close_request() == 0, 'the map key in another menu: nothing written')
    f.set_presenter(15)
    f.frame_step(11)
    f.map_key = True; f.frame_step(1); f.map_key = False; f.frame_step(1)
    check(f.close_request() == 1 and 'Map binding on the galactic map: close requested' in text(logs / 'ImpatientDiver.log'),
          'the Mod Bindings Menu key on the map: close request set')
    f.clear_request()
    f.set_presenter(0); f.frame_step(11)
    f.map_key = True; f.set_presenter(15); f.frame_step(12); f.map_key = False; f.frame_step(1)
    check(f.close_request() == 0, 'a map key held while the map opens does not close it')
    rva, code = sig_bytes(image, 'hologram_request')
    lua, logs = new_game([], image, "fake.patch(%d, string.rep('\\0', %d))" % (rva, len(code)))
    f = fake(lua)
    f.frame_step(40)
    f.set_presenter(15)
    f.frame_step(11)
    f.escape = True; f.frame_step(1); f.escape = False; f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(f.close_request() == 0 and status.startswith('PARTIAL - 1 selected feature(s)')
          and 'Galactic map quick exit: NOT AVAILABLE, the map works as normal (code "hologram_request" not found)' in status,
          'its code missing: the map works as normal: %r' % (status.splitlines()[-1:],))

    # 8. Hellpod entry (Automatic): the local seat moving into a hellpod on the ship has each step's deadline moved to
    #    now (the game reaches the seat itself), then the briefing's intro timer is expired.
    lua, logs = new_game(['hellpod_auto'], image)
    f = fake(lua)
    f.frame_step(1)
    v = lua.globals().ImpatientDiver._test['values']
    check(v.players == 0x3326468 and v.avatar_ref == 0x3a8 and v.entities == 0x346bf98 and v.ent_ids == 0x1e65e4
          and v.seaters == 0x3326d78 and v.seat_records == 0x48 and v.seat_deadline == 0x28 and v.seat_moving == 0x30
          and v.seat_clock == 0x3326348 and v.hellpods == 0x3326428 and v.pod_list == 0x68
          and v.intro_phase == 0x27398c and v.intro_timer == 0x273988,
          'hellpod entry offsets read from the code')
    f.set_now(NOW); f.tick = True; f.set_game_state(3)
    f.frame_step(30)
    f.calls_text()
    f.seat_move(f.POD1, 3)
    f.frame_step(30)
    calls = f.calls_text()
    log = text(logs / 'ImpatientDiver.log')
    check(calls == 'seat reached;briefing ui' and f.seat_frames is not None and f.seat_frames <= 15
          and f.ui_frames is not None and f.ui_frames <= 20
          and 'Hellpod entry: skip started (automatic)' in log and 'Hellpod entry: briefing intro skipped' in log,
          'hellpod entry: seat in %r frames, briefing UI in %r frames (naturally 3 s + 2 s): %r'
          % (f.seat_frames, f.ui_frames, calls))
    # Leaving the hellpod (the seat was taken: an exit), another seat, or a seat move off the ship: left alone.
    f.set_presenter(0); f.write(0x2b000000, f.le32(0))
    f.frame_step(20); f.calls_text()
    f.seat_move(f.POD1, 2)  # still in the pod: moving out
    f.frame_step(150)
    exit_frames = f.seat_frames
    f.seat_free(); f.frame_step(20); f.calls_text()
    f.seat_move(0xc0c0, 2)  # not a hellpod
    f.frame_step(150)
    other_frames = f.seat_frames
    f.seat_free(); f.set_game_state(4); f.frame_step(20); f.calls_text()
    f.seat_move(f.POD2, 2)  # in a mission
    f.frame_step(150)
    mission_frames = f.seat_frames
    check(all(n is not None and n >= 120 for n in (exit_frames, other_frames, mission_frames)),
          'an exit, another seat and a mission seat play normally: %r frames' % ([exit_frames, other_frames, mission_frames],))

    # 8b. Manual: nothing without the key; a press during the move skips the rest.
    lua, logs = new_game(['hellpod_key'], image)
    f = fake(lua)
    f.frame_step(1)
    f.set_now(NOW); f.tick = True; f.set_game_state(3)
    f.frame_step(30)
    f.seat_move(f.POD2, 3)
    f.frame_step(400)
    natural = (f.seat_frames, f.ui_frames)
    f.set_presenter(0); f.write(0x2b000000, f.le32(0)); f.seat_free(); f.frame_step(30); f.calls_text()
    f.seat_move(f.POD2, 3)
    f.frame_step(20)
    f.space = True; f.frame_step(1); f.space = False; f.frame_step(20)
    pressed = (f.seat_frames, f.ui_frames)
    log = text(logs / 'ImpatientDiver.log')
    check(natural[0] >= 180 and natural[1] >= 300 and pressed[0] <= 30 and pressed[1] <= 40
          and 'Hellpod entry: started (waiting for the skip key)' in log and 'Hellpod entry: skip started (key press)' in log,
          'hellpod entry, Manual: untouched without the key %r, skipped with it %r' % (natural, pressed))

    # 8c. The seat wait's code missing: the hellpod entry is unavailable and the seat plays normally.
    rva, code = sig_bytes(image, 'seat_wait')
    lua, logs = new_game(['hellpod_auto'], image, "fake.patch(%d, string.rep('\\0', %d))" % (rva, len(code)))
    f = fake(lua)
    f.frame_step(40)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    f.set_now(NOW); f.tick = True; f.set_game_state(3); f.frame_step(30)
    f.seat_move(f.POD1, 2)
    f.frame_step(150)
    check('Hellpod to loadout: NOT AVAILABLE, plays normally (code "seat_wait" not found)' in status
          and f.seat_frames is not None and f.seat_frames >= 120,
          'seat code missing: the entry plays normally: %r' % (status.splitlines()[-3:],))

    # 8d. The avatar lookup calls a function other than the resolver found: the hellpod entry is off.
    rel = (0xfd9bb0 - 0x4db78e).to_bytes(4, 'little', signed=True)
    lua, logs = new_game(['hellpod_auto'], image, "fake.patch(%d, '%s')" % (0x4db78a, lua_bytes(rel)))
    f = fake(lua)
    f.frame_step(40)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check('Hellpod to loadout: NOT AVAILABLE, plays normally (the avatar lookup calls another resolver)' in status,
          'the avatar lookup must call the resolver found: %r' % (status.splitlines()[-3:],))

    # 9. After a mission, with every skip Automatic and the key pressed: the extraction, the elevator ride, the wait
    #    after it and the mission end screen all play on their own time (no mission return skip).
    lua, logs = new_game(['login_auto', 'pod_auto', 'ftl_auto', 'hellpod_auto'], image)
    f = fake(lua)
    f.frame_step(1)
    f.set_now(NOW); f.set_stamp(0x88, NOW - 100000)
    calls, stamps = [], []
    for scene in (1, 9, 8):
        f.set_stamp(0x88, NOW - 100000); f.set_scene(scene, 1)
        f.frame_step(5)
        f.space = True; f.frame_step(1); f.space = False; f.frame_step(40)
        calls.append(f.calls_text()); stamps.append(f.stamp(0x88))
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(calls == ['', '', ''] and stamps == [NOW - 100000] * 3 and 'Mission return' not in status
          and 'MissionEnd' not in text(logs / 'ImpatientDiver.log'),
          'scenes after a mission are left alone: %r %r' % (calls, stamps))

    # 7. Not the game (no game.dll): nothing happens.
    lua, logs = new_game(['ftl_auto'], image, "package.loaded.ffi = setmetatable({load = function() return {"
                         "GetCurrentProcess = function() end, GetModuleHandleA = function() return nil end} end},"
                         " {__index = require('ffi')})")
    f = fake(lua)
    f.frame_step(3)
    check(text(logs / 'ImpatientDiver_STATUS.log').startswith('NOT AVAILABLE - game.dll not loaded'),
          'without game.dll the status says so and nothing runs')

    passed = sum(results)
    print(f'{passed}/{len(results)} passed')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
