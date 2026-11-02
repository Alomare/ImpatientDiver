"""Offline test of skip_intro_animation.lua under Lua 5.1 (lupa), with a fake Chef Shared Loader and engine: when the
mod speeds the game up by itself (Fast and Instant), and when it must not. Needs only Python with lupa.
python -B tests/test_release.py"""
import os
import sys

import lupa.lua51 as lupa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, 'skip_intro_animation.lua'), encoding='utf-8').read()

FAKE = r'''
local T = { now = 0, keys = {}, mouse = {}, players = 1, host = true, mission = false, policy = {}, mult = 1, jump = 0,
            log = {}, notes = {}, asked_sm = {}, rows = {}, specs = {}, changed = {}, session = 'session',
            sync = 'sync', owner = { [1] = 'me' } }
local RUNTIME, CAMERA, DIVER = '46cab355bd8d4d37', '465f4895f3dc98d1', '4d1c334d294dfa97'
T.CANNON = '26ef7da30b82246d'
local meta = { __tostring = function(u) return "[Unit '#ID[" .. u.kind .. "]']" end }
function T.unit(kind, extra)
  local u = setmetatable({ kind = kind, alive = true }, meta)
  for k, v in pairs(extra or {}) do u[k] = v end
  return u
end
function T.camera(x, y, z, fov) return T.unit(CAMERA, { cam = { x = x, y = y, z = z, fov = fov, f = { x = 0, y = 1, z = 0 } } }) end
-- goid: its game object; pos: where it stands
function T.diver(state, goid, x, y) return T.unit(DIVER, { anim = state, goid = goid, pos = { x = x or 0, y = y or 0, z = 0 } }) end
function T.world(units) return { units = units or {}, time = 0 } end
function T.fill(w, kind, n) for _ = 1, n do w.units[#w.units + 1] = T.unit(kind) end end
function T.empty(w) for _, u in ipairs(w.units) do u.alive = false end; w.units = {} end
function T.keep(w, n)   -- the first n units stay
  for i = #w.units, n + 1, -1 do w.units[i].alive = false; w.units[i] = nil end
end
os.clock = function() return T.now end
stingray = {
  Application = {
    worlds = function() local out = {} for i, w in ipairs(T.worlds) do out[i] = w end return out end,
    main_world = function() return T.main end,
    set_time_step_policy = function(kind, v)
      T.policy[#T.policy + 1] = { kind, v }
      if kind == 'external_multiplier' then T.mult = v end
      if kind == 'jump' then T.jump = T.jump + v end   -- in the next frame's step
    end,
    build = function() return 'release' end,
    build_identifier = function() return 'test' end,
  },
  World = {
    units = function(w) local out = {} for i, u in ipairs(w.units) do out[i] = u end return out end,
    num_units = function(w) return #w.units end,
    time = function(w) return w.time end,
    delta_time = function(w) return 1 / 60 end,
    units_by_resource = function(w, id)
      assert(type(id) == 'table' and id.hex, 'units_by_resource without an IdString64')
      local out = {}
      for _, u in ipairs(w.units) do if u.kind == id.hex then out[#out + 1] = u end end
      return out
    end,
  },
  IdString64 = { from_hex = function(h) return { hex = h } end },
  Unit = {
    alive = function(u) return u.alive end,
    num_cameras = function(u)
      assert(u.kind ~= RUNTIME, 'asked a runtime-built unit for cameras')
      assert(u.alive, 'asked a dead unit for cameras')
      return u.cam and 1 or 0
    end,
    camera = function(u, i) assert(u.alive and i == 1, 'camera of a dead unit'); return u.cam end,
    has_animation_state_machine = function(u)
      assert(u.alive, 'asked a dead unit'); T.asked_sm[u] = true; return u.anim ~= nil
    end,
    animation_get_state = function(u)
      assert(u.alive and u.anim and T.asked_sm[u], 'animation_get_state without a state machine (an engine assert)')
      return unpack(u.anim)
    end,
  },
  Camera = {
    world_position = function(c) return c end,
    vertical_fov = function(c) return c.fov end,
    world_rotation = function(c) return c.f end,
  },
  Quaternion = { forward = function(q) return q end },
  Vector3 = { to_elements = function(v) return v.x, v.y, v.z end },
  Network = { game_session = function() return T.session end, peer_id = function() return 'me' end },
  GameSession = {
    unit_synchronizer = function(s) assert(s == 'session', 'unit_synchronizer without the session'); return T.sync end,
    game_object_owner = function(s, id)
      assert(s == 'session' and type(id) == 'number', 'game_object_owner without the session and an id')
      return T.owner[id]
    end,
  },
  UnitSynchronizer = {
    unit_to_game_object_id = function(sync, u) assert(sync == 'sync', 'no synchronizer'); return u.goid end,
  },
}
-- the F9 menu: T.rows holds each row's value (a saved one set before the mod loads, else its default)
function T.set(id, v) T.rows[id] = v; if T.changed[id] then T.changed[id](v) end end
local chef = {
  api = 3, loader_version = '1.2.3',
  has = function(n) return true end,
  own_log = function(n) T.own_log = n return true end,
  log = function(f, ...) T.log[#T.log + 1] = string.format(f, ...) end,
  notify = function(t) T.notes[#T.notes + 1] = t end,
  key_pressed = function(k) return T.keys[k] == true end,
  mouse_down = function(b) return T.mouse[b] == true end,
  in_mission = function() return T.mission end,
  players = function() return T.players end,
  is_host = function() return T.host end,
  unit_position = function(u)
    assert(u.kind ~= RUNTIME, 'asked a runtime-built unit where it is')
    if u.alive and u.pos then return u.pos.x, u.pos.y, u.pos.z end
  end,
  on = function() return function() end end,
  title = function(t) T.title = t end,
  option = function(id, spec)
    assert(spec.type == 'choice' and #spec.choices == 3 and spec.choices[spec.default], 'a row Chef would refuse')
    T.specs[id] = spec
    if T.rows[id] == nil then T.rows[id] = spec.default end
    return T.rows[id]
  end,
  get = function(id) return T.rows[id] end,
  on_change = function(id, fn) T.changed[id] = fn; return true end,
  call = function(name, ...)
    local tbl, fn = name:match('^(%w+)%.([%w_]+)$')
    return stingray[tbl][fn](...)
  end,
}
T.chef = chef
return T
'''

failures = []


def check(cond, what):
    if not cond:
        failures.append(what)


ROWS = ('login_intro', 'cryo_pod', 'ftl', 'hellpod_entry', 'drop_zoom')
OFF, FAST, INSTANT = 1, 2, 3


class Run:
    """A fresh Lua runtime: the title screen's worlds (the ship's, still empty, and the destroyer's), then the mod,
    with every F9 row saved at `mode` (None: no value saved, the rows' defaults)."""

    def __init__(self, mode=FAST):
        self.lua = lupa.LuaRuntime()
        self.T = self.lua.execute(FAKE)
        self.do('T.ship = T.world({ T.camera(0, 0, 0, 0.785) }); T.dest = T.world({ T.camera(0, 0, 0, 0.785) }); '
                'T.map = T.world({ T.camera(0, 0, 0, 0.785) }); T.worlds = { T.ship, T.dest, T.map }; T.main = T.ship')
        if mode is not None:
            self.do(' '.join('T.rows[%r] = %d;' % (row, mode) for row in ROWS))
        self.mod = self.lua.execute('local src, chef = ...; return assert(loadstring(src, "@mod"))(chef)',
                                    SRC, self.T.chef)
        self.dt = 0

    def do(self, code):
        self.lua.execute('local T = ...; ' + code, self.T)

    def frame(self, n=1, real=1 / 60, keys=(), click=False):
        for i in range(n):
            dt = real * self.T.mult + self.T.jump   # the engine hands update the game's step, with a jump asked
            self.T.jump = 0
            self.dt = dt
            self.T.now = self.T.now + real
            self.do('for _, w in ipairs(T.worlds) do w.time = w.time + %r end; '
                    'for k in pairs(T.keys) do T.keys[k] = nil end; %s T.mouse.left = %s'
                    % (dt, ' '.join('T.keys[%r] = true;' % k for k in keys), 'true' if click and i == 0 else 'false'))
            self.mod.update(dt)

    def set(self, row, mode):
        """A row changed in the F9 menu."""
        self.T.set(row, mode)

    def posture(self, state):
        self.do('T.me.anim[14] = %d' % state)

    def in_pod(self, fov=1.222):
        """Ours in its hellpod, the ship's camera on the drop location map's view (a host's or a solo player's as the
        clip ends; a client's holds a close-up on the pod first, fov 0.611)."""
        self.do('T.me.anim[14] = 17; T.ship.units[1].cam.fov = %r' % fov)

    def map_page(self):
        """The loadout screen's world as the drop location map shows: its floor of planes, no Helldiver yet."""
        self.do('T.fill(T.map, "96af7d6acb949f34", 19)')

    def friend(self, x=5, y=5, first=True):
        """Another player's Helldiver on the ship (T.other), listed before ours when `first`."""
        self.do('T.other = T.diver({ 1, 2, 3, 4, 5, 6, 7, 8, 59, 10, 11, 12, 13, 3, 0 }, 2, %d, %d); T.owner[2] = "peer2"; '
                'table.insert(T.ship.units, %s, T.other)' % (x, y, '2' if first else '#T.ship.units + 1'))

    def walk(self, samples, friend_too=False):
        """The player walks: our Helldiver and the camera 1 m further every 0.25 s (and the friend alongside)."""
        for _ in range(samples):
            self.do('T.me.pos.x = T.me.pos.x + 1; T.ship.units[1].cam.x = T.ship.units[1].cam.x + 1'
                    + ('; T.other.pos.x = T.other.pos.x + 1' if friend_too else ''))
            self.frame(15)

    def rate(self):
        return self.T.mult

    def speed(self):
        """What the last frame asked for the next: 'jump' (a jump, at x1), 'x8' or 'x1'."""
        if self.T.jump > 0:
            return 'jump' if self.T.mult == 1 else 'jump at x%d' % self.T.mult
        return 'x%d' % self.T.mult

    def lines(self, since=0):
        return list(self.T.log.values())[since:]

    # the scenes
    def ship(self):
        """The ship loaded: its world big and main, a camera in play, the Helldiver; the destroyer's world empty."""
        self.do('T.ship.units[1].cam.fov = 1.134; T.fill(T.ship, "aaaa000000000001", 1500); '
                'T.fill(T.ship, "46cab355bd8d4d37", 1); '
                'T.me = T.diver({ 1, 2, 3, 4, 5, 6, 7, 8, 59, 10, 11, 12, 13, 36, 0 }, 1); T.ship.units[#T.ship.units + 1] = T.me; '
                'T.main = T.ship')

    def outside(self, units=590):
        """The destroyer's world fills with its cannons and the rest: 590 units as in an FTL (584 to 593 live), 54 as
        in the log-in intro (62 or 63), 28 as in the hellpod launch (25 to 33), 17 as in a lobby change (11 to 24).
        T.keep(T.dest, 6) leaves the camera and five others, as in the walk to the bridge."""
        self.do('T.fill(T.dest, "e857e91975dbb999", %d); T.fill(T.dest, "46cab355bd8d4d37", 1); '
                'T.fill(T.dest, T.CANNON, 2)' % (units - 4))

    def inside(self):
        self.do('T.keep(T.dest, 1)')


# log-in intro: fast from the outside shot on, through the walk to the bridge, x1 once the camera goes wide
r = Run()
check(r.T.own_log == 'ImpatientDiver', 'own log name')
check(r.T.title == 'Impatient Diver (CSL/EAC)', 'the F9 menu names the mod Impatient Diver (CSL/EAC)')
r.frame(30)
check(r.rate() == 1, 'nothing sped up on the title screen')
r.outside(54)
r.do('T.main = T.dest')
r.frame()
check(r.rate() == 8, 'the log-in intro\'s outside shot is sped up')
r.frame(60)
r.do('T.keep(T.dest, 6)')        # the walk to the bridge: the cannons go, a few units stay
r.ship()                         # its camera wide for the first frames 
r.frame(2)
check(r.rate() == 8, 'still fast as the ship loads with its camera wide')
r.do('T.ship.units[1].cam.fov = 0.262')
r.frame(15)
r.inside()                       # the destroyer's world empties before the walk ends
r.frame(15)
check(r.rate() == 8, 'still fast in the walk to the bridge')
r.do('T.ship.units[1].cam.fov = 1.134')
r.frame()
check(r.rate() == 1, 'x1 the frame the camera goes wide again')
r.frame(120)
check(r.rate() == 1, 'stays x1 after the log-in intro')

# before the ship loads, the log-in intro ends when the destroyer's world empties
r = Run()
r.outside(54)
r.do('T.main = T.dest')
r.frame(10)
r.inside()
r.frame()
check(r.rate() == 1, 'x1 the frame the destroyer\'s world empties, no ship yet')

# a ship whose camera never narrows: no walk to the bridge, x1 after 3 s of game time
r = Run()
r.outside(54)
r.do('T.main = T.dest')
r.frame(10)
r.ship()
r.frame(2)
check(r.rate() == 8, 'fast while waiting for the walk')
r.frame(5)                       # 5 frames at x8: 0.67 s of game time
r.frame(30)                      # 30 more: 4.7 s
check(r.rate() == 1, 'x1 when no walk to the bridge follows')

# cannons still there when the log-in intro ends: no FTL made of them
r = Run()
r.outside(54)
r.do('T.main = T.dest')
r.frame(10)
r.ship()
r.do('T.ship.units[1].cam.fov = 0.262')
r.frame(30)
check(r.rate() == 8, 'fast in the walk to the bridge, cannons left')
r.do('T.ship.units[1].cam.fov = 1.134')
r.frame(120)
check(r.rate() == 1, 'x1 after the log-in intro, cannons left')

# FTL: fast while the destroyer's world holds its cannons, x1 the frame they go
r = Run()
r.ship()
r.frame(200)
check(r.rate() == 1, 'nothing sped up on the ship')
r.outside()
r.frame()
check(r.rate() == 8, 'the FTL is sped up')
r.frame(60)
r.inside()
r.frame()
check(r.rate() == 1, 'x1 the frame the FTL ends')
r.frame(60)
r.outside()
r.frame()
check(r.rate() == 8, 'a second FTL is sped up')
r.mod.shutdown()
check(r.T.policy[len(r.T.policy)][2] == 1, 'shutdown puts x1 back')

# the hellpod launch: the destroyer's world becomes the main world once the ship was loaded: left alone, though its
# ship empties as its cannons come (ours was last seen in its hellpod; live, the ship emptied 1.2 s before them)
r = Run()
r.ship()
r.frame(60)
r.in_pod()
r.frame(30)
r.do('T.keep(T.ship, 3)')
r.outside(28)
r.do('T.main = T.dest')
r.frame(120)
check(r.rate() == 1, 'the hellpod launch is not sped up')
check(not any(p[1] == 'external_multiplier' and p[2] == 8 for p in
              (tuple(x.values()) for x in r.T.policy.values())), 'no x8 asked in the launch')

# the launch's outside world filling while the ship is still loaded and on screen: its own kind tells it (even in a
# world the FTL's size)
r = Run()
r.ship()
r.frame(60)
r.do('T.fill(T.dest, "e93e9835bce95d4a", 1)')
r.outside()
r.frame(30)
check(r.rate() == 1, 'the launch is not sped up when its kind shows first')

# the same while the loadout screen shows the Helldiver (the player is in the hellpod)
r = Run()
r.ship()
r.do('T.map.units[#T.map.units + 1] = T.diver({ 1, 2, 3 })')
r.frame(60)
r.outside()
r.frame(30)
check(r.rate() == 1, 'nothing sped up while the loadout screen is up')

# a mission: x1 at once; after it, its return's outside shot (the ship loading under it) with nothing sped up, until
# the shot is over; leaving the lobby 13 s later is sped up  waited for the 90 s)
r = Run()
r.ship()
r.frame(60)
r.outside()
r.frame()
check(r.rate() == 8, 'FTL fast before the mission test')
r.do('T.mw = T.world(); T.fill(T.mw, "aaaa000000000002", 13000); T.worlds[#T.worlds + 1] = T.mw')   # it loads
r.frame()
r.T.mission = True
r.frame()
check(r.rate() == 1, 'x1 the frame a mission starts')
r.do('T.main = T.mw')
r.frame(300)
check(r.rate() == 1, 'x1 throughout the mission, the outside world full')
r.do('T.keep(T.ship, 3); T.keep(T.dest, 1)')
r.T.mission = False
r.frame(2)                       # the mission's world still the main one, no outside shot yet
r.outside(41)
r.do('T.main = T.dest')
r.frame(60)
check(r.rate() == 1, 'nothing sped up in the return\'s outside shot')
r.do('T.keep(T.dest, 1); T.main = T.mw')    # the shot blinks out with the mission's world the main one
r.frame()
r.outside(41)
r.do('T.main = T.dest')
r.frame()
check(not any('the return from the mission is over' in l for l in r.lines()),
      'the return is not over while no ship loaded since the mission')
r.ship()
r.frame(10)
check(r.rate() == 1 and not any('SCENE lobby change' in l for l in r.lines()),
      'nor as the ship loads under it (no lobby change)')
r.inside()
r.frame()
check(any('the return from the mission is over' in l for l in r.lines()), 'the return is over once its shot is')
r.frame(13 * 60)
r.do('T.keep(T.ship, 3)')
r.outside(23)
r.do('T.main = T.dest')
r.frame()
check(r.rate() == 8, 'leaving the lobby 13 s after the return: sped up')
r.inside()
r.frame(95 * 60)
r.outside()
r.frame()
check(r.rate() == 8, 'an FTL long after the mission is sped up')

# ... a return with no outside shot seen  keeps the 90 s
r = Run()
r.ship()
r.frame(60)
r.T.mission = True
r.frame(60)
r.do('T.keep(T.ship, 3)')
r.T.mission = False
r.frame(30)
r.ship()
r.frame(13 * 60)
r.outside(17)
r.frame()
check(r.rate() == 1, 'a return with no outside shot: no lobby change sped up within the 90 s')

# other players in the session: the FTL sped up all the same, as host and not, and the session is logged
r = Run()
r.ship()
r.T.players = 2
r.frame(60)
r.outside()
r.frame()
check(r.rate() == 8, 'the FTL is sped up with another player in the session, as host')
r.inside()
r.frame(30)
r.T.host = False
r.T.players = 3
r.frame(60)
r.outside()
r.frame()
check(r.rate() == 8, 'the FTL is sped up with other players in the session, not host')
check(any('SESSION host, 2 players' in l for l in r.lines()) and any('SESSION not host, 3 players' in l for l in r.lines())
      and any('SCENE FTL starts' in l and 'not host, 3 players' in l for l in r.lines()), 'the session is logged')

# the cap: at most 45 s of game time fast, then x1 until the scene ends
r = Run()
r.ship()
r.frame(60)
r.outside()
r.frame(int(5.4 * 60))           # 5.4 s real at x8: 43 s of game time
check(r.rate() == 8, 'still fast before the cap')
r.frame(int(1 * 60))
check(r.rate() == 1, 'x1 after 45 s of game time')
r.frame(600)
check(r.rate() == 1, 'stays x1 while the capped scene goes on')
r.inside()
r.frame(30)
r.outside()
r.frame()
check(r.rate() == 8, 'the next scene is fast again')

# the hellpod entry: fast while the stepping-in clip plays, x1 once the Helldiver is in the pod
r = Run()
r.ship()
r.frame(60)
r.posture(15)
r.frame()
check(r.rate() == 8, 'the hellpod entry is sped up')
r.frame(30)
r.in_pod()
r.frame()
check(r.rate() == 1, 'x1 the frame the Helldiver is in the hellpod')
r.frame(60)
check(r.rate() == 1, 'stays x1 in the hellpod')

# a session that names our Helldiver: the one this game owns (another player's, listed first, speeds nothing up)
r = Run()
r.T.players = 2
r.ship()
r.friend()
r.frame(60)
r.do('T.other.anim[14] = 15')
r.frame(10)
check(r.rate() == 1, 'another player\'s hellpod entry speeds nothing up')
check(any('HELLDIVER owned (game object:owner 2:peer2 1:me) (2 in main world 1)' in l for l in r.lines()),
      'each Helldiver\'s game object and owner are logged')
r.posture(15)
r.frame()
check(r.rate() == 8, 'our hellpod entry is sped up with another player in the session')

# ... and several owned: none read
r = Run()
r.T.players = 2
r.ship()
r.friend()
r.do('T.owner[2] = "me"; T.other.anim[14] = 15')
r.frame(60)
check(r.rate() == 1 and any('not known yet (several owned' in l for l in r.lines()), 'several Helldivers owned: none read')

# no unit synchronizer (as in the game, : the only Helldiver while solo is ours, and stays ours once a
# friend comes aboard
r = Run()
r.T.sync = None
r.ship()
r.frame(60)
check(any('HELLDIVER the only one, solo (1 in main world 1)' in l for l in r.lines()), 'solo: the only Helldiver is ours')
r.T.players = 2
r.friend()
r.frame(60)
r.do('T.other.anim[14] = 15')
r.frame(10)
check(r.rate() == 1, 'a friend who came later: their hellpod entry speeds nothing up')
r.do('T.other.anim[14] = 3')
r.posture(15)
r.frame()
check(r.rate() == 8, 'ours, known from before the friend came: sped up')

# no unit synchronizer, two Helldivers from the start: none read until the camera follows ours, alone
r = Run()
r.T.sync = None
r.T.players = 2
r.ship()
r.friend()
r.frame(60)
check(any('not known yet (no unit synchronizer' in l for l in r.lines()), 'ours not known yet, and why')
r.do('T.other.anim[14] = 15')
r.frame(10)
check(r.rate() == 1, 'ours not known: a friend\'s hellpod entry speeds nothing up')
r.do('T.other.anim[14] = 0')
r.frame(40)
check(r.rate() == 1, 'host, ours not known: a friend\'s cryo pod speeds nothing up')
r.do('T.other.anim[14] = 3')
r.walk(3, friend_too=True)
check(not any('the camera follows' in l for l in r.lines()), 'two Helldivers walking with the camera: neither')
r.walk(2)
check(not any('the camera follows' in l for l in r.lines()), 'not after two moving samples')
r.walk(4)
check(any('HELLDIVER the one the camera follows' in l for l in r.lines()), 'ours: the one the camera follows')
r.do('T.other.anim[14] = 15')
r.frame(10)
check(r.rate() == 1, 'ours found: a friend\'s hellpod entry still speeds nothing up')
r.do('T.other.anim[14] = 3')
r.posture(15)
r.frame()
check(r.rate() == 8, 'ours found by the camera: our hellpod entry is sped up')

# just joined another's session: the only Helldiver in the cryo pod is ours
r = Run(mode=INSTANT)
r.T.sync = None
r.ship()
r.frame(60)
r.do('T.me.alive = false; for i, u in ipairs(T.ship.units) do if u == T.me then table.remove(T.ship.units, i) break end end')
r.T.host = False
r.T.players = 2
r.friend()
r.do('T.other.anim[14] = 15')    # the friend's Helldiver alone aboard before ours comes: not ours
r.frame(40)
check(r.speed() == 'x1', 'just joined, the friend\'s Helldiver alone aboard: not ours')
r.do('T.other.anim[14] = 3')
r.do('T.me = T.diver({ 1, 2, 3, 4, 5, 6, 7, 8, 59, 10, 11, 12, 13, 0, 0 }, 1); T.ship.units[#T.ship.units + 1] = T.me')
r.frame(40)
check(any('HELLDIVER the only one in the cryo pod, just joined' in l for l in r.lines())
      and any('SCENE cryo pod starts' in l for l in r.lines()), 'just joined: our cryo pod is sped up')

# ... but not a minute after joining, nor two in their pods
r = Run()
r.T.sync = None
r.ship()
r.frame(60)
r.do('T.me.alive = false; for i, u in ipairs(T.ship.units) do if u == T.me then table.remove(T.ship.units, i) break end end')
r.T.host = False
r.T.players = 2
r.friend()
r.frame(61 * 60)
r.do('T.me = T.diver({ 1, 2, 3, 4, 5, 6, 7, 8, 59, 10, 11, 12, 13, 0, 0 }, 1); T.ship.units[#T.ship.units + 1] = T.me')
r.frame(40)
check(r.rate() == 1, 'a minute after joining: a Helldiver in the cryo pod isn\'t taken as ours')
r = Run()
r.T.sync = None
r.T.players = 2
r.ship()
r.friend()
r.do('T.other.anim[14] = 0; T.me.anim[14] = 0')
r.frame(30)
r.T.host = False
r.frame(60)
check(not any('HELLDIVER the only one in the cryo pod' in l for l in r.lines()),
      'just joined, two Helldivers in their pods: neither taken as ours')
check(r.rate() == 8, '... though ours is in one of them: sped up (every player\'s Helldiver in the pod)')

# host: a friend's cryo pod speeds nothing up
r = Run()
r.T.sync = None
r.ship()
r.frame(60)
r.T.players = 2
r.friend()
r.do('T.other.anim[14] = 0')
r.frame(60)
check(r.rate() == 1, 'host: a friend\'s cryo pod speeds nothing up')

# the cryo pod: our Helldiver in the pod's loop, then its walk-out (Fast: x8 throughout)
r = Run()
r.ship()
r.T.players = 2
r.frame(60)
r.posture(0)
r.frame()
check(r.rate() == 8, 'Fast: the cryo pod is sped up')
r.frame(20)
r.posture(6)
r.frame(40)
check(r.rate() == 8, 'Fast: the walk-out too')
r.posture(3)
r.frame()
check(r.rate() == 1, 'Fast: x1 the frame the Helldiver is out of the cryo pod')

# the drop zoom: a click on the drop location map from inside the hellpod; x1 1 s of game time after the loadout page
r = Run()
r.ship()
r.map_page()
r.in_pod()
r.frame(60)
r.frame(click=True)
check(r.rate() == 8, 'a click on the drop location map speeds the zoom up')
r.frame(4)                       # 4 frames at x8: 0.53 s of game time
r.do('T.map.units[#T.map.units + 1] = T.diver({ 1, 2, 3 })')   # the loadout page: its Helldiver
r.frame(4)
check(r.rate() == 8, 'still fast in the move into the loadout view')
r.frame(6)
check(r.rate() == 1, 'x1 once the move into the loadout view is over')
r.frame(click=True)
check(r.rate() == 1, 'a click on the loadout page speeds nothing up')

# a click on the map with no loadout page after it: x1 after 1.5 s of game time
r = Run()
r.ship()
r.map_page()
r.in_pod()
r.frame(60)
r.frame(click=True)
r.frame(14)                      # 1.9 s of game time
check(r.rate() == 1, 'x1 when no loadout page follows the click')

# a click anywhere else speeds nothing up
r = Run()
r.ship()
r.map_page()
r.frame(60)
r.frame(click=True)
r.frame()
check(r.rate() == 1, 'a click outside the hellpod speeds nothing up')

# the ship's first load is scanned at once, even right after another scan: a walk to the bridge that empties the
# destroyer's world early is still told by the ship's camera
r = Run()
r.outside(54)
r.do('T.main = T.dest')
r.frame(10)
r.do('T.keep(T.dest, 6)')
r.ship()
r.frame()
r.do('T.ship.units[1].cam.fov = 0.262')
r.frame(2)
r.inside()
r.frame(5)
check(r.rate() == 8, 'still fast in a walk that empties the destroyer\'s world 0.2 s after a scan')

# the F9 menu: a row per scene, Off / Fast (x8) / Instant, Instant by default
r = Run(mode=None)
check(sorted(r.T.specs.keys()) == sorted(ROWS), 'a row for each scene')
check(all(r.T.rows[row] == INSTANT and r.T.specs[row].choices[2] == 'Fast (x8)' for row in ROWS),
      'every row Off / Fast (x8) / Instant, Instant by default')
check(any('FTL transition Instant' in l for l in r.lines()), 'the start line names each row\'s mode')

# Instant: at x1 the clock jumps 1 s every frame while the FTL plays, no more jumps once it ends
r.ship()
r.frame(60)
r.outside()
r.frame()
check(r.speed() == 'jump', 'Instant: the FTL starts jumping, at x1')
r.frame(5)
check(r.speed() == 'jump' and r.dt > 1, 'Instant: each frame\'s step has the jump asked in the last')
r.inside()
r.frame()
check(r.speed() == 'x1', 'Instant: no jump asked the frame the FTL ends')
check(any('SCENE FTL over' in l and '6 jumps' in l for l in r.lines()), 'the scene\'s jumps are logged')
check(not any(p[1] == 'external_multiplier' and p[2] == 8 for p in
              (tuple(x.values()) for x in r.T.policy.values())), 'Instant: no x8 asked in a short scene')
check(len(r.T.notes) == 0, 'Instant: no notice')

# Fast shows its notices, x8 and the x1 after it
r = Run(mode=FAST)
r.ship()
r.frame(60)
r.outside()
r.frame(10)
r.inside()
r.frame()
check(list(r.T.notes.values()) == ['TIME X8', 'TIME X1'], 'Fast: a notice at x8 and at the x1 after it')

# Instant: at most 20 s jumped in an FTL, then x8 for the rest, and x1 after 45 s of game time
r = Run(mode=INSTANT)
r.ship()
r.frame(60)
r.outside()
r.frame()
r.frame(19)
check(r.speed() == 'jump', 'Instant: still jumping after 19 s jumped')
r.frame()
check(r.speed() == 'x8', 'Instant: x8 once 20 s were jumped')
r.frame(180)                     # 20.3 + 24.0 s of game time
check(r.speed() == 'x8', 'Instant: x8 until the cap')
r.frame(10)
check(r.speed() == 'x1', 'Instant: x1 after 45 s of game time, jumps in')
check(len(r.T.notes) == 0, 'Instant: no notice for its x8 or the x1 after it')

# Instant log-in intro: the outside shot jumps 6 s, then x8 while the ship loads; the walk to the bridge jumps again,
# and its wait for the camera counts paced time, so the jumps don't use it up
r = Run(mode=INSTANT)
r.outside(54)
r.do('T.main = T.dest')
r.frame()
check(r.speed() == 'jump', 'Instant: the log-in intro jumps')
r.frame(5)
check(r.speed() == 'jump', 'Instant: the outside shot still jumps after 5 s')
r.frame()
check(r.speed() == 'x8', 'Instant: x8 once the outside shot jumped 6 s (waiting for the ship)')
r.frame(30)
r.do('T.keep(T.dest, 6)')
r.ship()
r.frame()
check(r.speed() == 'jump', 'Instant: the walk to the bridge jumps again')
r.frame(9)                       # 10 s of game time jumped, 1.3 s paced
r.do('T.ship.units[1].cam.fov = 0.262')
r.frame(3)
check(r.speed() == 'jump', 'Instant: still the log-in intro when the walk starts 10 jumps after the ship loaded')
r.do('T.ship.units[1].cam.fov = 1.134')
r.frame()
check(r.speed() == 'x1', 'Instant: x1 the frame the camera goes wide')
check(any('the ship is there' in l for l in r.lines()), 'the ship\'s arrival in the log-in intro is logged')

# ... and a ship that takes long to load: the outside shot's cap, then the walk to the bridge jumps all the same
r = Run(mode=INSTANT)
r.outside(54)
r.do('T.main = T.dest')
r.frame(320)                     # 6.1 s jumped, then 41.7 s at x8
check(r.speed() == 'x1', 'Instant: x1 once the outside shot reached the cap')
r.do('T.keep(T.dest, 6)')
r.ship()
r.frame(2)
check(r.speed() == 'jump', 'Instant: the walk to the bridge has its own cap')

# Instant drop zoom: the wait for the loadout page counts paced time; the camera's move into it game time
r = Run(mode=INSTANT)
r.ship()
r.map_page()
r.in_pod()
r.frame(60)
r.frame(click=True)
check(r.speed() == 'jump', 'Instant: the drop zoom jumps')
r.frame(2)                       # 2 s of game time jumped, 0.27 s paced
check(r.speed() == 'jump', 'Instant: still waiting for the loadout page after 2 jumps')
r.do('T.map.units[#T.map.units + 1] = T.diver({ 1, 2, 3 })')   # the loadout page: its Helldiver
r.frame()
check(r.speed() == 'jump', 'Instant: jumping through the move into the loadout view')
r.frame()
check(r.speed() == 'x1', 'Instant: x1 a jump after the loadout page opened')

# Instant hellpod entry, and no more jumps once a mission starts
r = Run(mode=INSTANT)
r.ship()
r.frame(60)
r.posture(15)
r.frame()
check(r.speed() == 'jump', 'Instant: the hellpod entry jumps')
r.in_pod()
r.frame()
check(r.speed() == 'x1', 'Instant: no jump once the Helldiver is in the hellpod')
r.outside()
r.frame(3)
r.T.mission = True
r.frame()
check(r.speed() == 'x1', 'Instant: no jump the frame a mission starts')

# Instant cryo pod (not host): jumps in the pod's loop; the walk-out's first 30 frames at x8 (the game places the
# Helldiver), then jumps again
r = Run(mode=INSTANT)
r.ship()
r.T.players = 2
r.T.host = False
r.frame(60)
r.posture(0)
r.frame()
check(r.speed() == 'jump', 'Instant: the cryo pod jumps')
r.frame(3)
r.posture(6)
r.frame()
check(r.speed() == 'x8', 'Instant: the walk-out starts at x8')
r.frame(29)
check(r.speed() == 'x8', 'Instant: 30 frames of the walk-out at x8')
r.frame()
check(r.speed() == 'jump', 'Instant: jumps again after them')
r.posture(3)
r.frame()
check(r.speed() == 'x1', 'Instant: x1 once out of the cryo pod')
check(any('cryo pod: the walk-out after' in l for l in r.lines()), 'the walk-out is logged')

# rows: Off leaves its scene alone (and only it), Fast is x8 without jumps, a change counts the next frame
r = Run(mode=INSTANT)
r.set('ftl', OFF)
r.ship()
r.frame(60)
r.outside()
r.frame(30)
check(r.speed() == 'x1', 'an FTL set Off plays at x1')
check(any('OPTION FTL transition: Off' in l for l in r.lines()), 'a row change is logged')
r.inside()
r.frame(30)
r.posture(15)
r.frame()
check(r.speed() == 'jump', 'the hellpod entry still jumps with the FTL Off')
r.in_pod()
r.frame(30)
r.set('ftl', FAST)
r.outside()
r.frame(5)
check(r.speed() == 'x8', 'an FTL set Fast runs at x8 without jumps')
r.set('ftl', INSTANT)
r.frame()
check(r.speed() == 'jump', 'Fast to Instant mid-scene: jumps at x1')
r.set('ftl', OFF)
r.frame()
check(r.speed() == 'x1', 'Off mid-scene: x1 and no jump')

# what is logged: the Helldiver, its posture, what a small world shows
r = Run()
r.ship()
r.frame(60)
before = len(r.T.log)
r.posture(3)
r.frame()
check(any(' ANIM L14 36>3' in l for l in r.lines(before)), 'a posture change is logged at once')
check(any('HELLDIVER the only one, solo (1 in main world' in l for l in r.lines()), 'our Helldiver is found')
before = len(r.T.log)
r.map_page()
r.frame()
check(any('WORLD 3 (20 units) shows the map floor' in l for l in r.lines(before)), 'a small world\'s marker is logged')

# a lobby change: the destroyer's small outside world shows its cannons while the old ship is still the main world
#  second join): sped up as it begins over our ship, as the old ship empties and while the next one loads
# (x8 once the jumps are spent), with jumps again once it has loaded under the shot (the FTL's row); no FTL
r = Run(mode=INSTANT)
r.ship()
r.frame(60)
r.outside(17)
r.frame(2)
check(r.speed() == 'jump', 'a lobby change\'s small outside shot over our loaded ship: sped up')
r.do('T.keep(T.ship, 3); T.main = T.dest')
r.frame(30)
check(r.speed() == 'x8', 'x8 while the next ship loads, the jumps spent')
r.ship()
r.frame()
check(r.speed() == 'jump' and any('lobby change: the next ship is there' in l for l in r.lines()),
      'a lobby change: jumps again once the next ship has loaded under the outside shot')
r.do('T.main = T.dest')
r.frame()
r.do('T.main = T.ship')
r.frame()
check(r.speed() == 'jump', 'still while the main world swaps between the two ')
r.inside()
r.frame()
check(r.speed() == 'x1' and any('SCENE lobby change over' in l for l in r.lines())
      and not any('SCENE FTL' in l for l in r.lines()), 'x1 the frame the cannons go; no FTL')
r.frame(60)
r.outside(28)
r.do('T.main = T.dest')
r.frame(5)
check(r.speed() == 'x1', 'a small outside shot later, the main one, the same ship still loaded: no lobby change')

# joining from the galactic map : the small shot over our loaded ship, then an FTL whose world shrinks
# for the arrival but keeps its cannons: both sped up to their ends
r = Run(mode=INSTANT)
r.ship()
r.frame(60)
r.outside(25)
r.frame()
check(r.speed() == 'jump', 'joining: the small shot over our ship is sped up')
r.inside()
r.frame()
check(r.speed() == 'x1', 'x1 once its cannons go')
r.outside()
r.frame(3)
check(r.speed() == 'jump', 'joining: its FTL is sped up')
r.do('for i = 1, 500 do table.remove(T.dest.units, 2).alive = false end')   # 90 units left, the cannons with them
r.frame(2)
check(r.speed() == 'jump', 'still sped up as the FTL\'s world shrinks for the arrival')
check(not any('SCENE FTL over' in l for l in r.lines()), 'the FTL is not over before its cannons go')
r.inside()
r.frame()
check(r.speed() == 'x1', 'x1 once the arrival\'s cannons go')

# ... left alone with the FTL's row Off, and back from a mission (the ship loads under an outside shot too)
r = Run(mode=INSTANT)
r.set('ftl', OFF)
r.ship()
r.frame(60)
r.outside(17)
r.do('T.keep(T.ship, 3); T.main = T.dest')
r.frame(30)
r.ship()
r.frame(5)
check(r.speed() == 'x1', 'a lobby change with the FTL transition Off: x1')
r = Run(mode=INSTANT)
r.ship()
r.frame(60)
r.T.mission = True
r.do('T.keep(T.ship, 3); T.main = T.dest')
r.outside(17)
r.frame(60)
r.T.mission = False
r.frame(30)
r.ship()
r.frame(30)
check(r.speed() == 'x1', 'the return from a mission: a ship loaded under the outside shot, not sped up')

# joining a lobby whose players are in their hellpods: every Helldiver plays the stepping-in clip at once ;
# ours not known, a posture every player's Helldiver shares is ours too
r = Run(mode=INSTANT)
r.T.sync = None
r.ship()
r.frame(60)
r.do('T.me.alive = false; for i, u in ipairs(T.ship.units) do if u == T.me then table.remove(T.ship.units, i) break end end')
r.T.host = False
r.T.players = 3
r.do('T.a = T.diver({ 1, 2, 3, 4, 5, 6, 7, 8, 59, 10, 11, 12, 13, 36, 0 }, 2, 5, 5); '
     'T.b = T.diver({ 1, 2, 3, 4, 5, 6, 7, 8, 59, 10, 11, 12, 13, 36, 0 }, 3, 9, 9); '
     'T.ship.units[#T.ship.units + 1] = T.a; T.ship.units[#T.ship.units + 1] = T.b')
r.frame(40)
r.do('T.a.anim[14] = 15; T.b.anim[14] = 15')
r.frame(5)
check(r.speed() == 'x1', 'two players\' Helldivers stepping in, ours not aboard yet: nothing sped up')
r.do('T.me = T.diver({ 1, 2, 3, 4, 5, 6, 7, 8, 59, 10, 11, 12, 13, 36, 0 }, 1); T.ship.units[#T.ship.units + 1] = T.me')
r.frame(40)
check(r.speed() == 'x1', 'ours aboard, not stepping in: nothing sped up')
r.posture(15)
r.frame()
check(r.speed() == 'jump' and any('ANIM all 3 Helldivers L14 15' in l for l in r.lines()),
      'every player\'s Helldiver stepping in: sped up')
r.do('T.a.anim[14] = 17; T.b.anim[14] = 17')
r.in_pod()
r.frame()
check(r.speed() == 'x1', 'x1 once they are all in their hellpods')

# a client's FTL: the destroyer's big outside world is the main one for a while ; the FTL is sped up, and
# ours stays known through it, so its hellpod entry after the FTL is sped up
r = Run(mode=INSTANT)
r.T.sync = None
r.ship()
r.frame(60)
r.T.players = 2
r.T.host = False
r.friend()
r.frame(60)
r.outside()
r.do('T.main = T.dest')
r.frame()
check(r.speed() == 'jump', 'a client\'s FTL, its outside world the main one: sped up')
r.frame(5)
check(not any('ours gone' in l for l in r.lines()) and any('kept in world 1' in l for l in r.lines()),
      'ours kept while the FTL\'s world is the main one')
r.inside()
r.do('T.main = T.ship')
r.frame(30)
r.posture(15)
r.frame()
check(r.speed() == 'jump', 'ours kept through the FTL: its hellpod entry is sped up')

# ours is let go when its world no longer holds the ship (a lobby change; a handle left alive counts for nothing),
# and in a mission
r = Run()
r.ship()
r.frame(60)
r.do('T.keep(T.ship, 3); T.me.alive = true; T.main = T.map')
r.frame(5)
check(any('ours gone (its world no longer holds the ship)' in l for l in r.lines()), 'ours let go when the ship empties')
r = Run()
r.ship()
r.frame(60)
r.T.mission = True
r.frame()
check(any('ours gone (a mission)' in l for l in r.lines()), 'ours let go in a mission')

# ours is taken on the ship only (not a Helldiver in a small main world)
r = Run()
r.do('T.map.units[#T.map.units + 1] = T.diver({ 1, 2, 3 }); T.main = T.map')
r.frame(30)
check(not any('the only one, solo' in l for l in r.lines()), 'no Helldiver taken off the ship')

# with other players in the session the drop zoom waits for them: a click on the map speeds nothing up ;
# the click, the cameras that move and the other Helldivers' postures are logged
r = Run(mode=INSTANT)
r.T.sync = None
r.ship()
r.frame(60)
r.T.players = 2
r.friend()
r.map_page()
r.in_pod()
r.frame(60)
r.frame(click=True)
r.frame(5)
check(r.speed() == 'x1' and not any('SCENE drop zoom' in l for l in r.lines()),
      'other players aboard: a click on the drop map speeds nothing up')
r.do('T.other.anim[14] = 15')
r.frame(2)
check(any('ANIM other 1 L14 3>15' in l for l in r.lines()), 'another Helldiver\'s posture is logged')
check(r.speed() == 'x1', 'and speeds nothing up')

# Instant cryo pod: the wait in the pod jumps up to 12 s, then x8 (after joining it waits for loading: 2.3 to 3.5 s
# real whether 16 or 40 s were jumped, , not capped by 3.4 s real of it; the walk-out has
# jumps and a cap of its own
r = Run(mode=INSTANT)
r.ship()
r.T.players = 2
r.T.host = False
r.frame(60)
r.posture(0)
r.frame()
r.frame(10)
check(r.speed() == 'jump', 'Instant: the cryo pod still jumps after 10 s')
r.frame(2)
check(r.speed() == 'x8', 'Instant: x8 once 12 s were jumped in the pod')
r.frame(225)                     # 3.75 s real at x8: the scene's game time past 42 s
check(r.speed() == 'x8', 'Instant: still x8 after 3.7 s real in the pod (no cap)')
r.posture(6)
r.frame(30)
check(r.speed() == 'x8', 'Instant: the walk-out\'s 30 frames at x8')
r.frame()
check(r.speed() == 'jump', 'Instant: then jumps of its own, past the wait\'s cap')
r.posture(3)
r.frame()
check(r.speed() == 'x1', 'Instant: x1 once out of the cryo pod')

# joining on the same planet : the old ship empties as the destroyer's small shot shows its cannons;
# sped up from then, through the next ship's load, to the cannons' end
r = Run(mode=INSTANT)
r.ship()
r.frame(60)
r.outside(25)
r.do('T.main = T.dest')
r.frame(15)
r.do('T.keep(T.ship, 3)')
r.frame()
check(r.speed() == 'jump', 'joining: sped up as the old ship empties under the outside shot')
r.frame(60)
r.ship()
r.do('T.main = T.ship')
r.frame()
check(r.speed() == 'jump', 'joining: jumps again once the next ship is there')
r.inside()
r.frame()
check(r.speed() == 'x1', 'joining: x1 once the cannons go')

# a client's hellpod entry: after the clip the camera holds its close-up on the pod (fov 0.611), then pulls out to the
# drop location map (1.222); sped up until the map's view, with jumps of its own; 10 s of game time at most
r = Run(mode=INSTANT)
r.ship()
r.frame(60)
r.T.players = 2
r.T.host = False
r.posture(15)
r.frame(8)
r.in_pod(0.611)
r.frame()
check(r.speed() == 'jump' and any('hellpod entry: in the hellpod after' in l and 'fov 0.611' in l for l in r.lines()),
      'a client in the hellpod, the camera\'s close-up on the pod: still sped up')
r.frame(5)
check(r.speed() == 'jump', 'the close-up has jumps of its own (the clip spent 9 of 12)')
r.do('T.ship.units[1].cam.fov = 1.0')
r.frame()
check(r.speed() == 'x8', 'x8 while it pulls out, its jumps spent')
r.do('T.ship.units[1].cam.fov = 1.222')
r.frame()
check(r.speed() == 'x1', 'x1 once the camera is on the drop location map')
r = Run(mode=INSTANT)
r.ship()
r.frame(60)
r.posture(15)
r.frame(3)
r.in_pod(0.611)
r.frame(80)                      # 6 jumps, then 74 frames at x8: past 10 s of game time
check(r.speed() == 'x1' and any('SCENE hellpod entry over' in l for l in r.lines()),
      'a close-up longer than 10 s of game time: x1')

# the host's drop zoom with a friend aboard: a click on the map as the friend steps in; sped up once every player's
# Helldiver is in its hellpod, until the camera's move into the loadout view is over; once a stay in the pod
r = Run(mode=INSTANT)
r.T.sync = None
r.ship()
r.frame(60)
r.T.players = 2
r.friend()
r.map_page()
r.in_pod()
r.do('T.other.anim[14] = 15')
r.frame(30)
r.frame(click=True)
r.frame(5)
check(r.speed() == 'x1', 'host: a click while the friend steps in speeds nothing up yet')
r.do('T.other.anim[14] = 17')
r.frame()
check(r.speed() == 'jump', 'host: the zoom jumps once every Helldiver is in its hellpod')
r.frame()
check(r.speed() == 'jump', 'still while the camera rests on the map')
r.do('T.ship.units[1].cam.y = 0.1')
r.frame()
check(r.speed() == 'jump' and any('drop zoom: the camera moves into the loadout view' in l for l in r.lines()),
      'jumping through the camera\'s move into the loadout view')
r.frame()
check(r.speed() == 'x1', 'x1 a jump after the camera began its move')
r.frame(click=True)
r.frame()
check(r.speed() == 'x1', 'a click on the loadout page speeds nothing up')
r.in_pod()
r.posture(16)
r.frame(5)
r.in_pod()
r.frame(5)
r.frame(click=True)
check(r.speed() == 'jump', 'in the pod again: a new click, every Helldiver in: the zoom again')

# ... nothing without a click, nor as a client; a pick that brings no camera move ends after 1.5 s paced, and the next
# click may try again
r = Run(mode=INSTANT)
r.T.sync = None
r.ship()
r.frame(60)
r.T.players = 2
r.friend()
r.map_page()
r.in_pod()
r.do('T.other.anim[14] = 17')
r.frame(30)
check(r.speed() == 'x1', 'host, everyone in the pods, no click: nothing sped up')
r.frame(click=True)
check(r.speed() == 'jump', 'host: a click with everyone in: the zoom')
r.frame(30)
check(r.speed() == 'x1' and any('no loadout page after the click' in l for l in r.lines()),
      'no camera move after the pick: x1')
r.frame(click=True)
check(r.speed() == 'jump', 'the next click tries again')
r = Run(mode=INSTANT)
r.T.sync = None
r.ship()
r.frame(60)
r.T.players = 2
r.T.host = False
r.friend()
r.map_page()
r.in_pod()
r.do('T.other.anim[14] = 17')
r.frame(30)
r.frame(click=True)
r.frame(3)
check(r.speed() == 'x1', 'a client\'s click with everyone in speeds nothing up (its zoom follows the host\'s)')

# back on the map from the loadout view, a new pick zooms again 1.2 s from the click to the camera's
# move, then 0.9 s), as host with others and alone; not before the camera is back, nor without a click
r = Run(mode=INSTANT)
r.T.sync = None
r.ship()
r.frame(60)
r.T.players = 2
r.friend()
r.map_page()
r.in_pod()
r.do('T.other.anim[14] = 17')
r.frame(30)
r.frame(click=True)
r.do('T.ship.units[1].cam.y = 0.1')
r.frame(3)
r.do('T.ship.units[1].cam.y = 1.2')            # in the loadout view
r.frame(5)
check(r.speed() == 'x1', 'host: x1 in the loadout view')
r.do('T.ship.units[1].cam.y = 0.4')            # going back to the map
r.frame(3)
r.frame(click=True)
r.frame()
check(r.speed() == 'x1', 'a click before the camera is back on the map speeds nothing up')
r.do('T.ship.units[1].cam.y = 0.01')
r.frame(5)
check(r.speed() == 'x1' and any('back on the drop location map' in l for l in r.lines()),
      'back on the map: nothing sped up without a click')
r.frame(click=True)
check(r.speed() == 'jump', 'host: a pick again zooms again')
r.frame()
check(r.speed() == 'jump', 'still while the camera rests on the map')
r.do('T.ship.units[1].cam.y = 0.2')
r.frame()
r.frame()
check(r.speed() == 'x1', 'x1 a jump after the camera began its move')
r = Run()
r.ship()
r.map_page()
r.in_pod()
r.frame(60)
r.frame(click=True)
r.frame(4)
r.do('T.map.units[#T.map.units + 1] = T.diver({ 1, 2, 3 })')   # the loadout page: its Helldiver
r.frame(10)
r.do('T.ship.units[1].cam.y = 1.2')
r.frame(5)
r.frame(click=True)
check(r.rate() == 1, 'alone: a click in the loadout view speeds nothing up')
r.do('T.ship.units[1].cam.y = 0')               # back on the map, the loadout page's Helldiver still there
r.frame(5)
check(r.rate() == 1, 'alone: back on the map, nothing sped up without a click')
r.frame(click=True)
check(r.rate() == 8, 'alone: a pick again zooms again')
r.frame(9)                       # 1.2 s of game time, as the 1.2 s at x1 live
check(r.rate() == 8, 'alone: still fast while the camera rests on the map')
r.do('T.ship.units[1].cam.y = 0.2')
r.frame(9)
check(r.rate() == 1, 'alone: x1 once the camera\'s move is over')
r.do('T.ship.units[1].cam.y = 1.2')
r.frame(5)
r.frame(click=True)
check(r.rate() == 1, 'alone: a click in the loadout view after a pick again speeds nothing up')
r.do('T.ship.units[1].cam.y = 0')
r.frame(5)
check(any(l.endswith('back on the drop location map') for l in r.lines()[-5:]), 'alone: back on the map again')
r.posture(16)
r.frame()
r.in_pod()
r.frame(5)
r.frame(click=True)
check(r.rate() == 1, 'alone, in the pod again with the loadout page\'s Helldiver: no pick again yet')

# switched off in the F9 menu mid-scene: the game's clock goes back
r = Run()
r.outside(54)
r.do('T.main = T.dest')
r.frame()
check(r.rate() == 8, 'a scene at x8')
r.mod.on_stop()
check(r.rate() == 1, 'stopped: x1 again')
check(r.T.title == 'Impatient Diver (CSL/EAC)' and all(len(s.hint) <= 200 for s in r.T.specs.values()),
      'each row has a hint Chef shows whole')
if failures:
    print('FAILED:', *failures, sep='\n  ')
    sys.exit(1)
print('tests: all checks passed')
