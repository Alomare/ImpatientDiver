# Skip Intro Animation: investigation notes

Game build 25480438. Unit names are resource hashes; "S<n>" is a 0-based state index in that unit's
animation state machine (dumps via `_shared/filediver/cmd/cryo_probe`).

## The two sequences

- **Boot intro** (camera outside the ship, then the Helldiver walks to the centre). The exterior shot is a
  separate cinematic world: destroyer exterior guns plus camera rigs `3babe3b5c727bf7b` (S46, 3.3 s) and
  `bb3881db2f8d8164`. The ship interior loads in parallel. During the walk the local Helldiver plays
  cinematic-layer states (layer 14, 1-based: S36 -> S18 -> S3). The cinematic world's remaining units are
  destroyed on the frame control returns.
- **Cryo pod** (after the tutorial, or being sent back to the ship). The pod `33cb06b89be208da` and rig `3babe…` spawn
  when it starts and are destroyed when it ends:

  | Time from pod spawn | Event | Length |
  |---|---|---|
  | 0 s | pod S0 (closed); rig S55 | S55 = 9.98 s |
  | ~3.2 s | game sends "open": pod S1 `cryo_exit_pod`, chamber S1 `ready_open`, rig S54 | 7.33 s / 9.25 s / 8.33 s |
  | ~10.5 s | pod S1 ends (`cryo_exit_done` -> S0); scene ends | |

## What is known

- Neither sequence is a UI screen (screen stack and presenter stay idle), unlike the briefing intro that
  Ship Station Hotkeys skips by zeroing a timer.
- The camera is attached to the rig: putting the rig into its Empty state freezes the camera, but the sequence
  carries on and control returns at the normal time (exp-1). The game's own code drives the timeline.
- There is no world time scale, and `AnimationBlenderComponent.set_speed/set_time` only affect crossfade
  animations, not state-machine states.
- `Unit.animation_layer_info(unit, layer)` returns (time in state, state length); layers are 1-based and
  layer 0 crashed the game.
- Animation events only act when the state they leave from is current (exp-1 fired `cryo_exit_done` on a
  closed pod and nothing happened).

## Animation-level results

- exp-1: putting the camera rig into its Empty state freezes the camera; the sequence keeps its timing.
- exp-2: advancing the pod along its own transitions only changes visuals. `cryo_exit` from S0 sent the
  pod forward empty (the player is placed in the pod separately); `cryo_exit_done` from S1 made the pod
  vanish. The scene kept its normal timing either time. **Animation events cannot skip the sequence.**

## Native results

- exp-3: the local avatar's seater record stays empty through both sequences: **the cryo pod is not a seat.**
  The avatar exists before either sequence starts (boot: just after the exterior shot begins).

## Snapshot method (exp-4)

Read-only snapshots, every 15 frames during a sequence and on each mark, of the local avatar's native state
(layout from Consistent Vaulting, build 25480438), written to `SkipIntroAnimation_snaps.log`:

| Region | Address | Size |
|---|---|---|
| players | `[0x3326468]` | 0x1000 |
| mode | `[0x33266a0]` (mission mode; +0x40 mission type) | 0x80 |
| avatar_record | `[0x3326d20] + 0x53e134 + ai*0x1238` | 0x1238 |
| avatar_input | `[0x3326d20] + 0x150 + ai*0xa7aec` (input state) | 0x2000 |
| move / mover | `[[0x3326558]+0x48c8] + mi*132`, `[[0x3326558]+0x48d0] + mi*164` | 132 / 164 |

`ai` is the avatar's index from the map at `[0x3326d20]+0xf8`; `mi` from `[0x3326558]+0x48a0`.
The offline diff looks for fields that count down during a sequence or flip at its start and end.

## exp-4 result: the hold flags

Diffing the snapshots (middle of each sequence against well after control returns) found exactly two fields
that behave the same in both sequences, both in the avatar record (`[0x3326d20] + 0x53e134 + ai*0x1238`):

| Offset | During either sequence | With control |
|---|---|---|
| +0x750 (second word of the flags block at +0x74c) | 0x40000000 | 0 |
| +0x7e4 (float) | 1.0 | 0.0 |

+0x758 also holds 0x800 during both. All of them are set before the sequence is visible and clear on the
frame control returns (boot: between f1680 and f1691, the "control" mark was f1691; cryo: f5595, mark f5616).

## Current lead (exp-5)

First memory writes, only on the Skip test key, only while the hold bit is set and the record's identity
(+0x28 == avatar id) matches, through WriteProcessMemory. Press 1 clears the hold bit; press 2 also clears
the 0x800 bit and the weight; press 3 keeps all three cleared for 3 seconds. Each write is followed by a
second of logged readback, to show whether the game sets them again.

## exp-5 result: the hold flags are a mirror, not the lock

Clearing +0x750's hold bit (and +0x758's 0x800 bit and the +0x7e4 weight) stuck: the game did not set the
hold bit again, and only re-set 0x800 about 55 frames later. But nothing changed on screen and control
returned at the normal time in both sequences. The fields record that the avatar is held; the lock itself
is owned by other native state that does not re-read them.

## Static analysis

The rest of this research used an offline copy of game.dll's code for build 25480438 (not included). Addresses
below are RVAs in game.dll; "Ghidra session" addresses use base 0x7ffcea020000.

- The avatar flags are a 192-bit bitset at avatar manager + 0x53e880 + ai*0x1238 (24 bytes). The "hold bit"
  0x40000000 at record +0x750 is **bit 62** of the first qword.
- Gameplay code tests bit 62 alongside others, e.g. `0xa5b93b` tests 0x4000000000010000 (bits 16 and 62)
  against the first qword and branches if either is set; masks are also built with `bts r, 0x1e` on the
  second half (0x127efbc, 0x1288a56, 0x128adab, 0x128bc97).
- Almost nothing writes the block inline (one `mov dword [rcx+0x53e880], ecx` at 0xa6c6ac), and no
  "load 62, call helper" pattern exists near its references. The block is written through computed pointers
  or whole-record copies (plausibly network replication), which needs a decompiler with cross-references
  (Ghidra) to trace.

## Ghidra: the cutscene system

Decompiling the cutscene code traced the hold bit:
avatar flags change through a notifier `0x7ffceaa5f220(component, mask, set)`; generic setter
`0x7ffceaac0d60(mask)` is called with mask 0x4000000000000000 by three functions, which belong to the
game's **cutscene system** (debug strings "Cutscene", "play_scene: %s", "interrupt_current_scene: %s"):

| RVA (session base 0x7ffcea020000) | What |
|---|---|
| `[0x346d530]` | cutscene manager; +0x1908 previous, +0x190c current, +0x1910 queued scene id |
| `0x12948b0` | `play_scene(manager, id)`: starts a scene, sets the avatar hold bit |
| `0x12954d0` | `interrupt_current_scene(manager, force)`: runs the scene's cleanup handler |
| `0x117e950` | scene id to name |
| `0xaa0960` | avatar flag setup: sets the hold bit if a scene is playing |

Scene ids: 1 mission_extraction, 2 ship_bridge_hellpod_launch, **3 ship_bridge_intro**,
4 ship_clan_station_reveal, **5 ship_cryogenic_intro**, 6 ship_hellpod_launch, **7 ship_intro**,
8 ship_mission_return_failure, 9 ship_mission_return_success, 10 ship_name_resource_loading,
11 ship_planet_arrival, 12 ship_planet_departure, 13 ship_teleporter_arrival, 14 ship_teleporter_deeplink_join,
15 ship_teleporter_network_join, 16 tutorial_avatar_respawn, 17 tutorial_cape_ceremony, 18 tutorial_intro,
19 tutorial_outro, 20 tutorial_outro_to_ship.

The game interrupts scenes itself with `if (current != 0) interrupt_current_scene(manager, 0)`
(e.g. in `0x1356a30` and in "unload_scene_safe").

## exp-7

Logs scene changes by name, and on the Skip test key calls `interrupt_current_scene(manager, 0)` once, only
during scenes 3, 5 and 7, only after verifying the function's first 18 bytes. The dump code is no longer
called (and must still be removed before release).

## exp-7 result: the boot intro skip works

- Boot: scene 7 `ship_intro`. One call to `interrupt_current_scene(manager, 0)` ended it on the same frame;
  control returned immediately inside the ship, no crash.
- Joining a ship plays 15 `ship_teleporter_network_join` -> 12 `ship_planet_departure` -> 11
  `ship_planet_arrival` -> 15 again -> **13 `ship_teleporter_arrival`** (the cryo pod sequence, ~11 s).
  exp-7 only allowed 3/5/7, so 13 was left alone. exp-8 adds 13.

## exp-8 result and the two ways to end a scene

Interrupting 13 `ship_teleporter_arrival` 0.4 s in returned control but left the avatar model in the pod
pose, attached to the pod a few metres from the real position (it orbited the player), the pods rolling
forever, and interaction blocked. Why, from the decompiled code:

- `interrupt_current_scene` jumps the scene's state machine (context at manager + 0x60, phase at +0) to an
  **abort** phase via the phase dispatcher `0x117e410(context, scene, phase)`: 7 -> 4, 13 -> 6, 5 -> 5.
- `set_current_scene_to_done` (`0x1295720`, "set_current_scene_to_done: %s", referenced only from a data
  table) jumps to the **done** phase instead: 7 -> 3, 13 -> 5, 5 -> 4, 3 -> 13.
- Scene 13's phase handler (`0x1177b70`): phase 5 fires events 0xd130d731 and 0x44e9d562 and ends the
  scene; phase 6 skips those events. Scene 7's phase 3 queues `ship_bridge_intro`, phase 4 ends it outright,
  which is why interrupt was right for the boot intro.

exp-9 interrupts 3 and 7 and sets 5 and 13 to done.

## exp-9 result: done alone is not enough either

`set_current_scene_to_done` on 13 ended the scene but left the camera stuck and no control (early press:
pods kept rolling, camera froze; press after step-out: cinematic bars vanished, camera followed the rig a bit
longer, then froze). Scene 13's normal flow is 1 -> 2 -> 3 -> 4 -> 5: phase 4 returns camera and control,
phase 5 fires the release events and ends the scene. Jumping to 5 skips 4; interrupt's 6 skips 5.

## exp-10

Scene 13 is stepped through its phases in order, one per frame, via the phase dispatcher
`0x117e410(context = {manager, manager + 0x60}, 13, phase)`, reading the current phase at manager + 0x60
and stopping at phase 5, on a scene change, or if a phase does not advance. 3 and 7 keep using interrupt.
5 (`ship_cryogenic_intro`) is not skipped until observed.

## exp-10 result: the walk-out is physical

Stepping 13 through 2, 3, 4, 5 in four frames ended the scene cleanly (no crash) and returned control, but
with the avatar still inside the pod area, unable to leave and not visible. The avatar's walk-out of the pod
is animation-driven and happens during the normal time between phases, so a full skip would also need to
move the avatar to the exit position (a native teleport of a networked player).

## exp-11

Steps 13 only to phase 3 and lets the scene run on from there (a partial skip of the pod rolling in), and
logs the scene phase with every change so a normal, unskipped run gives the phase timeline.

## Teleport research: the game's own exit points

The ship level loader (`0x65df10`) matches named level objects (`spawn_host_01`, `spawn_returnsuccess_0N`,
`spawn_returnfailure_0N`, `spawn_enter_teleporter_0N`, `spawn_teleporter_hidden_0N`,
**`spawn_exit_teleporter_0N`**, `spawn_armory`, ...) and stores each 4x4 transform (0x40 bytes, position at
+0x30) in a per-ship block of the system at `[0x33265f0]` (Ship Station Hotkeys' "Hellpod system"):
block = `[0x33265f0] + 0x11cd8 + ship * 0x1208`, exits at block + 0xe80 + slot * 0x40. The ship index comes
from a hashed map at system + 0x38 (capacity +0x40, multiplier +0x48) keyed by the ship entity id.

Destination chain for a teleport: the exit point of the player's slot; else the exit point nearest the
avatar; else a fixed offset in front of the pod; else no teleport (partial skip only). Still unknown: how
to move the avatar so the movement system and network accept it (next: the code that consumes these exit
transforms). exp-11 logs the four exit positions and the Helldivers' positions when scene 13 starts/ends.

## exp-11 result: no teleport needed

Natural pod scene (13) timeline: phase 1 (pod rolls in) 2.6 s, phase 2 1.0 s, **phase 3 (walk-out) 7.5 s**,
phases 4-5 a few frames. Exit points read fine: ship block 0 slots at x = 10.41, y = -20.13/-20.13/-21.90/-23.70.

The avatar's body barely moves: it is placed at the exit spot (~11.53, -21.47) by the game a few frames into
phase 3 (it was briefly in the pod area during phase 1). The visible walk-out is only the avatar's cinematic
animation layer 14 (1-based): 36 normal -> 0 in-pod loop at scene start -> 6 walk-out clip (10.62 s) at
phase 3. Stepping to 3 and letting it run left layer 14 on 0: control in the right spot, but the model drawn
relative to the pod (invisible body, gun orbiting). exp-10 stepped through 3 too fast for the placement.

## exp-12

Scene 13: step to 3, hold 30 frames (the game places the body), step 4 and 5, then reset the cinematic
layer of any Helldiver still in the in-pod loop (0) to 36 with `Unit.animation_set_state`, keeping all other
layers' states. No teleport.

## exp-12 result

- Boot: interrupting `ship_intro` skipped the whole `ship_bridge_intro` and with it audio events; the galactic
  map was missing sounds afterwards. Scene phases post audio through `post_audio` (`0x12982d0(_, hash)`):
  ship_intro phase 3 posts 0x41ca6b56 (and queues ship_bridge_intro), ship_bridge_intro phase 9 posts
  0xf70237cb and its done phase 13 posts 0x1110bb89 (and re-shows the menus).
- Pod: body placed correctly and (on the second try) interaction worked, but the Helldiver stayed invisible;
  gun, pistol and cape reappeared separately. The first try's layer reset never ran (the local Helldiver was
  not tracked yet). In the natural sequence the cinematic layer goes to the walk-out clip (6) at phase 3; the
  body is most likely shown by that clip's events, which stepping never triggered.

## exp-13

Boot: after the interrupt, post the audio events the skipped phases would have (7: 0x41ca6b56, 0xf70237cb,
0x1110bb89; 3: 0xf70237cb if before phase 9, then 0x1110bb89). Pod: refresh unit tracking at the press;
at the phase-3 hold start the walk-out clip (layer 14: 0 -> 6); after phase 5 set it to normal (-> 36).

## exp-13 result

- Boot: map sounds all present, but a cryo pod rolling sound played after the skip: 0x41ca6b56 or 0xf70237cb
  is a cutscene sound. The game's own Wwise banks don't contain these hashes as event ids: `post_audio` maps
  them to Wwise ids through a runtime map at `[0x346c9f8]` (buckets, capacity, empty, multiplier, same layout
  as the other game maps; lookup at `0x12556e0`).
- Pod: same as exp-12's second try (right spot, interaction, gun/pistol/cape visible, body invisible).
- The walk-out clip (layer 14 state 6) emits end event 0x5178e781, but game.dll never references that
  hash, so the clip end is not what shows the body.

## Scene 13's update function

`0x1177e80` runs every frame for scene 13 and changes phase itself, doing more than the phase entry
handlers (`0x1177b70`) that stepping called:
- 1 -> 2 when the player list entry reaches state 2 (pod arrived); calls `0x11d13a0(entry, 1, 0)`.
- 2 -> 3 when `[ctx+0x90] + 1.5 s <= now`: sends the scene rig slot 0x60ed8c39 anim event 0x23173e19,
  flow events (0xaa3994d2, 0xdc19bd06) and (0x81320af8, 0x7f35c126), and the avatar anim event 0x23173e19
  (the walk-out clip, state 6), then sets the phase to 3 and `[ctx+0x88] = now`. None of this ran when
  stepping.
- phase 3 calls `0x11cf0a0()` every frame; 3 -> 4 when `[ctx+0x88] + 7.5 s <= now`.
- 4 -> 5 when `[ctx+0x88] + 0x8235 us <= now`.
ctx = manager + 0x60; now = `[[0x3326348] + 0x18]` (u64 microseconds). The timer checks are
`mov rcx,[reg+88h/90h]; add rcx,imm32; cmp [rax+18h],rcx`, with the clock loaded by a rip-relative mov.

## exp-14

Boot: post only the done phase's events (0x616c02e2, 0x1110bb89); log the Wwise ids of all scene audio
events once so they can be looked up in the banks (`_shared/filediver/cmd/wwise_probe`).
Pod: no phase handler calls and no animation changes. A press arms a fast-forward: phase 1 waits for the
pod; in phases 2-4 the timer stamp is moved back to `now - wait` (phase 3 after a 30-frame hold for the
body placement), so the game's own update changes phase with all its events. Verified by the three timer
check signatures and the clock's rip-relative address; a stamp ahead of the clock stops it. Logs layer 14
at the end and 2 s later.

## exp-14 result: both skips work

- Boot: all map sounds present, no pod sound. Wwise ids (via the audio map): 0x41ca6b56 -> 1472490507,
  0xf70237cb -> 3081520204, 0x616c02e2 -> 101254742, 0x1110bb89 -> 756337494, 0x44e9d562 -> 3379619309, all
  in bank `content/audio/cutscenes_sfx`. 0x1110bb89's event is a SetState (the likely cause of the missing
  map sounds); 0x41ca6b56's is a Stop.
- Pod: pressed during phase 1; the fast-forward waited for the pods (2.1 s), moved the timers, and the
  scene ended 30 frames into phase 3. Body visible, correct spot, control and interaction. The Helldiver is
  shown walking out of the pod (layer 14 on 6 at the end, 3 two seconds later): cosmetic, acceptable.

## FTL and lobby join (research for exp-15)

Scene update dispatcher `0x117d830` (per scene, per frame; stamps at ctx+0x88, clock as above):
- 12 ship_planet_departure: 1 -> 2 after 0.25 s; 2 -> 3 at once; 3 -> 4 when 3.38 s (0x33a025) have
  passed AND `0x1294830(_, 11)` (the next scene's resources loaded) AND `0x1295970(manager)` (the 16
  resource slots at manager+0x9ee98 loaded); 4 queues 11.
- 11 ship_planet_arrival: 1 -> 2 at once; 2 -> 3 after 6.4 s (0x61e91a; an audio flag event at 3.67 s,
  checked before the change, so it still fires in the same frame); 3 -> 4 (end) after 0.25 s. Pure timers.
- 15 ship_teleporter_network_join (update `0x1179e30`): 1 -> 2 when loaded (network/resources); 2 -> 3
  after 0.33 s; 3 -> 4 after 5 s (events at 1.6 s and 2.0 s fire first) and loaded; 4 queues 13 in
  teleporter mode.
Observed join chain (exp-7 log): 15 (4.2 s) -> 12 (3.7 s) -> 11 (6.7 s) -> gap 5 s -> 15 (5 s) -> 13.
exp-15 fast-forwards 12 phase 3, 11 phase 2 and 15 phase 3 (loading waits stay), each only if its own
timer instruction matches, and one press follows the chain into later skippable scenes (up to 900
frames between them).

## Boot videos (research for exp-15)

Not Lua (the 10 game Lua files have nothing on video). StateSplash (on_enter `0xadf700`, update
`0xae03c0`, exit `0xae0930`) plays three videos from the table at `0x32938e0` (0x20 each: package, video,
start/stop audio, skippable byte at +0x18): 0 = `packages/generated/videos/video_sie_logo`, 1 = unknown,
2 = `video_arrowhead_logo`; the dump shows all three skippable bytes 0. The update skips a video on input
only if its byte is set, and plays none at all if `0x13f03d0()` says so (sets +0x82; it checks
`[[0x3326348]+0x28]` and a platform setting). The object is registered in the list at `[0x3326e68]`
(+0xa4c count, +0xa50 {object, type 0xb7}). `bink_cs_game_intro` and the setting `WasIntroVideoSeen`
suggest a separate game intro cinematic (first launch?). exp-15 logs the table and the splash object's
video index and flags to find out what the user's "intro cinematic" is and whether the mod runs early
enough to see it.

## exp-15 result

- FTL (host planet move) and joining another host's planet: fast-forwarded as planned, all functional; the
  FTL music keeps playing (fine). Annoyance: a quick black fade in/out showed over the loadout screen.
  Cause: 12 fades to black at phase 1 (`0x11d66c0`, fader at `[0x347cda8]+0x128`: duration +0x784,
  elapsed +0x798, alpha +0x794, start +0x79c, target +0x7a0, hold +0x7a4; `0x11d6760` fades back) and 11
  does again at phase 3; fast-forwarded, both land in half a second, and after the lobby join skip the
  loadout screen is already up when the FTL plays.
- Boot: the splash state jumped straight to "done" ([clock+0x28] = 1: PC skips the logos itself) and was
  gone at 17.6 s. The user's intro ("Super Earth Public Announcement", then the recruitment trailer) ran
  from 24.7 s to 127 s, well after the mod starts (13.7 s).

## Title screen intro videos

StateTitleScreen (on_enter `0xad5950`, update `0xad7cb0`, on_exit `0xad8df0`; registered in the list at
`[0x3326e68]` +0x2590/+0x2598, type 0xb8) owns a video player at +0x81a8 and queues 0x2b1a74c2 then
0xde13da08 (the "title screen video", in the video table at `0x32e5c00`). The key press path: when an
input is seen and title+0x11 is clear, and the player is playing (`0x1795b10`), title+0xa56b set, and
title+0xa541 or `[0x347cdd8]+0x87479`: call `0x1795130(player)` (stops the current video, posts its
stop audio, flips the player's slot). One call per press, so the PSA and the trailer each take one.

## exp-16

Title videos: poll the title object; when the game's own key-press conditions hold, call the skip
function (once per 20 frames), logging each video id. Verified by 7 code checks (functions, the lea of
+0x81a8, the call site, and the flag compares with the global's rip-relative load).
FTL fade: while a fast-forward is in scene 11 or 12, hold the fader clear (duration, alpha, start, target
0). Verified by the fade setter's bytes (its fader load and the alpha/start/target stores).

## exp-16 result and release 1.0.0

- Title videos: not auto-skipped in exp-16; dropped at the user's request (they already skip on any key).
- FTL fade hold: a brief pop instead of the black flash when joining; accepted. Solo moves fine.

Release 1.0.0 (`skip_intro_animation.lua`; the research build is kept as `research/recon_exp16.lua` with
`research/test_recon.py`):
- Arsenal options Log-in ship intro / Cryo pod transition / FTL transition, each Automatic or On Key
  Press. Every choice deploys the script plus an undeclared settings resource
  `mods/alomare/skip_intro_animation_settings/<option>_<choice>`, detected with
  `Application.can_get('lua', name)`; an option switched off leaves its scenes alone.
- Key: spacebar via `stingray.Keyboard` (always), plus the Mod Bindings Menu binding
  `alomare.skip_intro_animation.skip` ("Skip cutscene") when that mod is present (it can't set defaults).
- Signatures (see `research/sig_check.py`) are checked at this build's RVAs first, else searched for in
  4 MB per frame; globals come from rip-relative loads, functions from call sites plus prologue checks,
  and scene ids from the id-to-name jump table (pure reads). Missing pieces disable only what depends on
  them. Status in `Logs/SkipIntroAnimation_STATUS.log` (the loader's open_log only accepts *.log names).
- Chains: a fast-forward follows later skippable scenes within 900 frames, but only into scenes whose
  option is Automatic, or any selected one when it was started by a key press. An automatic skip runs
  once per scene instance.
- Tests: `tests/test_release.py` maps the real dump as process memory (32 checks, mutation-tested).

## 1.0.0 crash report: game crashes after the hellpod descent

Users (and the user, with all skips on Automatic) crash a few seconds into the descent, during loading,
after a strange camera angle in the ship while the hellpods fire. That session: log-in intro skipped, a
solo planet move (FTL fast-forwarded), then a drop; the mod did nothing during the launch itself (its
fast-forward chain had timed out before). The minidump shows a null write in helldivers2.exe+0x5f5c33 on
an engine thread with no game.dll frames.
Lead: 1.0.0 held the screen fader (`[0x347cda8]+0x128`) clear during the FTL scenes (added in exp-16), and
scene 6 ship_hellpod_launch uses that fader: after 10 s in phase 2 it sets alpha 1 with a 3 s hold
(`+0x7a4`), which brings up the loading screen. exp-15 (no fader writes) dropped fine after an FTL.
Second suspect: finishing a host's own planet move early (exp-15's successful drop followed a lobby join).
1.0.1: no fader writes at all, and each scene change is logged with its time.

## Crash cause found: the log-in intro interrupt

Test: FTL off, other skips on, a drop without moving planets: crash. Mod disabled: no crash. The mod's only
action that session was interrupting ship_intro, so the crash comes from the interrupt's abort path
(ship_intro phase 4), which skips the whole ship_bridge_intro and its done phase (13); that phase resets
cutscene manager state (+0x193c, +0x2418/+0x241c/+0x2420, the camera blends at +0x1c88/+0x1da0/+0x1eb8) that
the hellpod launch then relies on (the odd camera while the hellpods fire, then the crash).

Version 2 (recon 1, versions are plain integers from now on): the log-in intro is a fast-forward like the
others. ship_intro (dispatcher case 7) waits 3 s in phase 1 (plus a loading flag) and 0.33 s in phase 2;
ship_bridge_intro's update (`0x116d7a0`) moves phases 2-12 on timers of 1-2.5 s at ctx+0x88, ending in
its own done phase 13 (which also posts the audio the menus need, so nothing is posted by the mod). The
interrupt and post_audio are no longer used. The FTL fade hold is back (not involved in the crash).

## Version 3: settings in Mod Options Menu

The Arsenal options and settings resources are gone (one `Addon` option). Each skip is a Mod Options Menu
choice `alomare.skip_intro_animation.<login|pod|ftl>` (Off / Manual / Automatic, default Automatic) under the
category "Impatient Diver". Without the menu (or if an option fails to register) the skips are Automatic.
- The menu is looked for every frame until found (the two addons load in either order); applied changes
  arrive through `on_change` and take effect at once, rewriting the status file.
- Native resolution starts the first time any skip is on, so with all three Off the mod never reads game
  memory. Resolved scenes stay mapped for every feature; the mode is checked when a skip would start and in
  each fast-forward step (Off stops it).
- Status file line 3 says where the settings come from.

## Version 4: stricter search after game updates

- The fallback search now covers only game.dll's executable sections, collects every match (a match starting in a
  chunk's overlap is counted once) and accepts a signature only when it matches exactly once; otherwise that skip
  is off and plays normally. (Version 3 took the first match in the whole image.) Test 5d: a signature copied to two
  places is ignored.
