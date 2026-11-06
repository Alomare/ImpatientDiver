# Impatient Diver: how it works in the game

For other mod authors. Since V9 the mod uses only the engine's Lua API on the game's plain Lua 5.1 (no LuaJIT, no FFI, no memory access), under Chef Shared Loader's sandbox. Numbers are from Steam build 26251122 (engine stingray 46805) unless noted.

The research behind V8 and older (the cutscene manager, scene phases, hellpod seats, drop zoom progress, the presenter manager, game.dll signatures on build 25480438) is in [RESEARCH.md at tag v8](https://github.com/Alomare/ImpatientDiver/blob/v8/RESEARCH.md). None of it applies to how the mod works now, but it explains what the scenes are.

## The clock

- `Application.set_time_step_policy('external_multiplier', n)` scales the engine's step, and game.dll's scene clock follows it. At x8 the world ran at 8.00x (about 0.117 s a step at 69 fps).
- `system_step_range` defaults to 0 to 0.2 s a step, so x8 below 40 fps is clamped.
- `Application.set_time_step_policy('jump', s)` makes the next step `s` longer, past that clamp. One 5 s jump was fine in every scene tried. Scene timers end up to a jump late.
- Loading runs on real time: jumping doesn't shorten it. A cap per scene keeps a wait for loading from eating all the jumps.
- Sounds aren't sped up: they play on at normal speed after a skipped scene.
- The loader's own clock (`chef.time()`) follows game time, so its timers speed up too. Use `os.clock` for real time.

## Telling the scenes apart

There is no Lua API for the current cutscene. These markers come from logs of every scene, as host, client and solo.

### Worlds

Worlds print alike: compare with `==`.

- **The ship:** a main world of more than 1000 units (2200 to 4100), off missions.
- **The Super Destroyer's outside shots:** a small world that holds any of the `content/env_ship/hangar/se_destroyer_supportcannon_*` kinds (`03544419135a9935`, `26ef7da30b82246d`, `35035d21c9b68391`, `c8ccd4986bf70c7c`). The ship's world has them too, so they only count in a small world. Its size tells the shot:

| Shot | Units |
|---|---|
| FTL | 584 to 593 at its start; it can shrink for the arrival, with its cannons kept |
| Joining or leaving a lobby | 11 to 30 |
| Hellpod launch | 25 to 33, with `e93e9835bce95d4a`, which no other shot has |
| Log-in intro | 54 to 63, as the main world, before any ship has loaded |
| Return from a mission | about 41, about 50 s until the ship has loaded under it |

- **The loadout screen:** a small world with its floor of `content/art_shared/meshes/plane_2x2m` (`96af7d6acb949f34`). It gains an `avatar_helldiver` as the loadout page opens, and keeps it when the player goes back to the map. Its weapon and grenade pages drop that Helldiver again (20 units, as on the map), so alone the Helldiver doesn't tell the map from them; there the main camera stays away from its spot on the map.
- As a client, the FTL's world can be the main world for a while. While a mission or a lobby loads, the main world can swap between two worlds every frame.

### The Helldiver's posture

`Unit.animation_get_state` returns one state per layer, more than `chef.call` passes on, so call it directly, after `Unit.alive` and `Unit.has_animation_state_machine`. Layer 14 (0-based states of `content/fac_helldivers/cha_avatar/avatar_helldiver`):

| State | What |
|---|---|
| 0 | The cryo pod's loop |
| 3 | Normal play |
| 6 | The cryo pod's walk-out clip (event `0x23173e19`, its end event leads to 3) |
| 15 | Stepping into the hellpod (event `0xa9b0a3bb` from any state) |
| 17 | The loop inside the hellpod |
| 16 | Leaving the hellpod |
| 18 | The walk to the bridge after logging in (a clip; its end leads to 3) |
| 36 | The default state, as a Helldiver spawns |

State numbers move with the game's state machine: they differ between builds on other layers. FileDiver's `cryo_probe` dumps the machine. Check these after a game update.

### Which Helldiver is ours

Other players' avatars play the same postures on our machine, and in this build the session never answers whose unit is whose (`GameSession.unit_synchronizer` gives nothing). What works:

- The only Helldiver while solo; kept when others come aboard.
- Just after joining another's session: the only one in the cryo pod (the joiner's pod plays first).
- Else the one the camera follows: while the camera moves, ours keeps its offset to it and the others don't.
- Not known yet: a posture every player's Helldiver shares counts (joining a lobby in its hellpods, all step in at once).

Keep it while its unit lives and its world still holds the ship; let it go in a mission.

### The main camera

The main world's first camera is the only one that moves in these scenes.

- Field of view 1.134 in play.
- Narrow (0.262) in the walk to the bridge; wide for a frame or so as the ship first loads. The walk ends when it is wide again.
- In the hellpod the drop map's view is 1.222. A client's camera holds a close-up (0.611) for 2.4 s first; a host's is on the map as the clip ends.
- The move into the loadout view: 0.9 s, about 1.2 m. It is what ends a squad's zoom, and it starts 1.2 s after a pick when everyone is in.

## The scenes

- **Log-in intro:** 3.33 s of timed phases, then a wait for the ship's load, then the walk to the bridge. The player can move once the Helldiver goes from 18 to 3; the camera starts widening about 0.5 s later and takes 1.4 s (jumped a second a frame, it read wide 2 to 7 frames after the 3).
- **Cryo pod:** the pod rolling in and a 1 s wait alone. After joining a lobby, 2.3 to 3.5 s real of loading however much is jumped. Then a 7.5 s walk-out, whose first frames need normal steps: the game places the Helldiver a few frames in.
- **FTL:** runs while its world holds the cannons. Don't end it when the world shrinks: the arrival plays in the shrunk world, and a player sees it twice.
- **Lobby change:** begins over our loaded ship, or as the old ship empties the frame the cannons show (at most 0.3 s after). The next ship loads 0.5 to 2.4 s later, then 3 to 6 jumps end it. The launch looks alike, except that its ship empties a second before its cannons with the Helldiver in the pod.
- **Drop zoom:** alone, a click on the map starts it. With others, the click only picks the point and the zoom waits for every player's Helldiver to be in its pod. A click speeding up the clock before that jumps the game for nothing. A client's zoom follows the host's synced progress, so a client can't shorten it.
- **Not found:** a marker for the wait between the travel click and the FTL (about 4.2 s). Nothing logged changes during it.

## The intro patch

- Videos are `bk2` resources (Bink 2, revision `KB2n`): a 16-byte main part and the file in `.stream`. The start-up logos are `917be57698744617`, `3d7f04931c0dd5f2` and `c08afc84be2bc3fa`; the title's videos `5263c1fe0615c6ad` (8 s) and `c4038098ec6384ab` (98 s).
- A cut keeps the header, a frame table of the first frames and their data. A one-frame video never counted as ended, so a third of a second is kept.
- The title's video ends only once its voice line has finished, so a cut picture alone leaves a black screen with the line playing. Each logo has a sound of its own too.
- The patch silences every clip of `content/audio/intro_logos` and the title's voice line in `content/audio/<language>/cutscenes`.
- Sound object ids of those lines differ by language and change with updates; their parent object stays (`631201114` for the 100.7 s line). Build 26251122 removed the short line (parent `394469756`) and six others from the English bank.
- `content/audio/cutscenes_sfx` (the ship cutscenes' sounds) holds copies of all nine intro_logos clips (62 objects in both banks) and of 58 sounds of `content/audio/foley_player`. A patch carries a bank whole, so a copy of cutscenes_sfx in it would put the game's version of the rest of that bank over another sound mod's: the patch changes only intro_logos and the cutscenes banks. The game plays the first loaded copy of a sound, and intro_logos is the only bank in the start-up's package (`packages/splash`, `83fa1822be1891ab`); cutscenes_sfx is in a cutscene package (`4f2ac109b7ad817a`).
- The patch carries a whole copy of each bank it changes, so an update can make a copy stale. Rebuild after updates that touch these banks.
- Only the voice languages installed where the patch is built can be covered.

## What can't be done from Lua 5.1 this way

- Closing the galactic map in one press: Lua can't send the game a key, and the close request is game memory.
- Faster walking on the ship: the speeds are game memory, and a time multiplier would speed up the whole ship.
- Skipping the title's "press a button" screen: V8 used a flag in game memory.

## Prior art and credits

Facts other mods taught; no code of theirs is used.

- [War Journalist](https://github.com/HWG90/DBF_PhotoMode): the time step policy for slowing the game.
- Skip All Intro (Nexus 17681): which videos and sound banks the intro uses.

## Research tools

- `tests/test_release.py`: the script under Lua 5.1 (lupa) with a fake loader and engine. Needs only Python with lupa.
- `tests/mutate.py`: runs that test against copies of the script with one guard removed each; every one must fail.
- `research/build_release.py`, `research/intro_sounds.py`, `research/intro_videos.py`: the build and the intro patch, which need the maintainer's workspace.
