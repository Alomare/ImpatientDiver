-- HD2-Addon: mods/alomare/skip_intro_animation
-- HD2-Requires: chef-shared-loader >= 1.5.1
-- Impatient Diver, for Chef Shared Loader (Lua 5.1, no FFI). How it works in the game: RESEARCH.md.
-- It speeds scenes up by itself, each as its row in the F9 menu says (Off, Fast or Instant; Instant by default):
--   the log-in intro: from its outside shot until our Helldiver can move after its walk to the bridge, or the ship's
--   camera, narrowed for the walk, is wide again;
--   the cryo pod (joining a lobby): while our Helldiver is in the pod's loop or its walk-out clip;
--   the FTL: while the Super Destroyer's big outside world (the FTL's) holds its cannons;
--   a lobby change (joining or leaving, on the FTL's row): the destroyer's small outside shot as it begins over our
--   loaded ship or as the old ship empties, and from a ship's load under it, until its cannons go;
--   the hellpod entry: while our Helldiver plays its stepping-in clip, then while the camera holds its close-up on
--   the pod (a client's, before it pulls out to the drop location map);
--   the drop zoom: alone, from a click on the drop location map, from inside the hellpod, until the loadout page opens
--   and its camera move is over (once the loadout screen has shown, a click on its pages is no pick: its weapon and
--   grenade pages hide the Helldiver as the map does); as host with others, from the moment every player's Helldiver
--   is in its hellpod after a click, until the camera's move into the loadout view is over (a client's zoom follows
--   the host's); back on the map from the loadout view, the next click zooms again (alone too), until the camera's
--   move is over.
-- Fast: time x8. Instant: at x1 the clock jumps 1 s every frame, up to a bit more than the scene's length, then x8 for
-- what is left (the log-in intro's outside shot and its walk to the bridge each have their own jumps and cap, as do
-- the cryo pod's wait and its walk-out; the walk-out starts with 30 frames at x8, for the game to place the Helldiver).
-- Back to x1 the frame the scene ends, or after 45 s of game time. Never in a mission or in the hellpod launch, and no
-- outside shot in the return from a mission (until its own is over, 90 s at most). With other players too: only our
-- own Helldiver's posture counts (found as the Helldiver section says; until then only a posture every player's
-- Helldiver shares). Only Fast shows a notice.
-- Solo Pause (its own F9 row, Off by default): a key holds the game's clock while no one else is in the session.
-- Log: ImpatientDiver.log in the loader's folder (%APPDATA%\Arrowhead\Helldivers2): the scenes with their game time
-- and jumps, the speed changes, the session and what marks the scenes. Each line starts with the real seconds since
-- the mod started.
local chef = ...
local M = { version = '10' }
local TITLE = 'Impatient Diver'   -- the name mod loaders show (the F9 menu's group; Arsenal's in the build)

local sr = stingray
local Application, World, Unit, Camera, Vector3, IdString64 =
  sr.Application, sr.World, sr.Unit, sr.Camera, sr.Vector3, sr.IdString64
local clock, fmt, min = os.clock, string.format, math.min

local FAST = 8
local JUMP = 1               -- Instant: game seconds the clock jumps each frame (one 5 s jump was fine in every scene)
local STEP_MOST = 0.2        -- the engine's longest step (system_step_range): only a jump makes a longer one
-- Instant: game seconds jumped at most a scene, so a wait for loading can't use up more; x8 for the rest. Jumped, the
-- FTL took 14 s, the hellpod entry 8 and the drop zoom 4 or 5 (each phase ends up to a jump late). The
-- log-in intro's outside shot has 3.33 s of timed phases, then waits for the ship to load (1.35 s real at x8 and
-- jumped alike); its walk to the bridge gets jumps of its own once the ship is there. The cryo pod: the pod rolling in
-- and a 1 s wait alone (7 or 8 jumps), but after joining a lobby a wait for loading (2.3 to 3.5 s real
-- whether 16 or 40 s were jumped), then the 7.5 s walk-out with its own jumps. A lobby
-- change: 0.5 to 2.4 s real from the old ship's going to the next one's load (joining takes longest), then 3 to 6 jumps
-- (lobby join phase 3 waits 5 s); that part has jumps of its own. The hellpod entry: 8 jumps for the clip, then a
-- client's camera held its close-up on the pod 2.4 s at x1 (a host's is on the map as the clip ends).
local JUMP_MOST = { ['log-in intro'] = 6, walk = 16, ['cryo pod'] = 12, ['walk-out'] = 12, FTL = 20,
                    ['lobby change'] = 12, ['hellpod entry'] = 12, ['pod view'] = 6, ['drop zoom'] = 7 }
local PLACE_FRAMES = 30      -- the cryo pod's walk-out at x8 first: the game places the Helldiver a few frames in
local CAP = 45               -- game seconds a scene (each part of the log-in intro) may be sped up
local WALK_CAP = 24          -- ... but the walk to the bridge (7 to 12 jumped): then the log-in intro is over
local WALK_SETTLE = 1        -- game seconds (jumps in) the walk goes on once our Helldiver can move (its camera
                             -- widens 0.5 s after that, for 1.4 s; jumped on, a player holding a key ran meanwhile)
local AFTER_MISSION = 90     -- real seconds at most after a mission with no outside shot sped up (the return plays as
                             -- it is): until the ship has loaded with no outside shot left
local WIDE_FOV = 1.0         -- the main camera wider than this (1.134 in play): the player has it
local MAP_FOV = 1.2          -- ... and in the hellpod, as wide as this: the drop location map's view (1.222, 70 degrees)
local POD_VIEW = 10          -- game seconds at most of the camera's close-up on the pod after the stepping-in clip
local EMPTIED_EARLY = 0.25   -- real seconds the old ship may empty before the destroyer's cannons show (the same frame)
-- The waits below are paced: game seconds as x8 would have made them, the jumps left out (what loads takes real time)
local WALK_WAIT = 3          -- after the ship loads in the log-in intro, for its camera to narrow
local ZOOM_RAMP = 1.5        -- from a click on the drop location map to the loadout page, at most
local ZOOM_MOVE = 1          -- game seconds (jumps in) of the camera's move into the loadout view (a 1 s blend)
local SMALL = 1200           -- a world up to this size has its kinds counted whenever its unit count changes
local SHIP = 1000            -- a main world bigger than this, off missions: the ship
-- the destroyer's outside world in an FTL has 584 to 593 units (every FTL so far, host and client); the outside shots
-- of joining or leaving a lobby 11 to 24, the hellpod launch's 25 to 33, the log-in intro's 62 or 63
local FTL_UNITS = 300
local SCAN_MOST = 8000       -- a world bigger than this (a mission) isn't scanned
local SCAN_SECONDS = 2       -- the big worlds' kinds and the main world's cameras
local SCAN_AGAIN = 1         -- real seconds at least between two scans asked by a new main world
local SCAN_SLOW = 8          -- a scan's milliseconds logged over this
local RATE_SECONDS = 1       -- game time against real time, while sped up
local SESSION_SECONDS = 0.5  -- the session (host or not, players) read again
local DIVER_SECONDS = 0.5    -- the Helldiver looked up again
local JOIN_SECONDS = 60      -- after joining another's session: the only Helldiver in the cryo pod is ours
local FOLLOW_SECONDS = 0.25  -- the camera and the Helldivers sampled, to find ours among several
local FOLLOW_MOVE = 0.5      -- a sample counts when the camera moved this much since the last
local FOLLOW_KEEP = 0.3      -- ... and ours kept its offset to the camera within this share of the move
local FOLLOW_NEAR = 8        -- ours is at most this far from the camera
local FOLLOW_SAMPLES = 4     -- moving samples in a row in which ours alone kept its offset
local CAM_MOVE = 0.02        -- metres the main camera moves as the zoom's end begins
local VIEW_AWAY = 0.5        -- metres the main camera is from the drop location map's spot: in the loadout view (1.2 m)
local MAP_BACK = 0.1         -- ... and within this of it again: back on the map (0.01 m off)
local CAMERA_KIND = '465f4895f3dc98d1'    -- core/units/camera
local HELLDIVER = '4d1c334d294dfa97'      -- content/fac_helldivers/cha_avatar/avatar_helldiver
-- the posture layer's states in this build's avatar_helldiver (0-based, as Unit.animation_get_state reports them):
-- the clip stepping into the hellpod (entered by event 0xa9b0a3bb from any state) and the loop inside it, which the
-- clip's end event leads to; the cryo pod's loop (event 0x2a49b45b) and its walk-out clip (event 0x23173e19, as in
-- build 25480438; its end event leads to 3, normal play); the walk to the bridge after the log-in (a clip whose end
-- event leads to 3) and normal play
local POSTURE, POD_ENTER, POD_IN, CRYO_IN, CRYO_OUT, WALK_CLIP, PLAY = 14, 15, 17, 0, 6, 18, 3
local MAP_KIND = '96af7d6acb949f34'       -- content/art_shared/meshes/plane_2x2m: the loadout screen's world
-- content/env_ship/hangar/se_destroyer_supportcannon_ missile_launcher, orbital_cannon_single, orbital_gatling_single,
-- planet_killer (the ship's world has them too: they only count in a small world)
local CANNONS = { '03544419135a9935', '26ef7da30b82246d', '35035d21c9b68391', 'c8ccd4986bf70c7c' }
local LAUNCH_KIND = 'e93e9835bce95d4a'    -- only in the destroyer's world of the hellpod launch

if chef.has and chef.has('own_log') then chef.own_log('ImpatientDiver') end
local T0 = clock()
local function log(f, ...) chef.log('%7.2f %s', clock() - T0, fmt(f, ...)) end
local function say(text) if chef.notify then chef.notify(text, 2, 255, 220, 90) end end

-- an engine call's first use is logged first, so a crash in it names it
local first_use = {}
local function first(name)
  if not first_use[name] then
    first_use[name] = true
    log('first call: %s', name)
  end
end

-- ------------------------------------------------------------------ the F9 menu: a row per scene
local OFF, FAST_MODE, INSTANT = 1, 2, 3
local MODE_NAMES = { 'Off', 'Fast', 'Instant' }
local DEFAULT_MODE = INSTANT
local ROWS = {
  { scene = 'log-in intro', id = 'login_intro', label = 'Log-in ship intro',
    hint = 'The camera flying into the ship and the walk to the bridge after you log in.' },
  { scene = 'cryo pod', id = 'cryo_pod', label = 'Cryo pod transition',
    hint = 'Your cryo pod rolling in and your Helldiver stepping out when you arrive on a ship.' },
  { scene = 'FTL', id = 'ftl', label = 'FTL transition',
    hint = 'The FTL jump, and the ship shots when you join or leave a lobby. Loading still takes its time.' },
  { scene = 'hellpod entry', id = 'hellpod_entry', label = 'Hellpod to Loadout',
    hint = 'Climbing into the hellpod and the camera moving to the drop location map.' },
  { scene = 'drop zoom', id = 'drop_zoom', label = 'Drop Location Zoom',
    hint = 'The zoom after you pick a drop point. In a squad, only the host can speed it up.' },
}
local ROW_OF = {}
local HOW = ' Fast: 8x speed. Instant: at once.'
local menu = chef.has and chef.has('menu') and chef.option and chef.get
if menu then chef.title(TITLE) end
for _, row in ipairs(ROWS) do
  ROW_OF[row.scene] = row
  if menu then
    chef.option(row.id, { type = 'choice', label = row.label, hint = row.hint .. HOW,
                          choices = { 'Off', 'Fast (x8)', 'Instant' }, default = DEFAULT_MODE })
    if chef.on_change then
      chef.on_change(row.id, function(v) log('OPTION %s: %s', row.label, tostring(MODE_NAMES[v] or v)) end)
    end
  end
end
ROW_OF['lobby change'] = ROW_OF.FTL   -- the same row: the shots of the same scene family

local function mode_of(name)
  local v = menu and chef.get(ROW_OF[name].id)
  return (v == OFF or v == FAST_MODE or v == INSTANT) and v or DEFAULT_MODE
end

-- ------------------------------------------------------------------ worlds
-- worlds print alike, so each gets a number found by ==
local worlds, next_world = {}, 1
local main_e = nil           -- the main world's entry
local function entry(w)
  for _, e in ipairs(worlds) do
    if e.world == w then return e end
  end
  local e = { world = w, n = next_world, count = -1, kinds = {}, cams = {}, cam_seq = 0, cannons = false }
  next_world = next_world + 1
  worlds[#worlds + 1] = e
  log('WORLD %d new, %.2f s after launch', e.n, clock())
  return e
end

local function listed(e)
  for _, x in ipairs(worlds) do
    if x == e then return true end
  end
  return false
end

local function kind_of(u)
  local text = tostring(u)
  return text:match('#ID%[(%x+)%]') or text
end

-- a world's kinds counted: what it holds of the scenes' markers (a line when a small world's change)
local function take_kinds(e, counts)
  e.kinds = counts
  e.diver = counts[HELLDIVER] ~= nil
  local had = e.cannons
  e.cannons = false
  for _, k in ipairs(CANNONS) do
    if counts[k] then e.cannons = true end
  end
  if e.cannons and not had then e.cannons_at = clock() end
  if e.count > SMALL then return end
  local shows = {}
  if e.cannons then shows[#shows + 1] = 'cannons' end
  if counts[LAUNCH_KIND] then shows[#shows + 1] = 'the launch kind' end
  if counts[MAP_KIND] then shows[#shows + 1] = 'the map floor' end
  if e.diver then shows[#shows + 1] = 'a Helldiver' end
  local text = table.concat(shows, ', ')
  if text ~= (e.shows or '') then
    e.shows = text
    log('WORLD %d (%d units) %s', e.n, e.count, text == '' and 'shows no marker now' or 'shows ' .. text)
  end
end

-- one record per camera unit followed (its field of view, what was logged last, and when); kept while its unit is
-- still listed
local function records(e, units)
  local by = {}
  for _, r in ipairs(e.cams) do by[r.unit] = r end
  local out = {}
  for i, u in ipairs(units) do
    local r = by[u]
    if not r then
      e.cam_seq = e.cam_seq + 1
      r = { unit = u, label = e.n .. '.' .. e.cam_seq }
    end
    out[i] = r
  end
  e.cams = out
end

local function add_camera(u, kind, list)
  if kind == CAMERA_KIND and Unit.alive(u) then
    local n = Unit.num_cameras(u)
    if type(n) == 'number' and n > 0 then list[#list + 1] = u end
  end
end

-- a small world, counted again whenever its unit count changes (its cameras listed too)
local function recount(e)
  local counts, cams = {}, {}
  for _, u in pairs(World.units(e.world)) do
    local kind = kind_of(u)
    counts[kind] = (counts[kind] or 0) + 1
    add_camera(u, kind, cams)
  end
  e.small_cams = cams
  take_kinds(e, counts)
end

local next_scan, last_scan = 0, -1
local ship_seen = false
-- the main world's changes, logged; while a mission or a lobby loads it swaps between two worlds every frame or so:
-- those swaps are counted and logged once it settles
local swaps = { before = nil, at = -1, n = 0 }

-- a ship loaded again since `t` and still there (a lobby change reloads it under the destroyer's outside shot)
local function ship_reloaded_since(t)
  for _, e in ipairs(worlds) do
    if t and e.reloaded_at and e.reloaded_at >= t and e.count > SHIP then return true end
  end
  return false
end

-- a ship emptied since `t` (the old one, as a lobby change's outside shot begins)
local function ship_emptied_since(t)
  for _, e in ipairs(worlds) do
    if t and e.emptied_at and e.emptied_at >= t - EMPTIED_EARLY then return true end
  end
  return false
end

local function watch_worlds(now)
  local main = Application.main_world()
  local seen, me = {}, nil
  for _, w in pairs(Application.worlds()) do
    local e = entry(w)
    seen[e] = true
    if w == main then me = e end
    local n = World.num_units(w)
    if n ~= e.count then
      -- a ship loaded (again, once one was seen: a lobby change, or the return from a mission), or emptied
      if n > SHIP and e.count <= SHIP then
        e.loaded_at = now
        if ship_seen then e.reloaded_at = now end
      elseif n <= SHIP and e.count > SHIP then
        e.emptied_at = now
      end
      e.count = n
      if n <= SMALL then recount(e) end
    end
  end
  for i = #worlds, 1, -1 do
    if not seen[worlds[i]] then
      log('WORLD %d gone', worlds[i].n)
      table.remove(worlds, i)
    end
  end
  if me ~= main_e then
    local back = me ~= nil and me == swaps.before and now - swaps.at < 1   -- back to the one before, within a second
    swaps.before, swaps.at = main_e, now
    main_e = me
    if back then swaps.n = swaps.n + 1
    else
      log('MAIN world %s (%s units)%s', me and me.n or '-', me and me.count or '-',
        swaps.n > 0 and fmt(', after %d swaps', swaps.n) or '')
      swaps.n = 0
    end
    -- its cameras found at once (not on every frame while a mission loads: the main world swaps back and forth then),
    -- and always for the ship's first load: the walk to the bridge is told by its camera, and may be short
    if now - last_scan >= SCAN_AGAIN or not ship_seen then next_scan = 0 end
  elseif swaps.n > 0 and now - swaps.at >= 1 then
    log('MAIN world %s (%s units), after %d swaps', me and me.n or '-', me and me.count or '-', swaps.n)
    swaps.n = 0
  end
end

-- the big worlds' kinds, and the main world's cameras
local function scan()
  local t0 = clock()
  last_scan = t0
  for _, e in ipairs(worlds) do
    if e.count > SMALL and e.count <= SCAN_MOST then
      local main = e == main_e
      local counts, cams = {}, {}
      for _, u in pairs(World.units(e.world)) do
        local kind = kind_of(u)
        counts[kind] = (counts[kind] or 0) + 1
        if main then add_camera(u, kind, cams) end
      end
      take_kinds(e, counts)
      if main then records(e, cams) end
    end
  end
  local ms = (clock() - t0) * 1000
  if ms > SCAN_SLOW then log('scan took %.1f ms', ms) end
end

-- ------------------------------------------------------------------ the main camera
-- the main world's first camera (the player's, and the cutscenes'; the only one that moves): its field of view, read
-- every frame
local function watch_cam()
  local r = main_e and main_e.cams[1]
  if not r then return end
  if not Unit.alive(r.unit) then
    r.dead = true
    return
  end
  local c = Unit.camera(r.unit, 1)
  if not c then return end
  r.fov = Camera.vertical_fov(c)
end

-- the ship's first camera, when the ship is the main world
local function ship_cam()
  local r = main_e and main_e.count > SHIP and main_e.cams[1]
  if r and not r.dead and r.fov ~= nil then return r end
end

-- ------------------------------------------------------------------ the Helldiver
-- Our Helldiver (only its posture counts: never another player's): the only one while solo; the one whose game object
-- this game owns, if the session can say (so far it never could: no unit synchronizer, it seems); after joining
-- another's session, the only one in the cryo pod; else the one the camera follows (found while the player walks).
-- Kept once known while its unit lives and its world still holds the ship, even while another world is the main one
-- (as a client, the FTL's outside world can be); let go in a mission.
-- (`last`: the last posture read for ours, kept after ours is let go, until a mission starts)
local diver = { unit = nil, world = nil, said = nil, next = 0, posture = nil, now = nil, all = {}, last = nil }
local ours = { unit = nil, e = nil, how = nil }

local function forget_ours(why)
  if not ours.unit then return end
  log('HELLDIVER ours gone (%s)', why)
  ours.unit, ours.e, ours.how = nil, nil, nil
end
local joined_at = nil        -- when this game joined another's session (it was host, now isn't)
local has_sm = {}            -- per unit: it has an animation state machine (asked once a world)
local follow = { next = 0, cam = nil, last = {}, score = {} }

local function other_players()
  local n = chef.players and chef.players()
  return type(n) == 'number' and n > 1
end

local function dist(ax, ay, az, bx, by, bz)
  local dx, dy, dz = ax - bx, ay - by, az - bz
  return math.sqrt(dx * dx + dy * dy + dz * dz)
end

local function position(u)
  if chef.unit_position then return chef.unit_position(u) end
  if not Unit.alive(u) then return nil end
  return Vector3.to_elements(Unit.world_position(u, 1))
end

-- a unit's posture state, or nil (Unit.animation_get_state answers one state per layer, more than chef.call passes
-- on, so it's called straight, and only after Unit.alive and Unit.has_animation_state_machine)
local function posture_of(u)
  if not Unit.alive(u) then return nil end
  if has_sm[u] == nil then
    first('Unit.has_animation_state_machine')
    has_sm[u] = Unit.has_animation_state_machine(u) == true
    if not has_sm[u] then log('HELLDIVER %s has no animation state machine', tostring(u)) end
  end
  if not has_sm[u] then return nil end
  first('Unit.animation_get_state')
  return (select(POSTURE, Unit.animation_get_state(u)))
end

-- the session's answer: the one avatar whose game object this game owns, or nil and why not
local function owned_one(all)
  local session = chef.call('Network.game_session')
  if not session then return nil, 'no game session' end
  local me = chef.call('Network.peer_id')
  if me == nil then return nil, 'no peer id' end
  local sync = chef.call('GameSession.unit_synchronizer', session)
  if not sync then return nil, 'no unit synchronizer' end
  first('UnitSynchronizer.unit_to_game_object_id')
  local found, mine, owners = nil, 0, {}
  for i, u in ipairs(all) do
    local id = chef.call('UnitSynchronizer.unit_to_game_object_id', sync, u)
    local owner = type(id) == 'number' and chef.call('GameSession.game_object_owner', session, id) or nil
    owners[i] = tostring(id) .. ':' .. (owner == nil and '?' or owner == me and 'me' or tostring(owner))
    if owner ~= nil and owner == me then
      mine = mine + 1
      found = found or u
    end
  end
  local list = 'game object:owner ' .. table.concat(owners, ' ')
  if mine == 1 then return found, 'owned (' .. list .. ')' end
  return nil, (mine > 1 and 'several owned' or 'none owned') .. ' (' .. list .. ')'
end

-- just after joining another's session: the only Helldiver in the cryo pod is ours (the joiner's pod plays first)
local function joiner(now, all)
  if not joined_at or now - joined_at > JOIN_SECONDS then return nil end
  local hit = nil
  for _, u in ipairs(all) do
    local p = posture_of(u)
    if p == CRYO_IN or p == CRYO_OUT then
      if hit then return nil end
      hit = u
    end
  end
  return hit
end

-- The camera follows our Helldiver: while it moves (the player walks), ours keeps its offset to it and the others
-- don't. Ours is the only one that kept it in FOLLOW_SAMPLES moving samples in a row (a still camera tells nothing).
local function by_camera(now, all)
  if now < follow.next then return nil end
  follow.next = now + FOLLOW_SECONDS
  local r = main_e and main_e.cams[1]
  if not r or r.dead or not Unit.alive(r.unit) then return nil end
  local c = Unit.camera(r.unit, 1)
  if not c then return nil end
  local cx, cy, cz = Vector3.to_elements(Camera.world_position(c))
  local prev = follow.cam
  follow.cam = { cx, cy, cz }
  local moved = prev and dist(cx, cy, cz, prev[1], prev[2], prev[3]) or 0
  local last, keeper, keepers = {}, nil, 0
  for _, u in ipairs(all) do
    local x, y, z = position(u)
    if x then
      local o = { cx - x, cy - y, cz - z }
      last[u] = o
      local p = follow.last[u]
      if moved >= FOLLOW_MOVE and p and dist(o[1], o[2], o[3], p[1], p[2], p[3]) <= FOLLOW_KEEP * moved
          and dist(o[1], o[2], o[3], 0, 0, 0) <= FOLLOW_NEAR then
        keepers, keeper = keepers + 1, u
      end
    end
  end
  follow.last = last
  if moved < FOLLOW_MOVE then return nil end
  if keepers ~= 1 then
    follow.score = {}
    return nil
  end
  local n = (follow.score[keeper] or 0) + 1
  follow.score = { [keeper] = n }
  if n < FOLLOW_SAMPLES then return nil end
  local o = last[keeper]
  return keeper, fmt('the one the camera follows (%.1f m off, %d moving samples)', dist(o[1], o[2], o[3], 0, 0, 0), n)
end

local function look_up_diver(now)
  diver.next = now + DIVER_SECONDS
  local w = main_e and main_e.world
  if w ~= diver.world then has_sm, follow.cam, follow.last, follow.score = {}, nil, {}, {} end
  local all = {}
  if w then
    first('World.units_by_resource')
    local units = World.units_by_resource(w, IdString64.from_hex(HELLDIVER))
    if type(units) == 'table' then
      for _, u in pairs(units) do
        if Unit.alive(u) then all[#all + 1] = u end
      end
    end
  end
  diver.all = all
  if ours.unit and not Unit.alive(ours.unit) then forget_ours('its unit')
  elseif ours.unit and (not listed(ours.e) or ours.e.count <= SHIP) then forget_ours('its world no longer holds the ship')
  end
  local found, how = ours.unit, ours.how
  if found and ours.e ~= main_e then how = how .. ', kept in world ' .. ours.e.n end
  if not found then
    how = 'none'
    local ship = main_e and main_e.count > SHIP   -- ours is taken on the ship only
    if ship and #all == 1 and not other_players() then found, how = all[1], 'the only one, solo'
    elseif ship and #all > 0 then
      local why
      found, why = owned_one(all)
      if found then how = why
      else
        found = joiner(now, all)
        how = found and 'the only one in the cryo pod, just joined'
          or 'not known yet (' .. why .. '; the camera finds it while the player walks)'
      end
    end
    if found then ours.unit, ours.e, ours.how = found, main_e, how end
  end
  local said = how .. ' ' .. #all
  if found ~= diver.unit or said ~= diver.said then   -- (not for the main world alone: it swaps as a mission loads)
    if found ~= diver.unit then diver.posture = nil end
    log('HELLDIVER %s (%d in main world %s)', how, #all, main_e and main_e.n or '-')
  end
  diver.unit, diver.said, diver.world = found, said, w
end

-- ours not known with several Helldivers aboard: the camera, sampled while the ship is the main world
local function find_ours(now)
  if ours.unit or #diver.all < 2 or not (main_e and main_e.count > SHIP) then return end
  local u, how = by_camera(now, diver.all)
  if u then
    ours.unit, ours.e, ours.how = u, main_e, how
    diver.next = 0             -- taken at once
  end
end

-- our Helldiver's posture, read every frame; with others aboard, theirs too (logged, numbered as first seen). Ours not
-- known, a posture every player's Helldiver is in is ours too (joining a lobby whose players are in their hellpods,
-- every Helldiver plays the stepping-in clip at once).
local others = { n = 0, label = {}, posture = {}, shared = nil }
local function watch_anim()
  local u = diver.unit
  if u then
    local p = posture_of(u)
    diver.now = p
    if p ~= diver.posture then
      log('ANIM L%d %s>%s', POSTURE, tostring(diver.posture), tostring(p))
      diver.posture = p
    end
  end
  if #diver.all < 2 then return end
  local shared, n = nil, chef.players and chef.players()
  for i, o in ipairs(diver.all) do
    if o ~= u then
      local p = posture_of(o)
      if p ~= others.posture[o] then
        if not others.label[o] then others.n = others.n + 1; others.label[o] = others.n end
        log('ANIM other %d L%d %s>%s', others.label[o], POSTURE, tostring(others.posture[o]), tostring(p))
        others.posture[o] = p
      end
      if i == 1 then shared = p elseif p ~= shared then shared = nil end
    end
  end
  if u or #diver.all ~= n then shared = nil end
  if shared ~= others.shared then
    others.shared = shared
    if shared then log('ANIM all %d Helldivers L%d %s', n, POSTURE, tostring(shared)) end
  end
  if shared then diver.now = shared end
end

-- the Helldiver's posture state this frame (nil when it wasn't read this frame)
local function posture() return diver.now end

-- every player's Helldiver is aboard and in its hellpod (ours too)
local function all_in_pods()
  local n = chef.players and chef.players()
  if posture() ~= POD_IN or #diver.all ~= n then return false end
  for _, o in ipairs(diver.all) do
    if o ~= diver.unit and others.posture[o] ~= POD_IN then return false end
  end
  return true
end

-- where the main world's first camera is
local function main_cam_at()
  local r = main_e and main_e.cams[1]
  if not r or r.dead or not Unit.alive(r.unit) then return nil end
  local c = Unit.camera(r.unit, 1)
  if not c then return nil end
  return Vector3.to_elements(Camera.world_position(c))
end

-- the loadout screen's world (small, with its floor of planes); its `diver` is up while the loadout page shows (the
-- drop location map and the loadout screen's weapon and grenade pages show none)
local function loadout_world()
  for _, e in ipairs(worlds) do
    if e ~= main_e and e.count <= SMALL and e.kinds[MAP_KIND] then return e end
  end
end

-- While ours is in the hellpod on the ship, the clicks. With other players aboard, a click picks the drop point and the
-- zoom waits for every player's Helldiver in its hellpod (the camera moves into the loadout view 1 s after the last one
-- is in); `picked` holds the click, `zoomed` says the zoom went by, until ours leaves the pod or the camera is back on
-- the map from the loadout view (`map` its spot as the zoom began, `away` once it left it): a new pick then (`again`,
-- alone too; left alone it plays 1.2 s from the click to the camera's move, then 0.9 s).
-- Alone, `page` says the loadout screen has shown (its page's Helldiver) in this stay in the pod: its weapon and
-- grenade pages hide that Helldiver as the map does, so from then on only a pick again counts (`spot`: where the
-- camera was at the last click on the map, for a zoom that went by without being sped up).
local pod = { picked = false, zoomed = false, map = nil, away = false, again = false, page = false, spot = nil }

local function watch_pod(click)
  if posture() ~= POD_IN or not (main_e and main_e.count > SHIP) then
    pod.picked, pod.zoomed, pod.map, pod.away, pod.again = false, false, nil, false, false
    pod.page, pod.spot = false, nil
    return
  end
  if not other_players() then
    local lw = loadout_world()
    if lw and lw.diver and not pod.page then
      pod.page = true
      if not pod.zoomed then pod.zoomed, pod.map = true, pod.map or pod.spot end
      log('drop zoom: the loadout screen is up (a click on its pages is no pick)')
    end
    if click and not pod.page then
      local x, y, z = main_cam_at()
      if x then pod.spot = { x, y, z } end
    end
  end
  if pod.zoomed and pod.map then
    local x, y, z = main_cam_at()
    local d = x and dist(x, y, z, pod.map[1], pod.map[2], pod.map[3])
    if d and d >= VIEW_AWAY then pod.away = true
    elseif d and pod.away and d < MAP_BACK then
      pod.picked, pod.zoomed, pod.away, pod.again = false, false, false, true
      log('drop zoom: the camera is back on the drop location map')
    end
  end
  if click and other_players() then pod.picked = true end
end

-- ------------------------------------------------------------------ speed
local rate, jumping, asked, broken = 1, false, 0, false
local rate_by = nil          -- the mode of the scene that set the rate
local function set_rate(r, why, mode)
  if broken then return end
  first('Application.set_time_step_policy')
  local ok, err = chef.call('Application.set_time_step_policy', 'external_multiplier', r)
  if ok == nil and err then
    broken = true
    log('RATE x%g failed: %s (no more speed changes)', r, tostring(err))
    return
  end
  rate = r
  log('RATE x%g (%s)', r, why)
  -- a notice for Fast only (its x8, and the x1 after it); Instant goes by without one
  if mode == FAST_MODE or (mode == nil and rate_by == FAST_MODE) then say('TIME X' .. r) end
  rate_by = mode
end

-- the clock jumps JUMP seconds in the next frame's step
local function ask_jump()
  if broken then return end
  first('Application.set_time_step_policy (jump)')
  local ok, err = chef.call('Application.set_time_step_policy', 'jump', JUMP)
  if ok == nil and err then
    broken = true
    log('JUMP failed: %s (no more speed changes)', tostring(err))
    return
  end
  asked = JUMP
end

-- ------------------------------------------------------------------ the solo pause
-- A key (F6 by default) holds the game's clock at x0.001 while this game is alone in its session, whatever scene is
-- on; on its 1 FPS choice the engine's whole loop is throttled too (the multiplier only scales game time). Off by
-- default. It ends by itself when the row goes Off, or as soon as another player is in or joining the session.
local PAUSE_ID, PAUSE_OFF, PAUSE_ON, PAUSE_FPS = 'solo_pause', 1, 2, 3
local PAUSE_NAMES = { 'Off', 'On', 'On (1 FPS)' }
local PAUSE_RATE = 0.001
local paused, throttled, throttle_broken = false, false, false
local pause_key = nil
if menu then
  chef.option(PAUSE_ID, { type = 'choice', label = 'Solo Pause',
    hint = 'A key pauses the game while no one else is in your session. 1 FPS also lowers the frame rate while paused.',
    choices = { 'Off', 'On', 'On (1 FPS)' }, default = PAUSE_OFF })
  if chef.on_change then
    chef.on_change(PAUSE_ID, function(v) log('OPTION Solo Pause: %s', tostring(PAUSE_NAMES[v] or v)) end)
  end
  if chef.has('bind') and chef.bind then pause_key = chef.bind('solo_pause_key', 'f6', 'Solo Pause key') end
end

local function pause_mode()
  local v = menu and chef.get(PAUSE_ID)
  return (v == PAUSE_ON or v == PAUSE_FPS) and v or PAUSE_OFF
end

local function alone()
  local joining = chef.joining and chef.joining()
  return not other_players() and (type(joining) ~= 'number' or joining == 0)
end

-- the player's frame rate limit from the game's settings, read as the pause ends (it may have changed), or nil: none is
-- set, or it can't be read. 'no_throttle' alone leaves the game uncapped, whatever the setting says.
local function game_frame_limit()
  first('Application.user_setting')
  local enabled = chef.call('Application.user_setting', 'framerate_limit_enabled')
  local limit = chef.call('Application.user_setting', 'framerate_limit')
  if enabled ~= false and type(limit) == 'number' and limit > 0 then return limit end
  return nil
end

local function set_throttle(on)
  if throttle_broken or throttled == on then return end
  first('Application.set_time_step_policy (throttle)')
  local ok, err
  local limit = not on and game_frame_limit() or nil
  if on then ok, err = chef.call('Application.set_time_step_policy', 'throttle', 1)
  elseif limit then ok, err = chef.call('Application.set_time_step_policy', 'throttle', limit)
  else ok, err = chef.call('Application.set_time_step_policy', 'no_throttle') end
  if ok == nil and err then
    throttle_broken = true
    log('FRAME THROTTLE failed: %s (no more throttling)', tostring(err))
    return
  end
  throttled = on
  log('FRAME THROTTLE %s', on and '1 FPS'
    or limit and fmt("back to the game's limit, %g FPS", limit) or 'off (no limit set)')
end

local function set_paused(on, why)
  paused = on
  log('SOLO PAUSE %s (%s)', on and 'on' or 'off', why)
  say(on and 'PAUSED' or 'RESUMED')
end

local function check_pause()
  local mode = pause_mode()
  local press = pause_key and pause_key.pressed and pause_key.pressed() == true
  if paused then
    if mode == PAUSE_OFF then set_paused(false, 'the row is Off')
    elseif broken then set_paused(false, 'speed changes failed')
    elseif not alone() then set_paused(false, 'another player is in the session')
    elseif press then set_paused(false, 'the key')
    end
  elseif press and mode ~= PAUSE_OFF and not broken then
    if alone() then set_paused(true, PAUSE_NAMES[mode])
    else say('SOLO PAUSE: OTHER PLAYERS IN SESSION') end
  end
  set_throttle(paused and mode == PAUSE_FPS)
end

-- { name, world (the destroyer's entry), real (when it started), t (game s since it started, jumps in), paced (the
--   same, paced), jumped and jumps (the jumps' seconds and count), left (the part's jump seconds left), from (t when
--   the part began, for the cap), steps (its first steps' lengths), capped, spent (the part's jumps are over), walk
--   (paced s since the ship loaded: the walk to the bridge, the log-in intro's second part), narrowed (its camera
--   was narrow), walked (our Helldiver played its walk clip) and control (t when it could move) for the log-in intro,
--   out_frames (frames of the walk-out) for the cryo pod, in_pod (the clip is over) for the hellpod entry, loaded (the
--   next ship is there) for a lobby change, by_cam (it ends by the camera: other players aboard, or a pick again), cam
--   (where the main camera was as it began) and page (t when the loadout page opened, or the camera moved) for the
--   drop zoom }
local scene = nil
local block_until = -1       -- the return from a mission: no outside shot sped up until then
local mission_end, return_shot = nil, false   -- (return_shot: its outside shot was seen)
local note_said = nil
local session_said = nil     -- host or client, and the players (a SESSION line when it changes)

-- the small world holding the destroyer's cannons, if one does (the smallest, should a world still loading hold some)
local function destroyer()
  local best = nil
  for _, e in ipairs(worlds) do
    if e.cannons and e.count <= SMALL and (not best or e.count < best.count) then best = e end
  end
  return best
end

-- a small world besides the main one shows a Helldiver: the loadout screen (the player is in the hellpod)
local function loadout()
  for _, e in ipairs(worlds) do
    if e ~= main_e and e.diver and e.count <= SMALL then return true end
  end
  return false
end

-- what a scene going on needs to know this frame
local function progress(dt, paced, landed, now_real)
  if not scene then return end
  scene.t = scene.t + dt
  scene.paced = scene.paced + paced
  if landed > 0 then
    scene.jumped, scene.jumps, scene.left = scene.jumped + landed, scene.jumps + 1, scene.left - landed
  end
  if #scene.steps < 4 then scene.steps[#scene.steps + 1] = fmt('%.3f', dt) end
  if scene.name == 'log-in intro' then
    local cam = ship_cam()
    if cam then
      if not scene.walk then
        -- the walk to the bridge: its own jumps and cap (the outside shot may have spent its own waiting for the ship)
        log('SCENE log-in intro: the ship is there %.2f s real after it began (%.1f s of game time, %.1f s jumped); '
          .. 'camera fov %.3f', now_real - scene.real, scene.t, scene.jumped, cam.fov)
        scene.walk, scene.left, scene.from, scene.spent, scene.capped = 0, JUMP_MOST.walk, scene.t, nil, nil
      end
      scene.walk = scene.walk + paced
      if cam.fov <= WIDE_FOV and not scene.narrowed then
        scene.narrowed = true
        log('SCENE log-in intro: the camera narrowed (fov %.3f), %.1f s of game time into the walk', cam.fov,
          scene.t - scene.from)
      end
    end
    -- our Helldiver's walk clip, then normal play: the player can move
    local p = posture()
    if p == WALK_CLIP then scene.walked = true
    elseif p == PLAY and scene.walked and not scene.control then
      scene.control = scene.t
      log('SCENE log-in intro: the Helldiver can move, %.2f s real after it began; camera fov %s',
        now_real - scene.real, cam and fmt('%.3f', cam.fov) or '-')
    end
  elseif scene.name == 'cryo pod' and posture() == CRYO_OUT then
    scene.out_frames = (scene.out_frames or 0) + 1
    if scene.out_frames == 1 then
      -- the walk-out: its own jumps and cap (the wait in the pod may have spent its own)
      log('cryo pod: the walk-out after %.1f s of game time (%.1f s jumped), %.2f s real; %d frames at x%d first',
        scene.t, scene.jumped, now_real - scene.real, PLACE_FRAMES, FAST)
      scene.left, scene.from, scene.spent, scene.capped = JUMP_MOST['walk-out'], scene.t, nil, nil
    end
  elseif scene.name == 'hellpod entry' and posture() == POD_IN and not scene.in_pod then
    -- the camera's close-up on the pod after the clip: its own jumps
    scene.in_pod = true
    local cam = ship_cam()
    log('hellpod entry: in the hellpod after %.1f s of game time (%.1f s jumped), %.2f s real; camera fov %s',
      scene.t, scene.jumped, now_real - scene.real, cam and fmt('%.3f', cam.fov) or '-')
    scene.left, scene.from, scene.spent, scene.capped = JUMP_MOST['pod view'], scene.t, nil, nil
  elseif scene.name == 'lobby change' and not scene.loaded and listed(scene.world)
      and ship_reloaded_since(scene.world.cannons_at) then
    -- the next ship is there: what is left has jumps of its own (the wait for it may have spent the first)
    scene.loaded = true
    log('lobby change: the next ship is there %.2f s real after it began (%.1f s of game time, %.1f s jumped)',
      now_real - scene.real, scene.t, scene.jumped)
    scene.left, scene.from, scene.spent, scene.capped = JUMP_MOST['lobby change'], scene.t, nil, nil
  elseif scene.name == 'drop zoom' and not scene.page then
    if scene.by_cam then
      -- with others, or a pick again: the camera starts its move into the loadout view
      local x, y, z = main_cam_at()
      if x and scene.cam and dist(x, y, z, scene.cam[1], scene.cam[2], scene.cam[3]) >= CAM_MOVE then
        scene.page, pod.zoomed, pod.map, pod.again = scene.t, true, scene.cam, false
        log('drop zoom: the camera moves into the loadout view %.2f s of game time after every Helldiver was in its '
          .. 'hellpod (%.2f s paced)', scene.t, scene.paced)
      end
    else
      -- (watch_pod keeps the map's spot for a pick again, and that the loadout screen has shown)
      local lw = loadout_world()
      if lw and lw.diver then
        scene.page = scene.t
        log('drop zoom: the loadout page opened %.2f s of game time after the click (%.2f s paced)', scene.t,
          scene.paced)
      end
    end
  end
end

-- The scene to speed up now (and the destroyer's world when it starts one), or nil and why not.
local function pick(mission, now, click)
  if mission then return nil, 'a mission' end
  if scene and scene.name == 'log-in intro' then
    -- our Helldiver back in normal play after its walk clip: the player has it, whatever the camera does
    if scene.control and scene.t - scene.control >= WALK_SETTLE then return nil, 'the Helldiver can move' end
    if scene.walk and scene.t - scene.from >= WALK_CAP then return nil, 'the walk to the bridge reached its cap' end
    local cam = ship_cam()
    if not cam then         -- still outside: the destroyer's world keeps it going
      if not listed(scene.world) or scene.world.count <= 1 then return nil, "the destroyer's world emptied" end
      return scene.name
    end
    -- the walk to the bridge: its camera narrows, then widens again as the player gets control (it is wide for a
    -- frame or so as the ship loads)
    if not scene.narrowed then
      if (scene.walk or 0) > WALK_WAIT then return nil, 'no walk to the bridge' end
    elseif cam.fov > WIDE_FOV then return nil, 'the camera went wide' end
    return scene.name
  end
  if scene and scene.name == 'cryo pod' then
    if posture() == CRYO_IN or posture() == CRYO_OUT then return scene.name end
    return nil, 'the Helldiver is out of the cryo pod'
  end
  if scene and scene.name == 'hellpod entry' then
    if posture() == POD_ENTER then return scene.name end
    -- in the pod, a client's camera holds its close-up a while before it pulls out to the drop location map
    local cam = ship_cam()
    if posture() == POD_IN and cam and cam.fov < MAP_FOV and scene.t - scene.from < POD_VIEW then
      return scene.name
    end
    return nil, 'the Helldiver is in the hellpod'
  end
  if scene and scene.name == 'drop zoom' then
    if scene.page then
      if scene.t - scene.page < ZOOM_MOVE then return scene.name end
      return nil, 'the loadout view is up'
    end
    if scene.paced < ZOOM_RAMP then return scene.name end
    pod.picked = false         -- (with others: that click picked nothing; the next one may)
    return nil, 'no loadout page after the click'
  end
  local ship = main_e ~= nil and main_e.count > SHIP
  if ship and posture() == POD_ENTER then return 'hellpod entry' end
  if ship and (posture() == CRYO_IN or posture() == CRYO_OUT) then return 'cryo pod' end
  if ship and click and posture() == POD_IN and not other_players() then
    local lw = loadout_world()
    -- the drop location map: the loadout screen's world before its page has shown (watch_pod notes it the frame its
    -- Helldiver shows)
    if lw and not pod.page then return 'drop zoom' end
    if pod.again then return 'drop zoom' end   -- (the loadout page's Helldiver stays as the camera goes back)
  end
  -- With other players the zoom waits for every player's Helldiver in its hellpod, after a click (the host's clicks
  -- would jump the clock while it waits). Only the host's: a client's zoom follows the host's, synced.
  if ship and pod.picked and not pod.zoomed and chef.is_host and chef.is_host() == true and all_in_pods() then
    return 'drop zoom'
  end
  local d = destroyer()
  if not d then return nil, scene and "the destroyer's cannons went" end
  if d.kinds[LAUNCH_KIND] then return nil, 'the hellpod launch' end
  if not ship_seen then
    if d == main_e then return 'log-in intro', nil, d end
    return nil, 'an outside shot with no ship loaded'
  end
  if loadout() then return nil, 'the hellpod launch (the loadout screen is up)' end
  if now < block_until then return nil, 'after a mission' end
  -- The FTL's outside world is big as it starts, and may be the main one (as a client); an FTL goes on
  -- while its world holds the cannons (joining a lobby elsewhere, it shrinks for the arrival). A small one
  -- is a lobby change (joining or leaving) as it begins over our loaded ship, the main world (joining from the galactic
  -- map), as our old ship empties (the same frame, or 0.3 s after) unless ours was last
  -- seen in its hellpod (the launch: its ship empties a second before its cannons), and once a ship loaded under it
  -- (the main world may swap between the two meanwhile); else the launch.
  if d.count >= FTL_UNITS or (scene and scene.name == 'FTL' and scene.world == d) then return 'FTL', nil, d end
  if ship_reloaded_since(d.cannons_at) then return 'lobby change', nil, d end
  if main_e and main_e.count > SHIP and main_e.loaded_at and d.cannons_at and main_e.loaded_at < d.cannons_at then
    return 'lobby change', nil, d
  end
  if ship_emptied_since(d.cannons_at) and diver.last ~= POD_IN then return 'lobby change', nil, d end
  return nil, 'a small outside shot (the launch?)'
end

local function apply(dt, now, mission, click, paced, landed)
  progress(dt, paced, landed, now)
  local name, note, d = pick(mission, now, click)
  if name and mode_of(name) == OFF then name, note, d = nil, ROW_OF[name].label .. ' is Off', nil end
  local ended = false
  if scene and name ~= scene.name then
    log('SCENE %s over (%s): %.1f s of game time%s, %.1f s real%s; first steps %s', scene.name, note or '?', scene.t,
      scene.jumps > 0 and fmt(' (%.1f s of it in %d jumps)', scene.jumped, scene.jumps) or '', now - scene.real,
      scene.capped and ', capped' or '', table.concat(scene.steps, ' '))
    scene, ended = nil, true
  end
  if name and not scene then
    scene = { name = name, world = d, real = now, t = 0, paced = 0, jumped = 0, jumps = 0, left = JUMP_MOST[name],
              from = 0, steps = {} }
    if name == 'drop zoom' then
      local x, y, z = main_cam_at()
      scene.by_cam, scene.cam = other_players() or pod.again, x and { x, y, z } or nil
    end
    log('SCENE %s starts (%s; %s; %s)', name, MODE_NAMES[mode_of(name)],
      d and fmt('destroyer world %d, %d units', d.n, d.count) or 'posture ' .. tostring(posture()), session_said or '?')
  end
  if scene and not scene.capped and scene.t - scene.from >= CAP then
    scene.capped = true
    log('SCENE %s: %d s of game time, x1 until it ends', scene.name, CAP)
  end
  if note ~= note_said then
    note_said = note
    if note and not ended then log('x1: %s', note) end
  end
  local mode = scene and not scene.capped and mode_of(scene.name) or nil
  -- (the cryo pod's walk-out holds its first frames at x8)
  local hold = scene and scene.out_frames and scene.out_frames <= PLACE_FRAMES
  local jump = not paused and mode == INSTANT and scene.left > 0 and not hold
  if not paused and mode == INSTANT and scene.left <= 0 and not scene.spent then
    scene.spent = true
    log('SCENE %s: %.1f s jumped, x%d for the rest', scene.name, scene.jumped, FAST)
  end
  local want = paused and PAUSE_RATE or (mode and (jump and 1 or FAST) or 1)
  local why = paused and 'solo pause' or scene and scene.name or note or 'no scene'
  if want ~= rate then set_rate(want, why, paused and 'solo pause' or mode) end
  if jump ~= jumping then
    jumping = jump
    log('JUMPS %s (%s)', jump and fmt('of %d s a frame', JUMP) or 'off', why)
  end
  if jump then ask_jump() end
end

-- ------------------------------------------------------------------ frame
local next_session, was_host = 0, nil
local was_mission, mouse_was = false, false

-- A mission replaces the ship's units, and any engine call on a unit from before it (Unit.alive too) can end the game:
-- no unit handle is kept over a mission, and the first frame after it scans again.
local function drop_handles()
  for _, e in ipairs(worlds) do e.cams, e.small_cams = {}, nil end
  diver.unit, diver.all, diver.world, diver.said, diver.posture = nil, {}, nil, nil, nil
  others.label, others.posture, others.shared = {}, {}, nil
  has_sm, follow.cam, follow.last, follow.score = {}, nil, {}, {}
  next_scan = 0
end

function M.update(dt)
  local now = clock()
  dt = type(dt) == 'number' and dt or 0
  check_pause()
  -- the jump asked last frame is in this step; the rest is paced (the step x8 would have made; paused, no more than
  -- the game's own clock, so a scene's wait doesn't run out during the pause)
  local landed = (asked > 0 and dt >= asked) and asked or 0
  asked = 0
  local paced = (paused or rate == PAUSE_RATE) and dt or min((dt - landed) * FAST / rate, STEP_MOST)
  diver.now = nil
  local down = chef.mouse_down and chef.mouse_down('left') == true
  local click = down and not mouse_was
  mouse_was = down

  local mission = chef.in_mission() == true
  if mission ~= was_mission then
    was_mission = mission
    log('in mission: %s', tostring(mission))
    if mission then
      forget_ours('a mission')
      drop_handles()
      diver.last = nil
    else
      block_until, mission_end, return_shot = now + AFTER_MISSION, now, false
    end
  end
  if now >= next_session then
    next_session = now + SESSION_SECONDS
    local host = chef.is_host and chef.is_host()
    if host == false and was_host == true then
      joined_at = now
      log('SESSION joined another\'s')
    end
    was_host = host
    local s = fmt('%s, %s players', host == true and 'host' or host == false and 'not host' or '?',
      tostring(chef.players and chef.players()))
    if s ~= session_said then
      session_said = s
      log('SESSION %s', s)
    end
  end

  if not mission then
    watch_worlds(now)
    if not ship_seen and main_e and main_e.count > SHIP then
      ship_seen = true
      log('ship loaded (world %d, %d units)', main_e.n, main_e.count)
    end
    if now >= next_scan then
      next_scan = now + SCAN_SECONDS
      scan()
    end
    -- the return from a mission is over once its outside shot is (the ship loads again under it, about 50 s after
    -- the mission); a return with none waits for the 90 s
    if now < block_until then
      if destroyer() then return_shot = true
      elseif return_shot and main_e and main_e.count > SHIP and main_e.loaded_at and main_e.loaded_at >= mission_end then
        block_until = -1
        log('the return from the mission is over (%.1f s after it ended)', now - mission_end)
      end
    end
    watch_cam()
    find_ours(now)
    if now >= diver.next or diver.world ~= (main_e and main_e.world) or (ours.e and ours.e.count <= SHIP) then
      look_up_diver(now)
    end
    watch_anim()
    if diver.now ~= nil then diver.last = diver.now end
    watch_pod(click)
  end
  apply(dt, now, mission, click, paced, landed)

end

-- Switched off in the F9 menu, or stopped after errors: the game's clock goes back. With this the loader stops the mod
-- instead of pausing it, and a new copy starts when it's switched on again.
function M.on_stop()
  paused = false
  set_throttle(false)
  if rate ~= 1 then set_rate(1, 'stopped') end
end

function M.shutdown()
  paused = false
  set_throttle(false)
  if rate ~= 1 then set_rate(1, 'shutdown') end
end

local modes = {}
for i, row in ipairs(ROWS) do modes[i] = row.label .. ' ' .. MODE_NAMES[mode_of(row.scene)] end
modes[#modes + 1] = 'Solo Pause ' .. PAUSE_NAMES[pause_mode()]
log('Impatient Diver V%s on Chef Shared Loader %s (api %s), engine build %s %s, %.2f s after launch; %s%s', M.version,
  tostring(chef.loader_version), tostring(chef.api), tostring(Application.build and Application.build()),
  tostring(Application.build_identifier and Application.build_identifier()), clock(), table.concat(modes, ', '),
  menu and '' or ' (no F9 menu: defaults)')

return M
