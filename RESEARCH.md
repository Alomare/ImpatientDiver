# Impatient Diver: how it works in the game's code

Impatient Diver skips the intro videos at game start and the ship's cutscenes (log-in intro, cryo pod, FTL and lobby join), takes the Helldiver from the hellpod straight to the drop location screen, cuts the zoom after a drop location is picked, triples movement speed aboard the ship and closes the galactic map in one press. Every skip works by letting the game's own code finish what it is waiting for sooner: it moves a timer, a deadline or a progress value, never calls the game's abort paths.

All addresses are game.dll RVAs for build 25480438 (in a Ghidra session based at 0x7ffcea020000, `FUN_7ffceb2b48b0` is RVA 0x12948b0). The mod does not depend on them: every global, structure offset and timer wait is read from code signatures (below), so it survives updates that move code. "Live" marks behaviour seen in the game; the rest is read from the decompiled code.

## The cutscene system

The ship sequences are not UI screens (the screen stack and presenters stay idle). They are scenes of the game's cutscene system (debug strings "Cutscene", "play_scene: %s", "interrupt_current_scene: %s").

| What | Where |
|---|---|
| Cutscene manager | `[0x346d530]`; +0x1908 previous, +0x190c current, +0x1910 queued scene id (0 = none) |
| Scene context | manager + 0x60; +0 the current phase; timer stamps at context + 0x88 / + 0x90 (u64 microseconds) |
| Scene clock | `[[0x3326348] + 0x18]`, u64 microseconds |
| `play_scene(manager, id)` | 0x12948b0; also sets the avatar hold bit (see "Avatar hold flags") |
| `interrupt_current_scene(manager, force)` | 0x12954d0; jumps to the scene's abort phase |
| `set_current_scene_to_done` | 0x1295720 (referenced only from a data table); jumps to the scene's done phase |
| Scene id to name | 0x117e950 (a jump table; the mod reads the names from it) |
| Phase dispatcher (phase entry handlers) | 0x117e410(context = {manager, manager + 0x60}, scene, phase) |
| Scene update dispatcher (per scene, per frame) | 0x117d830 |

Scene ids: 1 mission_extraction, 2 ship_bridge_hellpod_launch, 3 ship_bridge_intro, 4 ship_clan_station_reveal, 5 ship_cryogenic_intro, 6 ship_hellpod_launch, 7 ship_intro, 8 ship_mission_return_failure, 9 ship_mission_return_success, 10 ship_name_resource_loading, 11 ship_planet_arrival, 12 ship_planet_departure, 13 ship_teleporter_arrival, 14 ship_teleporter_deeplink_join, 15 ship_teleporter_network_join, 16 tutorial_avatar_respawn, 17 tutorial_cape_ceremony, 18 tutorial_intro, 19 tutorial_outro, 20 tutorial_outro_to_ship.

Each scene's update changes phase itself when a timer runs out, and the phase change does real work (placing the Helldiver, firing flow and animation events, returning the camera and control, queuing the next scene). The timer checks all look like `mov rcx, [reg + 88h]; add rcx, imm32; cmp [clock + 18h], rcx; jb ...`, with the clock loaded by a rip-relative mov.

**Fast-forward (how every cutscene skip works).** While a timed phase runs, the mod writes `now - wait` into its stamp, so the game's own update sees the wait as over on its next frame and changes phase with everything it normally does. Phases that wait on loading or other players are left alone: once a phase's timer is over, the mod waits as long as the game does. A stamp ahead of the clock means something is wrong and stops the fast-forward. Since loading waits are never cut, a squad client can't get ahead of the host.

### Phases the mod fast-forwards

| Scene | Phase: wait | What else the phase waits on |
|---|---|---|
| 7 ship_intro (log-in, camera outside the ship) | 1: 3 s, 2: 0.33 s | phase 1 also a loading flag; phase 3 queues ship_bridge_intro |
| 3 ship_bridge_intro (walk to the bridge; update 0x116d7a0) | 2: 2 s, 3: 1.25 s, 4: 1.75 s, 5: 2.5 s, 6: 1 s, 7: 1.5 s, 8-10: 1 s, 11-12: 2 s | ends in its done phase 13 |
| 13 ship_teleporter_arrival (cryo pod; update 0x1177e80) | 2: 1.5 s (stamp + 0x90), 3: 7.5 s, 4: 33 ms | phase 1 waits for the pod to arrive |
| 12 ship_planet_departure (FTL) | 3: 3.38 s | and the next scene's resources (`0x1294830(_, 11)`) and the manager's 16 resource slots at + 0x9ee98 (`0x1295970`); phase 4 queues 11 |
| 11 ship_planet_arrival | 2: 6.4 s | none; an audio flag event at 3.67 s is checked before the change, so it still fires |
| 15 ship_teleporter_network_join (lobby join; update 0x1179e30) | 3: 5 s | phase 1 and phase 3 also wait for loading; phase 4 queues 13 |

Joining a lobby plays 15 -> 12 -> 11 -> (about 5 s) -> 15 -> 13. The mod follows such a chain with one press: an ended scene waits up to 30 s for a follow-up scene.

### The cryo pod scene (13)

Natural timeline (live): phase 1 (the pod rolls in) about 2.6 s, phase 2 1.0 s, phase 3 (walk-out) 7.5 s, phases 4 and 5 a few frames. The update:

- 1 -> 2 when the player list entry reaches state 2 (pod arrived); calls `0x11d13a0(entry, 1, 0)`.
- 2 -> 3 after 1.5 s: sends the scene rig slot 0x60ed8c39 anim event 0x23173e19, the flow events (0xaa3994d2, 0xdc19bd06) and (0x81320af8, 0x7f35c126), and the avatar anim event 0x23173e19 (the walk-out clip).
- Phase 3 calls `0x11cf0a0()` every frame; 3 -> 4 after 7.5 s (phase 4 returns camera and control); 4 -> 5 after 33 ms (phase 5 fires events 0xd130d731 and 0x44e9d562 and ends the scene).

The Helldiver's body barely moves: the game places it at the exit spot a few frames into phase 3. The visible walk-out is only the avatar's cinematic animation layer (layer 14, 1-based: state 36 normal, 0 the in-pod loop at scene start, 6 the walk-out clip at phase 3). So the fast-forward waits for the pod in phase 1 and holds 30 frames in phase 3 for the placement before moving the timer on (live: body visible at the right spot, control and interaction normal; the Helldiver is briefly shown finishing the walk-out clip).

### The screen fader

`[0x347cda8] + 0x128`: duration + 0x784, elapsed + 0x798, alpha + 0x794, start + 0x79c, target + 0x7a0, hold + 0x7a4. Set by `0x11d66c0` (fade to black), faded back by `0x11d6760`. ship_planet_departure fades to black at phase 1 and ship_planet_arrival again at phase 3; fast-forwarded, both fades land within half a second as a black flash. During those two scenes the mod holds duration, alpha, start and target at 0 (live: a brief pop instead of the flash). ship_hellpod_launch also uses this fader for the loading screen (alpha 1 with a 3 s hold).

## Ending a scene early: abort and done paths, and the crash they cause

`interrupt_current_scene` and `set_current_scene_to_done` both jump the scene's state machine through the phase dispatcher, skipping the phases between:

| Scene | Abort phase (interrupt) | Done phase |
|---|---|---|
| 7 ship_intro | 4 (ends it outright) | 3 (queues ship_bridge_intro) |
| 13 ship_teleporter_arrival | 6 (skips phase 5's events) | 5 (skips phase 4's camera and control) |
| 5 ship_cryogenic_intro | 5 | 4 |
| 3 ship_bridge_intro | | 13 |

The game itself interrupts with `if (current != 0) interrupt_current_scene(manager, 0)` (for example in 0x1356a30 and "unload_scene_safe"). Results in the game:

- **Interrupting ship_intro crashes a later hellpod launch.** It ends the log-in intro cleanly on the spot, but its abort phase skips all of ship_bridge_intro, including its done phase 13, which resets cutscene manager state (+0x193c, +0x2418/+0x241c/+0x2420 and the camera blends at +0x1c88/+0x1da0/+0x1eb8). The next ship_hellpod_launch relies on that state: the camera takes an odd angle in the ship while the hellpods fire, then the game crashes a few seconds into the descent, during loading (an engine thread, no game.dll frames). Fast-forwarding through both scenes instead has no such effect.
- Interrupting 13 returns control but leaves the avatar model in the pod pose, attached to the pod (it orbits the player), the pods rolling and interaction blocked.
- Setting 13 to done ends it with the camera stuck and no control.
- Calling the phase entry handlers in order (0x1177b70 for 13) ends the scene and returns control, but the per-frame update's work (above) never runs: the Helldiver is left invisible or stuck in the pod area. Resetting the cinematic animation layer by hand brings back the gun, pistol and cape but not the body.

## Cutscene audio: game hashes and Wwise ids

Scene phases post audio through `post_audio` (0x12982d0(_, hash)). The hash is the game's own, not a Wwise event id: `post_audio` turns it into the Wwise id through a runtime map at `[0x346c9f8]` (buckets, capacity, empty key, multiplier, the same layout as the game's other hashed maps; lookup at 0x12556e0). So these hashes are not found in the sound banks; read the map in the running game to get the Wwise id, then look that up in the banks.

| Posted by | Game hash | Wwise id | Wwise action |
|---|---|---|---|
| ship_intro phase 3 | 0x41ca6b56 | 1472490507 | a Stop |
| ship_bridge_intro phase 9 | 0xf70237cb | 3081520204 | |
| ship_bridge_intro done phase 13 | 0x616c02e2 | 101254742 | |
| ship_bridge_intro done phase 13 | 0x1110bb89 | 756337494 | a SetState |
| ship_teleporter_arrival phase 5 | 0x44e9d562 | 3379619309 | |

All five are in the bank `content/audio/cutscenes_sfx`. Skipping ship_bridge_intro's done phase (the interrupt above) leaves the galactic map without some of its sounds, most likely through the missing SetState. Posting the done phase's pair (0x616c02e2, 0x1110bb89) by hand restores them; also posting 0x41ca6b56 and 0xf70237cb plays a cryo pod rolling sound. On the title screen's no-intro start (below), where neither scene runs, the map has all its sounds, so that state is also set some other way. 0x1110bb89 and 0x616c02e2 are posted together by four more functions (0x116bf50, 0x116c500, 0x116cc30, 0x116ce10) and the bridge intro's phase handler 0x116d0a0, none called directly (likely through a function table).

## Other scenes (not skipped)

- **2 ship_bridge_hellpod_launch** (update 0x116b640): phase 1 waits for no open menu and for hellpods (`[0x33265f0] + 0x20`); phases 2-4 send each slot (0, 3, 2, 1) the enter-pod animation event 0x514 (`0x11ce740`) 1/3 s and 1/6 s apart (stamp + 0x90); phase 5 waits until 7 s after the scene started; phase 6 queues 6.
- **6 ship_hellpod_launch** (update 0x1171be0): phase 1 3.33 s; phase 2 waits 10 s **and** `0x11d5b10` (game state 4 and the players' mission state), then fades to black with a 3 s hold (the loading screen); phase 3 ends the scene. Because phase 2 waits for the mission to load, fast-forwarding scenes 2 and 6 saves only 2-4 s (live).
- **1 mission_extraction** (entry 0x1169530): phase 1 1 s, then opens MissionSummary (presenter 23); phase 2 waits until it closes; phase 3 6.67 s, then a fade; phase 4 (0x1169eb0) waits for game state 3 and up to 1 s for other players' flags (players table + 0x3ac, bits 9/10); phase 5 1/6 s; phase 6 queues 9 or 8. Closing MissionSummary early (live, host or client) only shows a black loading screen for the rest of its time, and once left the game stuck on it.
- **9 ship_mission_return_success** (update 0x1173e30): phase 1 5.83 s is the elevator ride: its entry (0x1173200) teleports the local Helldiver to one of four nodes at the bottom of the elevator (by player index: 0xd25583b5, 0x464952a5, 0x11ffed75, 0x75108d67) and the elevator carries it up; fast-forwarding phase 1 ends the scene before the ride and leaves the Helldiver stuck on the lower level (live). Phase 2 6.67 s, or at once while input action 0x900000000 is down (the game's own skip input, `[0x349cf18] + 0x328`); then MissionEnd (13) opens; phase 3 waits until it closes.
- **8 ship_mission_return_failure**: phase 1 1.67 s, opens MissionEnd, waits until it closes; no teleport.

## Menus: the presenter manager

The presenter manager is `[0x347ce28] + 0x4288`: current presenter + 0xc, stack of presenter ids + 0x14, depth + 0x28. Presenter ids (names table at 0x21dc810): 1 Main, 2 LoadingMission, 3 LoadingShip, 5 Armory, 13 MissionEnd (`ui.MenuMissionEnd`), 14 Loadout (the Hellpod briefing), 15 Hologram (`ui.MenuHologram`, the galactic map), 23 MissionSummary, 24 Load, 25 Join.

- `open(manager, id, data)` 0x14c0350 first closes the current presenter through `close_current(manager)` 0x14c0900, which runs the presenter's exit (0x14b5f20; for 15: `pop_screen(24)`, the Hologram screen, then the view teardown) and resumes the previous presenter.
- `PresenterManager::update` 0x14bf750 walks the stack and closes every presenter whose close request is set: `check(manager + 0xd8, id)` 0x14bdc20 is a switch over presenter ids. The requests are bytes in small objects that the presenter creation (0x14b7b60) allocates and clears: Hologram's at `[collection + 0x98] + 0x10`, MissionEnd's the first byte of `[collection + 0x88]`, MissionSummary's of `[collection + 0xd8]` (collection = manager + 0xd8). Their view models set them when the player continues.
- **Galactic Map Quick Exit:** on Escape (while the option ESC Closes Galactic Map is On) or a Mod Bindings Menu key while presenter 15 is current, the mod sets the Hologram's close request; the game closes the map that frame from any zoom level, as it does itself (live). A key already down when the map opens doesn't count.
- The game state: `[0x3326340] + 0xac21c`, 3 on the ship, 4 in a mission.

**Chat input open:** the HUD `[0x346d538]` (active byte + 0x24e335), its chat widget at + 0x14498, the text input's open byte at widget + 0x139b8 (live). The map keys are ignored while it is set.

## Hellpod to Loadout

- **Entering the hellpod is a seat transition** (`set_entering` 0x63a7b0, "seater.%u.entering"). Seater component `[0x3326d78]`: a hashed map of entity id -> record index at + 0x20 (capacity + 0x28, empty key + 0x2c, multiplier + 0x30), 64-byte records at `[+ 0x48]`: +0 seat collection (the hellpod's entity id), + 0x14 current node, + 0x18 target node, + 0x28 deadline (u64 microseconds on the scene clock), + 0x30 moving, + 0x32 instant.
- The seat update 0x639b40 walks the node graph: while moving, `if clock < deadline return`; else step to the next node and set deadline = now + that edge's time (0 when instant). At the target the seat is reached and the game opens the Hellpod briefing (presenter 14).
- The briefing's loadout screen (MenuScreenType 11, `[[0x347ce38] + 0xb0]` while the stack's type is 11) waits in intro phase 1 (+ 0x27398c) on a 2 s float timer (+ 0x273988, counted down at 0x146909f) before building the drop location UI.
- **The local Helldiver:** player manager `[0x3326468]`: avatar reference at + 0x3a8, valid while + 0x88 is set (0x7fff = none). The resolver 0xfd9ba0 turns it into an entity id: entity manager `[0x346bf98]`, reference map at + 0xf22ec8 (capacity + 0xf22ed0, empty + 0xf22ed4, multiplier + 0xf22ed8), the id at manager + 0x1e65e4 * 8 + index * 24.
- **The ship's hellpods:** `[0x3326428]`, count + 8, entity pointers from + 0x68 (each entity's id at + 8).
- The game's hashed maps: buckets of {key u32, value u32}, a power-of-two capacity, an empty key and a multiplier; the probe starts at key * multiplier (u32) and walks linearly until the key or the empty key.
- **The skip:** on the ship, when the local seat goes from free to moving into one of the ship's hellpods, each step's deadline is moved to now until the seat is reached (the game runs every node change and the seat completion), then the briefing's intro timer is set to 0 once phase 1 shows. Leaving the hellpod and every other seat are left alone. Live: interacting with the hellpod goes straight to the drop location screen, and the briefing works normally (tested solo; in a squad not yet confirmed in game).

## Drop Location Zoom

- The loadout screen has a page at + 8: 0 the drop location map, 1 the loadout (`set_page` 0x1470d90). Picking a drop point sets the screen's zoom target (+ 0x2739c4) to 1.0.
- The loadout screen's update (0x1468320, at 0x14684ef): while the drop group (`[0x3326aa0]`, players at + 0x4ec0) has players, its zoom progress (+ 0x4f64) moves toward the target at 1.0 per second (`move_toward(current, target, 1.0, dt)` 0x173cb30); on the map page, once target and progress are both 1.0, the screen calls `to_loadout` (0x146f510, set_page(1)). Without players in the group (a squad client), a screen whose + 0x27fe byte is clear opens the loadout page once the group's synced progress (+ 0x55f680, copied from network messages by 0x725160) is 1.0; with the byte set it doesn't switch there.
- **The skip:** on the map page, with the target at 1.0 and the progress (or, without players, the synced value) between 0 and 1, it is set to 1.0; the game opens the loadout page itself. Live as host (progress) and as a squad client (synced); a later network message refreshes the synced copy, but the page has switched by then.
- Not the zoom: `set_page(screen, 1)` asks the camera system `[0x346d560]` for a blend to the loadout view (`request(camera, position, target, type 5, 1.0 s, fov 70)` 0x127d1f0; back to the map 0.75 s). The camera keeps blends in a ring of 32 entries of 0xe8 bytes at + 0x200 (read index + 0x1f8, write index + 0x1fc; type + 0x2a4, duration + 0x2a8, elapsed + 0x2ac, delay + 0x2b0, reverse + 0x2b4, ring base included); its update adds dt to the latest blend's elapsed, and `blend_done` (0x127ba60) is elapsed >= duration. Ending that blend skips the window move into the ship as the loadout appears, which comes after the zoom.

## Intro cinematics

- **Boot logos:** StateSplash (on_enter 0xadf700, update 0xae03c0, exit 0xae0930) plays three videos from the table at 0x32938e0 (0x20 bytes each: package, video, start/stop audio, a skippable byte at + 0x18). On PC it skips them itself (`[[0x3326348] + 0x28]` = 1 and `0x13f03d0()`), and is gone about 17 s after launch.
- **The announcement and the recruitment trailer** belong to StateTitleScreen (on_enter 0xad5950, update 0xad7cb0, on_exit 0xad8df0), registered in the game's state list `[0x3326e68]` (count + 0x2590, 16-byte {object, type} entries from + 0x2598, type 0xb8). It owns a video player at + 0x81a8 and queues 0x2b1a74c2 (announcement and trailer) then 0xde13da08.
- on_enter stores the game object (`[0x3326340]`) at title + 0 and sets the title's no-intro byte (+ 0x10) when the game's flag at game + 0x106f, or its transition argument (a return to the title), is set. With the byte set and no message pending, it also calls the start handler 0xad6a90 at once (what a key press on the title screen does). No other instruction reads game + 0x106f, and none writes it with that displacement (a bulk copy, likely a launch option).
- The update runs the setup 0xad5cf0 once three packages are loaded (then sets + 0x144). The setup builds the video player only while + 0x10 is clear (then sets + 0x145). The update queues the videos only with a player, not yet queued (+ 0x146) and + 0x10 clear.
- **The skip:** before the first title screen the mod sets game + 0x106f to 1 (left alone if already set) and puts the byte back once the title screen has started. If the title screen is already up with + 0x10 clear and nothing queued, it sets + 0x10 instead (the title screen then waits for a key press, as after the videos). Live: no announcement or trailer, a short loading screen, then straight onto the ship; this start also skips the log-in ship intro (no ship_intro scene runs, as on a return to the title). The planet outside the ship can look grey for about 30 s while it streams in, since the ship comes up much earlier than the videos allow.
- The key-press path inside the title update: with an input seen, title + 0x11 clear, the player playing (0x1795b10) and title + 0xa56b set (plus + 0xa541 or `[0x347cdd8] + 0x87479`), it calls `0x1795130(player)`, which stops the current video, posts its stop audio and flips the player's slot: one video per press. Calling it from a mod under the same conditions did not skip anything in the one test made.
- Players' launch option `+connect_lobby -1` (Steam's join-a-lobby argument, parsed by the exe) also skips the intro; whether it does so through game + 0x106f is not yet confirmed in game.

## Ship Walk Speed Boost

- The movement update 0xa6c700 gets the Helldiver's AvatarComponentData record from the resolver 0x508db0 and picks the target speed from it: swim + 0x30; crouched (state bit 77) sprint + 0x28, jog + 0x24, aim + 0x1c, walk + 0x20; prone (bit 78) + 0x2c; standing sprint + 0x14 (empty stamina + 0x18), jog + 0x10, aim + 8, walk + 0xc. Walk and aim are multiplied by a direction factor (+ 4). It then applies injury and slow factors, takes the minimum with a per-move limit and caps the result at 10.0 m/s (`movss xmm6, [0x23c7554]; minss`, at 0xa6d0de).
- The resolver: avatar manager `[0x3326d20]`, a hashed map of entity ids to copy indices at + 0x547c70 (capacity + 0x547c78, empty + 0x547c7c, multiplier + 0x547c80). A hit gives a private copy of the whole record at + 0x547d24 + index * 0x354; a miss gives the shared type record (0x508770). An avatar spawned with its own entity settings has a private copy; the ship's Helldiver always does (the ship sets walk 1.5 and jog 4.08), mission Helldivers normally don't. (The HealthComponentData resolver 0x506580 has the same code with records of 0x43c bytes.)
- **The boost:** on the ship (game state 3) the ten ground speeds in the local Helldiver's private copy are set to min(speed x 3, cap), never lower, and put back when the option is turned off or the game state leaves 3 (only into that Helldiver's own record, and only while it still holds the boost). A record the game rebuilds is boosted again, never compounded. Live: on the ship the Helldiver jogs (4.08 -> 10 m/s, about 2.45x) and Shift doesn't sprint; a gamepad's slight push walks (1.5 -> 4.5 m/s); doors, stairs, terminals and the armory behave normally; mission speeds are untouched.
- Going past 10 m/s would need a change to the game's code (the cap is shared with missions), which this mod doesn't do.

## Avatar hold flags (a dead end)

While any cutscene holds the Helldiver, the avatar record (`[0x3326d20] + 0x53e134 + ai * 0x1238`, `ai` from the map at `[0x3326d20] + 0xf8`) has +0x750 = 0x40000000, +0x758 bit 0x800 and the float +0x7e4 = 1.0; all clear on the frame control returns. The 0x40000000 is bit 62 of a 192-bit avatar flag set (avatar manager + 0x53e880 + ai * 0x1238), changed through a notifier 0xa3f220(component, mask, set); the generic setter 0xaa0d60(mask) is called with 0x4000000000000000 by the cutscene system (`play_scene`, and 0xaa0960 when a scene is playing as the flags are set up). Clearing these fields (live) sticks but changes nothing: control returns at the normal time. They record that the avatar is held; the lock itself is the cutscene's phase logic.

## Engine behaviour seen along the way

- There is no world time scale, and `AnimationBlenderComponent.set_speed/set_time` only affect crossfade animations, not state-machine states.
- `Unit.animation_layer_info(unit, layer)` returns (time in state, state length); layers are 1-based and layer 0 crashes the game.
- Animation events only act when the state they leave from is current. Advancing the cryo pod's or the camera rig's animation states only changes visuals: the scene keeps its timing (the game code drives it, the camera just follows the rig).
- The cryo pod is not a seat (the avatar's seater record stays empty through it).

## Signatures (research/signatures.py)

All signatures are optional: a missing one turns off only the feature that needs it. At startup each is tried at this build's address, else game.dll's executable sections are searched over a few frames, and a signature counts only if it matches exactly once. Values are read from the matched instructions, and a value read by several signatures must agree.

| Name | RVA | Gives |
|---|---|---|
| interrupt_site | 0xad6ca2 | cutscene manager global, current scene offset (the interrupt itself is not called) |
| t13p2 | 0x1178030 | scene clock global and its + 0x18; scene 13 phase 2 stamp (+ 0x90) and wait (1.5 s) |
| t13p3, t13p4 | 0x1177f9b, 0x1177ec4 | scene 13 phases 3 (7.5 s) and 4 (33 ms) |
| t12p3, t11p2 | 0x117df3d, 0x117dee2 | FTL departure phase 3 (3.38 s), arrival phase 2 (6.4 s) |
| t15p3 | 0x1179efb | lobby join phase 3 (5 s) |
| t7p1, t7p2 | 0x117dbb1, 0x117db78 | ship_intro phases 1 (3 s) and 2 (0.33 s) |
| t3_2s, t3_125, t3_175, t3_25, t3_1s, t3_15 | 0x116d7d8, 0x116d809, 0x116d8bb, 0x116d92f, 0x116d949, 0x116d97a | ship_bridge_intro waits of 2, 1.25, 1.75, 2.5, 1 and 1.5 s |
| names | 0x117e950 | scene id-to-name switch (names read from its table) |
| fader | 0x11d66c0 | fader global, + 0x128, alpha, start, target, duration |
| game_state | 0x11d5b23 | game object global, game state offset |
| local_ref | 0x4db76b | player manager, local-active and avatar reference offsets, the resolver's call |
| ref_resolver | 0xfd9ba4 | entity manager and its reference map (must be the function local_ref calls) |
| seaters | 0x639846 | seater component and its map and records |
| seat_wait | 0x639d57 | seat moving, target and deadline offsets, the clock |
| hellpods | 0xadbaaf | hellpod manager, entity list |
| screen | 0x1082ef0 | screen stack global, the screen slot |
| briefing_intro | 0x146909f | loadout screen intro phase and timer |
| loadout_page | 0x1470db3 | loadout screen page offset |
| zoom_ramp | 0x14684ef | drop group global, players, target, progress, synced progress, the + 0x27fe byte, move_toward and to_loadout calls, page (must agree with loadout_page) |
| presenters | 0x662520 | UI global, presenter manager offset, stack, depth |
| presenter_open | 0x14c038e | current presenter offset, close_current |
| presenter_update | 0x14bf890 | close request collection offset, check, close |
| hologram_request | 0x14bdcbb | the Hologram's request slot and flag (must lie inside the check found) |
| chat_notice | 0x12f2f81 | HUD global, its active byte, the chat widget offset |
| chat_input | 0x18608d0 | the chat input's open byte |
| avatar_copy | 0x508db0 | avatar manager, private copy map and copies (record size 0x354 kept literal) |
| speed_record | 0xa6ca4e | the movement update's call of the resolver (must be avatar_copy) |
| speeds_crouch, speeds_stand, speeds_walk | 0xa6cc91, 0xa6cd29, 0xa6cdde | the ten speed offsets |
| speed_cap | 0xa6d0bf | the 10 m/s cap constant |
| title_enter | 0xad59f7 | game + 0x106f flag offset, title no-intro byte |
| title_register | 0xad5c71 | state list global, title type, count and entries |
| title_update | 0xad7ce8 | + 0x144, the setup's call |
| title_setup | 0xad645f | + 0x10, the player + 0x81a8, + 0x145 (must lie in the setup the update calls) |
| title_queue | 0xad7f9b | + 0x145, + 0x146, + 0x10 (must lie in the update) |

## Gotchas

- Every Bingus Shared Loader addon shares one LuaJIT FFI namespace, where a C name keeps its first declaration. The mod declares its Windows functions under its own names (`int imd_ReadProcessMemory(...) __asm__("ReadProcessMemory");`), so another mod's declaration of `ReadProcessMemory` with other types can't change its calls.
- Waits measured in frames get shorter at high frame rates (a 300-frame window is 2 s at 144 fps). The mod measures every wait in seconds of game time.
- Spacebar is also the jump key: a skip key on spacebar can fire while the player jumps (at extraction, for example). The mod never touches scenes 1, 8 and 9.
- Mod Bindings Menu lists only bindings registered in the current session, so a binding registered only in some modes disappears from the menu (and its action may go to another mod).

## Prior art and credits

Facts other mods taught; no code of theirs is used (except `src/bingus_text.lua`, CowboyBingus's, under the Zero-Clause BSD license).

- [Ship Station Hotkeys](https://github.com/CowboyBingus/ShipStationHotkeys) by CowboyBingus (formerly Galactic Menu Hotkey, in [Vanilla Plus Megapack](https://github.com/CowboyBingus/VanillaPlusMegapack)): the UI screen stack and presenter manager, the Hellpod briefing's intro timer (its F8 shortcut expires the same timer), the instant Hellpod entry and the hellpod system at `[0x33265f0]`.
- [Consistent Vaulting](https://github.com/CowboyBingus/ConsistentVaulting) by CowboyBingus: the avatar record layout used to find the hold flags.
- [HD2Runtime by SkyeShade](https://github.com/SkyeShade/HD2Runtime) (`docs/helldiver-fields.md`): the AvatarComponentData speed fields and the ship Helldiver's private record (walk 1.5, jog 4.08).
- [Better Chat](https://github.com/Alomare/BetterChat): the chat input's open byte.

## Research tools

- `research/signatures.py`: generates the signature block (and the shared signature engine) in `skip_intro_animation.lua` from a game.dll dump; `--check` verifies every signature matches once and the script is current.
- `tests/test_release.py`: runs the built entry under LuaJIT with a game.dll dump (not included) mapped as process memory, simulating the cutscene manager, clock, fader, presenter manager, hellpod seats, title screen and movement records.
