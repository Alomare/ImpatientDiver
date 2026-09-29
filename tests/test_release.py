"""Offline test of the release script under LuaJIT, with the real game.dll code as fake process memory.

The Ghidra-ready dump (_research/game_25480438.dll, offsets == RVAs) is mapped at a fake base, so the
signatures, rip-relative targets and the scene-name table are checked against the game's own code; only
the heap objects (cutscene manager, clock, fader) and the per-frame scene update are simulated.

Run from the mod folder:  python -B tests/test_release.py
"""
import sys
import tempfile
from pathlib import Path

from lupa.luajit21 import LuaRuntime

MOD = Path(__file__).resolve().parent.parent
SOURCE = (MOD / 'skip_intro_animation.lua').read_text(encoding='utf-8')
DUMP = MOD.parent / '_research' / 'game_25480438.dll'

HARNESS = r'''
local logdir, image = ...
local real_ffi = require('ffi')
local ffi = real_ffi
BASE = 0x40000000
MGR, CLK, FB = 0x20000000, 0x21000000, 0x22000000

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
    Keyboard = {button_id = function(n) return n == 'space' and 44 or nil end,
                pressed = function(id) return id == 44 and fake.space end},
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
        if spec.type ~= 'choice' or #spec.choices < 2 or #spec.choices > 16 then return false, 'bad choices' end
        for _, c in ipairs(spec.choices) do if not plain(c, 48) then return false, 'invalid choice name' end end
        local d = spec.default or 1
        if type(d) ~= 'number' or d % 1 ~= 0 or d < 1 or d > #spec.choices then return false, 'invalid default' end
        fake.options[id] = spec
        return true
    end,
    get = function(id)
        if not fake.options[id] then return nil end
        return fake.values[id:match('[^.]+$')] or fake.options[id].default or 1
    end,
    on_change = function(id, fn) fake.callbacks[id] = fn; return true end,
}
ModOptionsMenu = fake.option_menu
function fake.apply(short, value)  -- the player applies a change in the MODS tab
    fake.values[short] = value
    local id = 'alomare.skip_intro_animation.' .. short
    if fake.callbacks[id] then fake.callbacks[id](value, id) end
end
ModBindingsMenu = {api = 1, register_binding = function(id, label) fake.bound = id .. '|' .. label; return true end,
                   is_down = function(id) return fake.menu end}
update = function(dt) fake.base_updates = (fake.base_updates or 0) + 1 end

-- Globals the mod finds in the image: point them at simulated objects.
fake.patch(0x346d530, le64(MGR))
fake.patch(0x3326348, le64(CLK))
fake.patch(0x347cda8, le64(FB))
fake.heap(MGR + 0x1900, string.rep('\0', 0x20))
fake.heap(MGR + 0x60, string.rep('\0', 0xa0))
fake.heap(CLK, string.rep('\0', 0x20))
fake.heap(FB + 0x128 + 0x780, string.rep('\0', 0x30))

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
}
function fake.game_update()
    local current, phase = fake.scene()
    local plan = PLANS[current]
    local tm = plan and plan.timers[phase]
    if not tm or fake.stamp(tm[1]) + tm[2] > fake.now() then return end
    fake.calls[#fake.calls + 1] = string.format('update %d %d->%d', current, phase, phase + 1)
    write_mem(MGR + 0x60, le32(phase + 1))
    fake.set_stamp(0x88, fake.now())
    if phase + 1 == plan.final then fake.set_scene(plan.next or 0, plan.start or 1) end
end

function fake.frame_step(n)
    for _ = 1, n or 1 do
        fake.frame = fake.frame + 1
        update(0.016)
        fake.game_update()
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
    values = {'login': 1, 'pod': 1, 'ftl': 1}
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


def main():
    for pattern in (r'//', r'\bgoto\b', r'&(?!&)', r'~(?!=)', r'<<', r'>>'):
        import re
        check(not re.search(pattern, SOURCE.split('\n', 1)[1].replace('-->', '')), f'no Lua 5.3+ construct {pattern!r}')
    image = DUMP.read_bytes()
    fake = lambda lua: lua.globals().fake

    # 1. Every skip Off: idle, no native access at all; then turning one on in the menu starts it live.
    lua, logs = new_game([], image)
    f = fake(lua)
    f.frame_step(3)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('IDLE - every skip is set to Off') and f.reads == 0
          and f.base_updates == 3, 'every skip Off: idle, game memory untouched, update chained')
    opts = f.options
    ids = sorted(opts.keys()) if opts else []
    check(ids == ['alomare.skip_intro_animation.ftl', 'alomare.skip_intro_animation.login',
                  'alomare.skip_intro_animation.pod']
          and all(opts[i].mod == 'Impatient Diver' and opts[i].default == 3 and opts[i].type == 'choice'
                  and list(opts[i].choices.values()) == ['Off', 'Manual', 'Automatic'] for i in ids)
          and [opts['alomare.skip_intro_animation.' + k].label for k in ('login', 'pod', 'ftl')]
          == ['Log-in Ship Intro', 'Cryo Pod Transition', 'FTL Transition'],
          'three Off/Manual/Automatic options registered under Impatient Diver, Automatic by default')
    f.apply('login', 3)
    f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 1 skip(s) active') and 'Log-in ship intro: Automatic (ship_intro' in status
          and 'Cryo pod transition: Off' in status, 'turning a skip on in the menu resolves and reports it: %r' % (status,))
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
    check(status.startswith('IDLE - every skip is set to Off') and f.calls_text() == '' and f.stamp(0x88) == NOW - 100000,
          'switching it back Off leaves the scene alone and says so')
    f.apply('login', 2)
    f.frame_step(1)
    f.space = True; f.frame_step(1); f.space = False; f.frame_step(2)
    check(f.calls_text().startswith('update 7 1->2') and 'Log-in ship intro: Manual' in text(logs / 'ImpatientDiver_STATUS.log'),
          'switched to Manual: spacebar skips it')

    # 1b. Mod Options Menu not installed: every skip Automatic.
    lua, logs = new_game([], image, menu=False)
    f = fake(lua)
    f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 3 skip(s) active') and 'Settings: defaults, all Automatic' in status
          and status.count(': Automatic (') == 3, 'without Mod Options Menu all three are Automatic: %r' % (status,))

    # 1c. Mod Options Menu loaded after this addon: connected on a later frame, its values take over.
    lua, logs = new_game(['pod_key'], image, menu=False)
    f = fake(lua)
    f.frame_step(2)
    lua.execute('ModOptionsMenu = fake.option_menu')
    f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 1 skip(s) active') and 'Settings: Mod Options Menu' in status
          and 'Cryo pod transition: Manual' in status and 'Log-in ship intro: Off' in status,
          'a menu that loads later is connected and its values apply: %r' % (status,))

    # 1d. A menu that gives no value (or registration fails): that skip stays Automatic.
    lua, logs = new_game([], image, "fake.option_menu.get = function() return nil end; "
                                    "local reg = fake.option_menu.register_option; fake.option_menu.register_option = "
                                    "function(id, spec) if id:find('pod') then return false, 'full' end return reg(id, spec) end")
    f = fake(lua)
    f.frame_step(1)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('OK - 3 skip(s) active') and 'not registered: full' in text(logs / 'ImpatientDiver.log'),
          'no value from the menu, or a failed registration, keeps Automatic: %r' % (status,))

    # 2. All three selected, this build: fast path resolves everything from the real code.
    lua, logs = new_game(['login_auto', 'pod_key', 'ftl_auto'], image)
    f = fake(lua)
    f.frame_step(1)
    t = lua.globals().ImpatientDiver._test
    d = t.derived
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(d.manager == 0x346d530 and d.clock == 0x3326348 and d.fader == 0x347cda8,
          'globals derived from the code: %r' % ([hex(d[k]) if d[k] else None for k in ('manager', 'clock', 'fader')],))
    ids = d.scene_ids
    check(ids and ids['ship_intro'] == 7 and ids['ship_bridge_intro'] == 3 and ids['ship_teleporter_arrival'] == 13
          and ids['ship_planet_departure'] == 12 and ids['ship_planet_arrival'] == 11
          and ids['ship_teleporter_network_join'] == 15, 'scene ids read from the game\'s name table')
    check(status.splitlines()[:6] == ['OK - 3 skip(s) active', 'Impatient Diver ' + re.search(r"local M = {version = '([^']+)'", SOURCE).group(1),
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
    t11 = bytes.fromhex('48 8B 81 88 00 00 00 48 05 1A E9 61 00 48 39 42 18')
    prepare = ("fake.patch(0x117dee2, string.rep('\\0', 17)); fake.patch(%d, '%s')"
               % (moved_at, ''.join('\\%d' % b for b in t11)))
    lua, logs = new_game(['ftl_auto'], image, prepare)
    f = fake(lua)
    f.frame_step(1)
    t = lua.globals().ImpatientDiver._test
    during = t.state.ready
    f.frame_step(40)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(not during and t.found['t11p2'] == moved_at and status.startswith('OK - 1 skip(s) active')
          and 'ship_planet_arrival' in status and 'searched for' in status,
          'moved code is found by a scan spread over frames: %r' % (status.splitlines()[:3],))

    # 5. Missing code: the arrival check is gone, the FTL still works for the scenes it can verify.
    lua, logs = new_game(['ftl_auto', 'login_key'], image, "fake.patch(0x117dee2, string.rep('\\0', 17)); "
                                                          "fake.patch(0x117dbb1, string.rep('\\0', 17)); fake.patch(0x117dce5, string.rep('\\0', 17)); "
                                                          "fake.patch(0x116d809, string.rep('\\0', 18))")
    f = fake(lua)
    f.frame_step(40)
    status = text(logs / 'ImpatientDiver_STATUS.log')
    check(status.startswith('PARTIAL - 1 selected skip(s) not available')
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
        return ''.join('\\%d' % x for x in b)
    prepare = ("fake.patch(0x117e950, string.rep('\\0', 30)); fake.patch(%d, '%s'); fake.patch(%d, '%s')"
               % (0x100000, switch_at(0x100000, 0x10), 0x500000, switch_at(0x500000, int.from_bytes(real[21:25], 'little'))))
    lua, logs = new_game(['pod_auto'], image, prepare)
    f = fake(lua)
    f.frame_step(40)
    t = lua.globals().ImpatientDiver._test
    check(t.found["names"] == 0x500000 and t.derived.scene_ids['ship_teleporter_arrival'] == 13,
          'a decoy scene-name switch is rejected, the moved real one is used')

    # 5d. A moved signature found twice is not trusted: that skip plays normally.
    t11 = image[0x117dee2:0x117dee2 + 17]
    code = ''.join('\\%d' % b for b in t11)
    prepare = ("fake.patch(0x117dee2, string.rep('\0', 17)); fake.patch(0x500000, '%s'); fake.patch(0x600000, '%s')"
               % (code, code))
    lua, logs = new_game(['ftl_auto'], image, prepare)
    f = fake(lua)
    f.frame_step(40)
    status = (logs / 'ImpatientDiver_STATUS.log').read_text(encoding='utf-8')
    t = lua.globals().ImpatientDiver._test
    check(t.found['t11p2'] is None and 'ship_planet_arrival' not in status
          and 'Signature t11p2 found 2 times: ignored' in (logs / 'ImpatientDiver.log').read_text(encoding='utf-8'),
          'a signature matching twice is ignored: %r' % (status.splitlines()[:1],))

    # 5d. Key-press chain into a scene whose option is off: stopped there; fades outside the FTL untouched.
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

    # 5e. An automatic fast-forward that times out (loading never finishes) is not restarted in that scene.
    lua, logs = new_game(['ftl_auto'], image)
    f = fake(lua)
    f.frame_step(1)
    f.set_now(NOW)
    f.set_scene(15, 1)
    f.frame_step(2600)
    log = text(logs / 'ImpatientDiver.log')
    check(log.count('Skip started (automatic)') == 1 and log.count('Fast-forward timed out') == 1,
          'an automatic skip that timed out is not restarted for the same scene')

    # 6. Not the game (no game.dll): nothing happens.
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
