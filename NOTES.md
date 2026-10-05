# Skip Intro Animation: investigation notes

Game build 25480438. Unit names are resource hashes; "S<n>" is a 0-based state index in that unit's animation state machine (dumps via `_shared/filediver/cmd/cryo_probe`).

## The two sequences

- **Boot intro** (camera outside the ship, then the Helldiver walks to the centre). The exterior shot is a separate cinematic world: destroyer exterior guns plus camera rigs `3babe3b5c727bf7b` (S46, 3.3 s) and `bb3881db2f8d8164`. The ship interior loads in parallel. During the walk the local Helldiver plays cinematic-layer states (layer 14, 1-based: S36 -> S18 -> S3). The cinematic world's remaining units are destroyed on the frame control returns.
- **Cryo pod** (after the tutorial, or being sent back to the ship). The pod `33cb06b89be208da` and rig `3babe…` spawn when it starts and are destroyed when it ends:

  | Time from pod spawn | Event | Length |
  |---|---|---|
  | 0 s | pod S0 (closed); rig S55 | S55 = 9.98 s |
  | ~3.2 s | game sends "open": pod S1 `cryo_exit_pod`, chamber S1 `ready_open`, rig S54 | 7.33 s / 9.25 s / 8.33 s |
  | ~10.5 s | pod S1 ends (`cryo_exit_done` -> S0); scene ends | |

## What is known

- Neither sequence is a UI screen (screen stack and presenter stay idle), unlike the briefing intro that Ship Station Hotkeys skips by zeroing a timer.
- The camera is attached to the rig: putting the rig into its Empty state freezes the camera, but the sequence carries on and control returns at the normal time (exp-1). The game's own code drives the timeline.
- There is no world time scale, and `AnimationBlenderComponent.set_speed/set_time` only affect crossfade animations, not state-machine states.
- `Unit.animation_layer_info(unit, layer)` returns (time in state, state length); layers are 1-based and layer 0 crashed the game.
- Animation events only act when the state they leave from is current (exp-1 fired `cryo_exit_done` on a closed pod and nothing happened).

## Animation-level results

- exp-1: putting the camera rig into its Empty state freezes the camera; the sequence keeps its timing.
- exp-2: advancing the pod along its own transitions only changes visuals. `cryo_exit` from S0 sent the pod forward empty (the player is placed in the pod separately); `cryo_exit_done` from S1 made the pod vanish. The scene kept its normal timing either time. **Animation events cannot skip the sequence.**

## Native results

- exp-3: the local avatar's seater record stays empty through both sequences: **the cryo pod is not a seat.** The avatar exists before either sequence starts (boot: just after the exterior shot begins).

## Snapshot method (exp-4)

Read-only snapshots, every 15 frames during a sequence and on each mark, of the local avatar's native state (layout from Consistent Vaulting, build 25480438), written to `SkipIntroAnimation_snaps.log`:

| Region | Address | Size |
|---|---|---|
| players | `[0x3326468]` | 0x1000 |
| mode | `[0x33266a0]` (mission mode; +0x40 mission type) | 0x80 |
| avatar_record | `[0x3326d20] + 0x53e134 + ai*0x1238` | 0x1238 |
| avatar_input | `[0x3326d20] + 0x150 + ai*0xa7aec` (input state) | 0x2000 |
| move / mover | `[[0x3326558]+0x48c8] + mi*132`, `[[0x3326558]+0x48d0] + mi*164` | 132 / 164 |

`ai` is the avatar's index from the map at `[0x3326d20]+0xf8`; `mi` from `[0x3326558]+0x48a0`. The offline diff looks for fields that count down during a sequence or flip at its start and end.

## exp-4 result: the hold flags

Diffing the snapshots (middle of each sequence against well after control returns) found exactly two fields that behave the same in both sequences, both in the avatar record (`[0x3326d20] + 0x53e134 + ai*0x1238`):

| Offset | During either sequence | With control |
|---|---|---|
| +0x750 (second word of the flags block at +0x74c) | 0x40000000 | 0 |
| +0x7e4 (float) | 1.0 | 0.0 |

+0x758 also holds 0x800 during both. All of them are set before the sequence is visible and clear on the frame control returns (boot: between f1680 and f1691, the "control" mark was f1691; cryo: f5595, mark f5616).

## Current lead (exp-5)

First memory writes, only on the Skip test key, only while the hold bit is set and the record's identity (+0x28 == avatar id) matches, through WriteProcessMemory. Press 1 clears the hold bit; press 2 also clears the 0x800 bit and the weight; press 3 keeps all three cleared for 3 seconds. Each write is followed by a second of logged readback, to show whether the game sets them again.

## exp-5 result: the hold flags are a mirror, not the lock

Clearing +0x750's hold bit (and +0x758's 0x800 bit and the +0x7e4 weight) stuck: the game did not set the hold bit again, and only re-set 0x800 about 55 frames later. But nothing changed on screen and control returned at the normal time in both sequences. The fields record that the avatar is held; the lock itself is owned by other native state that does not re-read them.

## Static analysis

The rest of this research used an offline copy of game.dll's code for build 25480438 (not included). Addresses below are RVAs in game.dll; "Ghidra session" addresses use base 0x7ffcea020000.

- The avatar flags are a 192-bit bitset at avatar manager + 0x53e880 + ai*0x1238 (24 bytes). The "hold bit" 0x40000000 at record +0x750 is **bit 62** of the first qword.
- Gameplay code tests bit 62 alongside others, e.g. `0xa5b93b` tests 0x4000000000010000 (bits 16 and 62) against the first qword and branches if either is set; masks are also built with `bts r, 0x1e` on the second half (0x127efbc, 0x1288a56, 0x128adab, 0x128bc97).
- Almost nothing writes the block inline (one `mov dword [rcx+0x53e880], ecx` at 0xa6c6ac), and no "load 62, call helper" pattern exists near its references. The block is written through computed pointers or whole-record copies (plausibly network replication), which needs a decompiler with cross-references (Ghidra) to trace.

## Ghidra: the cutscene system

Decompiling the cutscene code traced the hold bit: avatar flags change through a notifier `0x7ffceaa5f220(component, mask, set)`; generic setter `0x7ffceaac0d60(mask)` is called with mask 0x4000000000000000 by three functions, which belong to the game's **cutscene system** (debug strings "Cutscene", "play_scene: %s", "interrupt_current_scene: %s"):

| RVA (session base 0x7ffcea020000) | What |
|---|---|
| `[0x346d530]` | cutscene manager; +0x1908 previous, +0x190c current, +0x1910 queued scene id |
| `0x12948b0` | `play_scene(manager, id)`: starts a scene, sets the avatar hold bit |
| `0x12954d0` | `interrupt_current_scene(manager, force)`: runs the scene's cleanup handler |
| `0x117e950` | scene id to name |
| `0xaa0960` | avatar flag setup: sets the hold bit if a scene is playing |

Scene ids: 1 mission_extraction, 2 ship_bridge_hellpod_launch, **3 ship_bridge_intro**, 4 ship_clan_station_reveal, **5 ship_cryogenic_intro**, 6 ship_hellpod_launch, **7 ship_intro**, 8 ship_mission_return_failure, 9 ship_mission_return_success, 10 ship_name_resource_loading, 11 ship_planet_arrival, 12 ship_planet_departure, 13 ship_teleporter_arrival, 14 ship_teleporter_deeplink_join, 15 ship_teleporter_network_join, 16 tutorial_avatar_respawn, 17 tutorial_cape_ceremony, 18 tutorial_intro, 19 tutorial_outro, 20 tutorial_outro_to_ship.

The game interrupts scenes itself with `if (current != 0) interrupt_current_scene(manager, 0)` (e.g. in `0x1356a30` and in "unload_scene_safe").

## exp-7

Logs scene changes by name, and on the Skip test key calls `interrupt_current_scene(manager, 0)` once, only during scenes 3, 5 and 7, only after verifying the function's first 18 bytes. The dump code is no longer called (and must still be removed before release).

## exp-7 result: the boot intro skip works

- Boot: scene 7 `ship_intro`. One call to `interrupt_current_scene(manager, 0)` ended it on the same frame; control returned immediately inside the ship, no crash.
- Joining a ship plays 15 `ship_teleporter_network_join` -> 12 `ship_planet_departure` -> 11 `ship_planet_arrival` -> 15 again -> **13 `ship_teleporter_arrival`** (the cryo pod sequence, ~11 s). exp-7 only allowed 3/5/7, so 13 was left alone. exp-8 adds 13.

## exp-8 result and the two ways to end a scene

Interrupting 13 `ship_teleporter_arrival` 0.4 s in returned control but left the avatar model in the pod pose, attached to the pod a few metres from the real position (it orbited the player), the pods rolling forever, and interaction blocked. Why, from the decompiled code:

- `interrupt_current_scene` jumps the scene's state machine (context at manager + 0x60, phase at +0) to an **abort** phase via the phase dispatcher `0x117e410(context, scene, phase)`: 7 -> 4, 13 -> 6, 5 -> 5.
- `set_current_scene_to_done` (`0x1295720`, "set_current_scene_to_done: %s", referenced only from a data table) jumps to the **done** phase instead: 7 -> 3, 13 -> 5, 5 -> 4, 3 -> 13.
- Scene 13's phase handler (`0x1177b70`): phase 5 fires events 0xd130d731 and 0x44e9d562 and ends the scene; phase 6 skips those events. Scene 7's phase 3 queues `ship_bridge_intro`, phase 4 ends it outright, which is why interrupt was right for the boot intro.

exp-9 interrupts 3 and 7 and sets 5 and 13 to done.

## exp-9 result: done alone is not enough either

`set_current_scene_to_done` on 13 ended the scene but left the camera stuck and no control (early press: pods kept rolling, camera froze; press after step-out: cinematic bars vanished, camera followed the rig a bit longer, then froze). Scene 13's normal flow is 1 -> 2 -> 3 -> 4 -> 5: phase 4 returns camera and control, phase 5 fires the release events and ends the scene. Jumping to 5 skips 4; interrupt's 6 skips 5.

## exp-10

Scene 13 is stepped through its phases in order, one per frame, via the phase dispatcher `0x117e410(context = {manager, manager + 0x60}, 13, phase)`, reading the current phase at manager + 0x60 and stopping at phase 5, on a scene change, or if a phase does not advance. 3 and 7 keep using interrupt. 5 (`ship_cryogenic_intro`) is not skipped until observed.

## exp-10 result: the walk-out is physical

Stepping 13 through 2, 3, 4, 5 in four frames ended the scene cleanly (no crash) and returned control, but with the avatar still inside the pod area, unable to leave and not visible. The avatar's walk-out of the pod is animation-driven and happens during the normal time between phases, so a full skip would also need to move the avatar to the exit position (a native teleport of a networked player).

## exp-11

Steps 13 only to phase 3 and lets the scene run on from there (a partial skip of the pod rolling in), and logs the scene phase with every change so a normal, unskipped run gives the phase timeline.

## Teleport research: the game's own exit points

The ship level loader (`0x65df10`) matches named level objects (`spawn_host_01`, `spawn_returnsuccess_0N`, `spawn_returnfailure_0N`, `spawn_enter_teleporter_0N`, `spawn_teleporter_hidden_0N`, **`spawn_exit_teleporter_0N`**, `spawn_armory`, ...) and stores each 4x4 transform (0x40 bytes, position at +0x30) in a per-ship block of the system at `[0x33265f0]` (Ship Station Hotkeys' "Hellpod system"): block = `[0x33265f0] + 0x11cd8 + ship * 0x1208`, exits at block + 0xe80 + slot * 0x40. The ship index comes from a hashed map at system + 0x38 (capacity +0x40, multiplier +0x48) keyed by the ship entity id.

Destination chain for a teleport: the exit point of the player's slot; else the exit point nearest the avatar; else a fixed offset in front of the pod; else no teleport (partial skip only). Still unknown: how to move the avatar so the movement system and network accept it (next: the code that consumes these exit transforms). exp-11 logs the four exit positions and the Helldivers' positions when scene 13 starts/ends.

## exp-11 result: no teleport needed

Natural pod scene (13) timeline: phase 1 (pod rolls in) 2.6 s, phase 2 1.0 s, **phase 3 (walk-out) 7.5 s**, phases 4-5 a few frames. Exit points read fine: ship block 0 slots at x = 10.41, y = -20.13/-20.13/-21.90/-23.70.

The avatar's body barely moves: it is placed at the exit spot (~11.53, -21.47) by the game a few frames into phase 3 (it was briefly in the pod area during phase 1). The visible walk-out is only the avatar's cinematic animation layer 14 (1-based): 36 normal -> 0 in-pod loop at scene start -> 6 walk-out clip (10.62 s) at phase 3. Stepping to 3 and letting it run left layer 14 on 0: control in the right spot, but the model drawn relative to the pod (invisible body, gun orbiting). exp-10 stepped through 3 too fast for the placement.

## exp-12

Scene 13: step to 3, hold 30 frames (the game places the body), step 4 and 5, then reset the cinematic layer of any Helldiver still in the in-pod loop (0) to 36 with `Unit.animation_set_state`, keeping all other layers' states. No teleport.

## exp-12 result

- Boot: interrupting `ship_intro` skipped the whole `ship_bridge_intro` and with it audio events; the galactic map was missing sounds afterwards. Scene phases post audio through `post_audio` (`0x12982d0(_, hash)`): ship_intro phase 3 posts 0x41ca6b56 (and queues ship_bridge_intro), ship_bridge_intro phase 9 posts 0xf70237cb and its done phase 13 posts 0x1110bb89 (and re-shows the menus).
- Pod: body placed correctly and (on the second try) interaction worked, but the Helldiver stayed invisible; gun, pistol and cape reappeared separately. The first try's layer reset never ran (the local Helldiver was not tracked yet). In the natural sequence the cinematic layer goes to the walk-out clip (6) at phase 3; the body is most likely shown by that clip's events, which stepping never triggered.

## exp-13

Boot: after the interrupt, post the audio events the skipped phases would have (7: 0x41ca6b56, 0xf70237cb, 0x1110bb89; 3: 0xf70237cb if before phase 9, then 0x1110bb89). Pod: refresh unit tracking at the press; at the phase-3 hold start the walk-out clip (layer 14: 0 -> 6); after phase 5 set it to normal (-> 36).

## exp-13 result

- Boot: map sounds all present, but a cryo pod rolling sound played after the skip: 0x41ca6b56 or 0xf70237cb is a cutscene sound. The game's own Wwise banks don't contain these hashes as event ids: `post_audio` maps them to Wwise ids through a runtime map at `[0x346c9f8]` (buckets, capacity, empty, multiplier, same layout as the other game maps; lookup at `0x12556e0`).
- Pod: same as exp-12's second try (right spot, interaction, gun/pistol/cape visible, body invisible).
- The walk-out clip (layer 14 state 6) emits end event 0x5178e781, but game.dll never references that hash, so the clip end is not what shows the body.

## Scene 13's update function

`0x1177e80` runs every frame for scene 13 and changes phase itself, doing more than the phase entry handlers (`0x1177b70`) that stepping called:
- 1 -> 2 when the player list entry reaches state 2 (pod arrived); calls `0x11d13a0(entry, 1, 0)`.
- 2 -> 3 when `[ctx+0x90] + 1.5 s <= now`: sends the scene rig slot 0x60ed8c39 anim event 0x23173e19, flow events (0xaa3994d2, 0xdc19bd06) and (0x81320af8, 0x7f35c126), and the avatar anim event 0x23173e19 (the walk-out clip, state 6), then sets the phase to 3 and `[ctx+0x88] = now`. None of this ran when stepping.
- phase 3 calls `0x11cf0a0()` every frame; 3 -> 4 when `[ctx+0x88] + 7.5 s <= now`.
- 4 -> 5 when `[ctx+0x88] + 0x8235 us <= now`. ctx = manager + 0x60; now = `[[0x3326348] + 0x18]` (u64 microseconds). The timer checks are `mov rcx,[reg+88h/90h]; add rcx,imm32; cmp [rax+18h],rcx`, with the clock loaded by a rip-relative mov.

## exp-14

Boot: post only the done phase's events (0x616c02e2, 0x1110bb89); log the Wwise ids of all scene audio events once so they can be looked up in the banks (`_shared/filediver/cmd/wwise_probe`). Pod: no phase handler calls and no animation changes. A press arms a fast-forward: phase 1 waits for the pod; in phases 2-4 the timer stamp is moved back to `now - wait` (phase 3 after a 30-frame hold for the body placement), so the game's own update changes phase with all its events. Verified by the three timer check signatures and the clock's rip-relative address; a stamp ahead of the clock stops it. Logs layer 14 at the end and 2 s later.

## exp-14 result: both skips work

- Boot: all map sounds present, no pod sound. Wwise ids (via the audio map): 0x41ca6b56 -> 1472490507, 0xf70237cb -> 3081520204, 0x616c02e2 -> 101254742, 0x1110bb89 -> 756337494, 0x44e9d562 -> 3379619309, all in bank `content/audio/cutscenes_sfx`. 0x1110bb89's event is a SetState (the likely cause of the missing map sounds); 0x41ca6b56's is a Stop.
- Pod: pressed during phase 1; the fast-forward waited for the pods (2.1 s), moved the timers, and the scene ended 30 frames into phase 3. Body visible, correct spot, control and interaction. The Helldiver is shown walking out of the pod (layer 14 on 6 at the end, 3 two seconds later): cosmetic, acceptable.

## FTL and lobby join (research for exp-15)

Scene update dispatcher `0x117d830` (per scene, per frame; stamps at ctx+0x88, clock as above):
- 12 ship_planet_departure: 1 -> 2 after 0.25 s; 2 -> 3 at once; 3 -> 4 when 3.38 s (0x33a025) have passed AND `0x1294830(_, 11)` (the next scene's resources loaded) AND `0x1295970(manager)` (the 16 resource slots at manager+0x9ee98 loaded); 4 queues 11.
- 11 ship_planet_arrival: 1 -> 2 at once; 2 -> 3 after 6.4 s (0x61e91a; an audio flag event at 3.67 s, checked before the change, so it still fires in the same frame); 3 -> 4 (end) after 0.25 s. Pure timers.
- 15 ship_teleporter_network_join (update `0x1179e30`): 1 -> 2 when loaded (network/resources); 2 -> 3 after 0.33 s; 3 -> 4 after 5 s (events at 1.6 s and 2.0 s fire first) and loaded; 4 queues 13 in teleporter mode. Observed join chain (exp-7 log): 15 (4.2 s) -> 12 (3.7 s) -> 11 (6.7 s) -> gap 5 s -> 15 (5 s) -> 13. exp-15 fast-forwards 12 phase 3, 11 phase 2 and 15 phase 3 (loading waits stay), each only if its own timer instruction matches, and one press follows the chain into later skippable scenes (up to 900 frames between them).

## Boot videos (research for exp-15)

Not Lua (the 10 game Lua files have nothing on video). StateSplash (on_enter `0xadf700`, update `0xae03c0`, exit `0xae0930`) plays three videos from the table at `0x32938e0` (0x20 each: package, video, start/stop audio, skippable byte at +0x18): 0 = `packages/generated/videos/video_sie_logo`, 1 = unknown, 2 = `video_arrowhead_logo`; the dump shows all three skippable bytes 0. The update skips a video on input only if its byte is set, and plays none at all if `0x13f03d0()` says so (sets +0x82; it checks `[[0x3326348]+0x28]` and a platform setting). The object is registered in the list at `[0x3326e68]` (+0xa4c count, +0xa50 {object, type 0xb7}). `bink_cs_game_intro` and the setting `WasIntroVideoSeen` suggest a separate game intro cinematic (first launch?). exp-15 logs the table and the splash object's video index and flags to find out what the user's "intro cinematic" is and whether the mod runs early enough to see it.

## exp-15 result

- FTL (host planet move) and joining another host's planet: fast-forwarded as planned, all functional; the FTL music keeps playing (fine). Annoyance: a quick black fade in/out showed over the loadout screen. Cause: 12 fades to black at phase 1 (`0x11d66c0`, fader at `[0x347cda8]+0x128`: duration +0x784, elapsed +0x798, alpha +0x794, start +0x79c, target +0x7a0, hold +0x7a4; `0x11d6760` fades back) and 11 does again at phase 3; fast-forwarded, both land in half a second, and after the lobby join skip the loadout screen is already up when the FTL plays.
- Boot: the splash state jumped straight to "done" ([clock+0x28] = 1: PC skips the logos itself) and was gone at 17.6 s. The user's intro ("Super Earth Public Announcement", then the recruitment trailer) ran from 24.7 s to 127 s, well after the mod starts (13.7 s).

## Title screen intro videos

StateTitleScreen (on_enter `0xad5950`, update `0xad7cb0`, on_exit `0xad8df0`; registered in the list at `[0x3326e68]` +0x2590/+0x2598, type 0xb8) owns a video player at +0x81a8 and queues 0x2b1a74c2 then 0xde13da08 (the "title screen video", in the video table at `0x32e5c00`). The key press path: when an input is seen and title+0x11 is clear, and the player is playing (`0x1795b10`), title+0xa56b set, and title+0xa541 or `[0x347cdd8]+0x87479`: call `0x1795130(player)` (stops the current video, posts its stop audio, flips the player's slot). One call per press, so the PSA and the trailer each take one.

## exp-16

Title videos: poll the title object; when the game's own key-press conditions hold, call the skip function (once per 20 frames), logging each video id. Verified by 7 code checks (functions, the lea of +0x81a8, the call site, and the flag compares with the global's rip-relative load). FTL fade: while a fast-forward is in scene 11 or 12, hold the fader clear (duration, alpha, start, target 0). Verified by the fade setter's bytes (its fader load and the alpha/start/target stores).

## exp-16 result and release 1.0.0

- Title videos: not auto-skipped in exp-16; dropped at the user's request (they already skip on any key).
- FTL fade hold: a brief pop instead of the black flash when joining; accepted. Solo moves fine.

Release 1.0.0 (`skip_intro_animation.lua`; the research build is kept as `research/recon_exp16.lua` with `research/test_recon.py`):
- Arsenal options Log-in ship intro / Cryo pod transition / FTL transition, each Automatic or On Key Press. Every choice deploys the script plus an undeclared settings resource `mods/alomare/skip_intro_animation_settings/<option>_<choice>`, detected with `Application.can_get('lua', name)`; an option switched off leaves its scenes alone.
- Key: spacebar via `stingray.Keyboard` (always), plus the Mod Bindings Menu binding `alomare.skip_intro_animation.skip` ("Skip cutscene") when that mod is present (it can't set defaults).
- Signatures (see `research/sig_check.py`) are checked at this build's RVAs first, else searched for in 4 MB per frame; globals come from rip-relative loads, functions from call sites plus prologue checks, and scene ids from the id-to-name jump table (pure reads). Missing pieces disable only what depends on them. Status in `Logs/SkipIntroAnimation_STATUS.log` (the loader's open_log only accepts *.log names).
- Chains: a fast-forward follows later skippable scenes within 900 frames, but only into scenes whose option is Automatic, or any selected one when it was started by a key press. An automatic skip runs once per scene instance.
- Tests: `tests/test_release.py` maps the real dump as process memory (32 checks, mutation-tested).

## 1.0.0 crash report: game crashes after the hellpod descent

Users (and the user, with all skips on Automatic) crash a few seconds into the descent, during loading, after a strange camera angle in the ship while the hellpods fire. That session: log-in intro skipped, a solo planet move (FTL fast-forwarded), then a drop; the mod did nothing during the launch itself (its fast-forward chain had timed out before). The minidump shows a null write in helldivers2.exe+0x5f5c33 on an engine thread with no game.dll frames. Lead: 1.0.0 held the screen fader (`[0x347cda8]+0x128`) clear during the FTL scenes (added in exp-16), and scene 6 ship_hellpod_launch uses that fader: after 10 s in phase 2 it sets alpha 1 with a 3 s hold (`+0x7a4`), which brings up the loading screen. exp-15 (no fader writes) dropped fine after an FTL. Second suspect: finishing a host's own planet move early (exp-15's successful drop followed a lobby join). 1.0.1: no fader writes at all, and each scene change is logged with its time.

## Crash cause found: the log-in intro interrupt

Test: FTL off, other skips on, a drop without moving planets: crash. Mod disabled: no crash. The mod's only action that session was interrupting ship_intro, so the crash comes from the interrupt's abort path (ship_intro phase 4), which skips the whole ship_bridge_intro and its done phase (13); that phase resets cutscene manager state (+0x193c, +0x2418/+0x241c/+0x2420, the camera blends at +0x1c88/+0x1da0/+0x1eb8) that the hellpod launch then relies on (the odd camera while the hellpods fire, then the crash).

Version 2 (recon 1, versions are plain integers from now on): the log-in intro is a fast-forward like the others. ship_intro (dispatcher case 7) waits 3 s in phase 1 (plus a loading flag) and 0.33 s in phase 2; ship_bridge_intro's update (`0x116d7a0`) moves phases 2-12 on timers of 1-2.5 s at ctx+0x88, ending in its own done phase 13 (which also posts the audio the menus need, so nothing is posted by the mod). The interrupt and post_audio are no longer used. The FTL fade hold is back (not involved in the crash).

## Version 3: settings in Mod Options Menu

The Arsenal options and settings resources are gone (one `Addon` option). Each skip is a Mod Options Menu choice `alomare.skip_intro_animation.<login|pod|ftl>` (Off / Manual / Automatic, default Automatic) under the category "Impatient Diver". Without the menu (or if an option fails to register) the skips are Automatic.
- The menu is looked for every frame until found (the two addons load in either order); applied changes arrive through `on_change` and take effect at once, rewriting the status file.
- Native resolution starts the first time any skip is on, so with all three Off the mod never reads game memory. Resolved scenes stay mapped for every feature; the mode is checked when a skip would start and in each fast-forward step (Off stops it).
- Status file line 3 says where the settings come from.

## Version 4: stricter search after game updates

- The fallback search now covers only game.dll's executable sections, collects every match (a match starting in a chunk's overlap is counted once) and accepts a signature only when it matches exactly once; otherwise that skip is off and plays normally. (Version 3 took the first match in the whole image.) Test 5d: a signature copied to two places is ignored.

## Version 5 (recon 1): galactic map quick exit, signatures from one block, translations

Galactic map (offline, Ghidra on the dump):
- The map is menu presenter 15 (Hologram, view model `ui.MenuHologram`). The presenter manager is `[0x347ce28] + 0x4288` (GalacticMenuHotkey's): current presenter `+0xc`, stack of presenter ids `+0x14`, depth `+0x28`. `open(manager, id, data)` 0x14c0350 closes the current one first through `close_current(manager)` 0x14c0900, which runs the presenter's exit (0x14b5f20: for 15, `pop_screen(24)` = the Hologram screen, then the view teardown) and resumes the previous presenter.
- `PresenterManager::update` 0x14bf750 walks the stack and closes every presenter whose close request is set: `check(manager + 0xd8, id)` 0x14bdc20 is a switch whose case 15 reads `[collection + 0x98] + 0x10` (the 0x18-byte object the presenter creation 0x14b7b60 allocates, flag cleared there). The mod sets that byte on an Escape press while presenter 15 is current: the game closes the map itself that frame, from any zoom level.
- Escape is the engine's keyboard button ("esc", else "escape"), else GetAsyncKeyState while the game has focus. The press that was down when the map opened doesn't count.
- Signatures: "is the briefing presenter open" 0x662520 (UI global, +0x4288, depth, stack), open's close call 0x14c038e (current +0xc, close), the update's check call 0x14bf890 (collection +0xd8, check, close) and check's cases 14-16 0x14bdcbb (Hologram slot +0x98, flag +0x10); the Hologram case must lie inside the check the update calls.

Signatures: `research/signatures.py` generates every signature (and the shared engine, `tools/sigscan.lua`) into the script. Timer checks now read their stamp offset and wait from the code (fields `<sig>_stamp` / `<sig>_wait`), with spans widened until the wildcarded pattern is unique (`tools/spanfind.py`); the scene name switch keeps its decoy check as an engine validator. `research/sig_check.py` (the v1 checker) is replaced by `signatures.py --check`.

Translations: `locales/en.lua` + `locales/pt-BR.lua`, resolved by bingus_text (`src/bingus_text.lua`, assembled ahead of the script by `tools/entry.py`); Mod Options Menu v1.1 gets option texts as functions, Mod Bindings Menu v2.1 the binding's. OFF stays a plain string (the menu shows the game's own word).

## Hellpod launch and mission return (research for 5-recon-1, offline)

Ghidra on the dump (`_research/launch.c`, `extract_return*.c`, `presenter_create.c`). Presenter ids, from the names table the presenter manager prints (`0x21dc810`): 1 Main, 2 LoadingMission, 3 LoadingShip, 5 Armory, 13 **MissionEnd** (`ui.MenuMissionEnd`, the stats screen), 14 Loadout, 15 Hologram, 23 **MissionSummary** (`ui.MenuMissionSummary`), 24 Load, 25 Join. The game state is `[0x3326340] + 0xac21c` (3 on the ship, 4 in a mission, from the scene checks).

Hellpod launch (todo 2a):
- 2 ship_bridge_hellpod_launch (update `0x116b640`): phase 1 waits for no open menu and hellpods (`[0x33265f0]+0x20`); phases 2, 3, 4 send each slot (0, 3, 2, 1) the enter-pod animation event 0x514 (`0x11ce740`) 1/3 s and 1/6 s apart (stamp +0x90); phase 5 waits until 7 s after the scene started (+0x88); phase 6 queues ship_hellpod_launch.
- 6 ship_hellpod_launch (update `0x1171be0`): phase 1 3.33 s (camera setup at 1 s); phase 2 waits 10 s **and** `0x11d5b10` (game state 4 and the players' mission state), then fades to black with a 3 s hold (the loading screen); phase 3 ends the scene. The wait for the mission is never skipped, so a client can't get ahead of the host.
- The drop-location screen comes after the mission loads; no cutscene scene runs in the mission before it (scene ids have none), so whatever plays there is still unmapped (the recon's presenter/state timeline should show it).

Mission return (todo 2b):
- 1 mission_extraction (dispatcher `0x117d830` case 1; entry `0x1169530` sets up the exterior rig 0xbb3881db2f8d8164 per player): phase 1 1 s, then opens MissionSummary (23); phase 2 waits until it closes; phase 3 6.67 s, then a fade (`0x11d66c0`); phase 4 (`0x1169eb0`) waits for game state 3 (the ship loaded) and up to 1 s for other players' flags (players table + 0x3ac, bits 9/10); phase 5 1/6 s; phase 6 queues 9 (success) or 8 (failure).
- 9 ship_mission_return_success (update `0x1173e30`): phase 1 5.83 s (the elevator: events at 0.5, 2 and 5 s); phase 2 6.67 s, or at once when input action 0x900000000 is down (the game's own skip input, `[0x349cf18] + 0x328`); then opens MissionEnd (13); phase 3 waits 0.83 s and until MissionEnd closes; phase 4 returns control.
- 8 ship_mission_return_failure: phase 1 1.67 s, opens MissionEnd, waits until it closes; phase 2 returns control.
- Menus close through the presenter manager's per-menu close request (the check `0x14bdc20` the update calls): MissionEnd's is the first byte of `[collection + 0x88]`, MissionSummary's of `[collection + 0xd8]` (collection = presenter manager + 0xd8), each a 1-byte object the presenter creation (`0x14b7b60`) allocates and clears; their view models (`0x15be0a0`, `0x15c17a0`) set it when the player continues. The order the user sees (liftoff, elevator, stats) suggests MissionSummary is the overlay during the Pelican ride.

5-recon-1 (rebuilt, still untested; same version as the map-exit build):
- Two experimental options, Manual by default: **Hellpod launch** (2 phases 2-5, 6 phases 1-2) and **Mission return** (1 phases 1, 3, 5 and MissionSummary; 9 phases 1-3 and MissionEnd; 8 phase 1 and MissionEnd). Timers are warped as before; a `close` step sets the menu's own close request once it has been the current presenter for 30 frames.
- Timeouts are now per phase and only in phases with a step, so a long load (scene 1 phase 4, the join chain) no longer ends a fast-forward.
- Research timeline (`RESEARCH`, reads only; remove before release): every scene phase, presenter stack and game state change with the scene clock, the open menu's close request, and skip key presses, in `ImpatientDiver.log`.
- Questions for the test: what each phase shows; whether MissionSummary is the Pelican ride overlay and closes on its own; whether closing MissionEnd early is clean (rewards still granted, the ship usable); whether the launch skip is safe in a squad (the host and the other players).

## 5-recon-1 results (2026-10-04)

- Galactic map quick exit: works from every level. The user asked for a Mod Bindings Menu key as well (gamepad players), Escape staying the base key, and no toggle.
- Hellpod launch (scenes 2 and 6): the skip works but saves only 2-4 s (log: launch to mission about 11-15 s either way), because ship_hellpod_launch phase 2 waits for the mission to load. And it is not what the user meant by todo 2a: they want the Helldiver entering the hellpod up to the drop location screen skipped, and everything after the loadout untouched. In two of the four runs ship_bridge_hellpod_launch went 1 -> 2 -> none in two frames by itself.
- Mission return: closing MissionSummary early (as host or client) only shows a black loading screen for the rest of the summary's time, and once the game stayed stuck on it. The extraction part is dropped; the elevator (scene 9) stays skippable. Spacebar is also the jump key, so a press made while jumping at extraction started a skip by accident (log f54653).

## 5-recon-2: hellpod entry, map key, shorter mission return

Hellpod entry (offline; `_research/seat_instant.c`, `seat_enter.c`, `seat_complete.c`, GalacticMenuHotkey's Hellpod shortcut):
- Entering the hellpod is an interaction that starts a seat transition (`set_entering` 0x63a7b0, "seater.%u.entering"; GalacticMenuHotkey: 3.13 s). Seater component `[0x3326d78]`: map of entity id -> record at +0x20 (capacity +0x28, empty +0x2c, multiplier +0x30), 64-byte records at +0x48: +0 seat collection (the hellpod's entity id), +0x14 current node, +0x18 target node, +0x28 deadline (u64 microseconds, scene clock `[0x3326348] + 0x18`), +0x30 moving, +0x32 instant.
- The seat update `0x639b40` walks the node graph: while moving, `if clock < deadline return`; else step to the next node and set deadline = now + that edge's time (0 when instant). At the target the seat is reached; the game then opens the Hellpod briefing (presenter 14), whose loadout screen (MenuScreenType 11, `[[0x347ce38] + 0xb0]`) waits in intro phase 1 (+0x27398c) on a 2 s float timer (+0x273988, counted down by the screen update 0x146909f) before building the drop location UI. GalacticMenuHotkey's F8 shortcut expires the same timer.
- The local Helldiver: player manager `[0x3326468]` +0x3a8 (avatar reference, valid while +0x88 is set), resolved like `0xfd9ba0`: entity manager `[0x346bf98]` reference map at +0xf22ec8 (capacity +0xf22ed0, empty +0xf22ed4, multiplier +0xf22ed8), id at manager + 0x1e65e4 * 8 + index * 24. The ship's hellpods: `[0x3326428]` count +8, entity pointers +0x68 (id at +8).
- The skip: on the ship (game state 3), when the local seat goes from free to moving into one of the ship's hellpods, each step's deadline is moved to now until the seat is reached (the game runs every node change and the seat completion itself), then the briefing's intro timer is set to 0 once phase 1 shows. Exits (the seat was already taken), other seats and missions are left alone. Manual: a press while it plays.
- Signatures: `local_ref` 0x4db76b (its call must be the resolver found), `ref_resolver` 0xfd9ba4, `seaters` 0x639846, `seat_wait` 0x639d57, `hellpods` 0xadbaaf, `screen` 0x1082ef0, `briefing_intro` 0x146909f; the intro part also needs the presenter manager.
- Open question (GalacticMenuHotkey's note): seating after the briefing UI is up let the pod entry camera replace the briefing's map camera. Here the seat is reached before the briefing opens, as in the natural order, but the intro is cut right after, so the camera is the thing to watch.

Other changes:
- Galactic map: always on (the Mod Options Menu toggle is gone); Mod Bindings Menu binding `alomare.skip_intro_animation.map` ("Close galactic map") works beside Escape, with the same "a key held when the map opens doesn't count" rule.
- The launch skip (scenes 2 and 6) and the extraction (scene 1, MissionSummary) are removed with their signatures; Mission return is scenes 9 and 8 only (elevator, mission end screen).
- Tests: 68 checks, including the seat and briefing simulation; mutations of the exit check, the hellpod check, the ship check, the deadline write, the intro write, the map key edge and the resolver cross-check are caught.

Questions for the test: does Automatic go from interacting with the hellpod straight to the drop location screen, with the right camera (the map, not the pod)? Does the briefing work normally afterwards (drop location, loadout, launch)? As a client in a squad, and as host with others? Manual: does a press during the climb skip it? Does the map key close the map?

## 5-recon-2 results (2026-10-04)

- Hellpod entry (Automatic, solo): interacting with the hellpod went straight to the drop location screen; the briefing worked. Squad play not tested yet.
- Galactic map: Escape and the Mod Bindings Menu key both close the map.
- Translations: every text showed translated (bp and es tested; logs "15 of 15").
- Mission return (Manual, pressed during the elevator): the skip ran, but the Helldiver got control in the lower level of the ship and was stuck there.
- Mod Bindings Menu: the IMPATIENT DIVER section header is still empty in Brazilian Portuguese.

## 5-recon-3: the elevator ride plays

Why the Helldiver was stuck (`_research/elevator.c`): scene 9's phase 1 entry (`0x1173200`) teleports the local Helldiver to one of four nodes at the bottom of the elevator (by player index: 0xd25583b5, 0x464952a5, 0x11ffed75, 0x75108d67), then plays an event on the level unit 0x7e8ac0673822c3a6; at 0.5 s another (unit 0xdd214b326e9c0317, event 5), at 2 s audio, at 5 s an animation state (0x978) on the Helldiver. The elevator carries the Helldiver up over those 5.83 s. Fast-forwarding phase 1 ended the scene (and gave back control) before the ride. Scene 8 (failure) has no such teleport.

- Mission return now leaves phase 1 alone: the ride plays, then phase 2 (6.67 s, the game's own skippable wait: input action 0x900000000) and the mission end screen are skipped. A press during the ride arms the skip. Signature t9p1 is removed.
- Option description updated in every language ("the wait after the elevator ride ... The elevator ride itself plays").
- Tests: 68 checks; the mission return test now holds the elevator phase (a phase 1 step fails it).

Mod Bindings Menu's empty section header (not ours to fix): MBM shows each section header by borrowing a game localization ID whose text cache slot it fills (`LABEL_POOL`, in order, sections sorted alphabetically). Pool entry 1 (0x77bf158a) and entries 61-65 (0x4b7ce100, 0x74f55d93, 0x59500445, 0x8bc421a5, 0xacf702d0) exist only in the us, gb and jp string tables (checked against all 14 extracted tables in `_research/equip_set/strings`), so in the other 11 languages the lookup finds nothing and the row is blank. IMPATIENT DIVER sorts first, so it gets entry 1; with Impatient Diver removed the next section would go blank instead. Fix for CowboyBingus: drop those 6 IDs from the pool (the other 59 exist in every language).

Questions for the test: after a successful mission with Mission return on Manual or Automatic, does the elevator ride play and does the Helldiver arrive upstairs with control, with the stats screen closed?

## 5-recon-3 results and V5 (2026-10-05)

- Mission return (Automatic): the elevator ride played and the wait after it and the mission end screen were skipped (log: MissionEnd closed 30 frames after it opened, control upstairs). With the ride left to play, the user judged what remained redundant (the wait has the game's own skip input, the stats screen closes with one press), so the option is removed with its signatures (t9p2, t9p3, t8p1, end_request) and the menu-close code. Scenes 1, 8 and 9 are never touched; test 9 checks it with every skip Automatic and the key pressed.
- Hellpod entry is now named "Hellpod to Loadout" in every language. Its option id stays `alomare.skip_intro_animation.hellpod`, so saved settings carry over.
- The research timeline (`RESEARCH`) is removed. Tests: 66 checks.

## 6-recon-1: key press fixes and the drop location zoom

User reports after V5: the "Skip cutscene" key was gone from Mod Bindings Menu (only "Close galactic map" was listed), and another player had to press the skip key once, twice or three times during cutscenes (not reproducible on the user's machine).

- Missing key: the skip binding was only registered while some skip was Manual (every skip is Automatic by default). Mod Bindings Menu lists only bindings registered in the session, and may give the action of one not registered (with its key) to another mod. The binding is now registered every session, whatever the modes; a key set before may have to be set again.
- Uneven presses, causes found offline: (1) every wait counted frames (fast-forward timeout 1200, chain gap 900, Hellpod Manual window 300 frames), so they were shorter at higher frame rates (the Hellpod key window was about 2 s at 144 fps, shorter than the 3.1 s climb); (2) a timed phase that also waits on loading (12 phase 3: the arrival's resources; 15 phase 3: loaded) counted the loading against the timeout, so a slow load ended the fast-forward and each later scene of the chain needed another press; (3) a press on the loading screen between two scenes of a chain was dropped; (4) a press a frame before its scene or hellpod entry was seen (the entry is checked every 10 frames) was dropped.
- Fixes: waits are in seconds of game time (the update's dt, at most 1 s per frame); a timed phase only times out while its timer still needs moving (once over, the phase waits on loading or other players as long as it takes); a press is kept 0.5 s; a press while no scene runs, within 30 s of a Manual scene, carries into the next selected scene; an automatic chain that reaches a Manual scene carries on with a press. Chains wait 30 s (was 900 frames) for a follow-up scene.

Drop location zoom (offline: `MenuScreenLoadout` update 0x1468320, `set_page` 0x1470d90, camera system 0x1279190):
- The loadout screen (MenuScreenType 11 at `[[0x347ce38] + 0xb0]`) has a page at + 8: 0 the drop location map, 1 the loadout. Picking a drop location sets +0x2739c4 to 1.0; once a global (`[0x3326aa0] + 0x55f680`, or +0x4f64 in a synced lobby) is 1.0 too, `0x146f510` calls `set_page(screen, 1)`, which asks the camera system `[0x346d560]` for a blend to the loadout view: `request(camera, position, target, type 5, 1.0 s, fov 70)` (0x127d1f0). Back to the map is the same with 0.75 s.
- The camera keeps blends in a ring of 32 entries of 0xe8 bytes at + 0x200 (read index + 0x1f8, write index + 0x1fc; the latest is the active one): type + 0x2a4, duration + 0x2a8, elapsed + 0x2ac, delay + 0x2b0, reverse + 0x2b4 (offsets include the ring base). The camera update adds dt to the latest blend's elapsed until it reaches the duration (blend weight = elapsed / duration), and `blend_done` (0x127ba60), which the loadout UI code calls (0x1485fa0, 0x1489ee0, 0x148b880), is true once elapsed >= duration.
- The skip: while the Hellpod briefing (presenter 14) shows the loadout screen, the page is read every frame; on 0 -> 1, if the latest blend is type 5, forward, not delayed, at most 5 s long and not over, its elapsed is set to its duration (the camera update then ends it as at its natural end). Manual: a press within 3 s of the page change. Signatures `loadout_page`, `zoom_request`, `blend_done` and `blend_tick` (elapsed and duration must agree between the last two, and the entry's fields must be in a row).
- Not known yet: whether this blend is the whole zoom the user sees (the UI may also animate in), and whether the zoom request is still the latest blend when the mod sees the page (another request the same frame would show as "not the zoom" in the log).
- Option "Drop Location Zoom" (Automatic by default), translated into every language. Tests: 77 checks, including slow loads, presses between scenes and a frame early, 144 fps, and the zoom (Automatic, back to the map, another blend, outside the briefing, Manual, Off, missing code).

Questions for the test: does picking a drop location go straight to the loadout (log: "Drop location zoom: ended at ...")? Any camera or UI glitch? In a squad as host and as client? Does the Skip cutscene key show in Mod Bindings Menu with every skip Automatic, and does one press skip each Manual cutscene (FTL, lobby join, pod)?

## 6-recon-1 results, 6-recon-2: the zoom on the map

- The Skip cutscene key is listed with every skip Automatic.
- The camera blend skip ended the wrong transition: the move from the map into the ship window as the loadout appears (log: "ended at 0.00 of 1.00 s" on the page change). The zoom to skip comes before it, as the drop point is clicked. The camera blend code and its signatures (`zoom_request`, `blend_done`, `blend_tick`) are removed.
- What waits between the click and the loadout page (the loadout screen's update 0x1468320, at 0x14684ef): the click sets the screen's zoom target (+0x2739c4) to 1.0. While the drop group (`[0x3326aa0]`, players at +0x4ec0) has players, its zoom progress (+0x4f64) moves toward the target at 1.0 per second (`move_toward(current, target, 1.0, dt)` 0x173cb30); on the map page, once target and progress are both 1.0, the screen calls `to_loadout` (0x146f510: set_page(1)). Without players it reads a per-player synced value instead (+0x55f680, no ramp). The only other writers of +0x4f64 are a clamped setter (0x72fb20) and a reset to 0 (0x1467e0f); this check is its only reader, so the visual zoom may be drawn from something else that the page switch then cuts.
- The skip: on the map page of the briefing's loadout screen, when the target is 1.0 and the progress is between 0 and 1 (with players in the group), the progress is set to 1.0; the game opens the loadout page itself (the window move then plays as normal). Going back to the map (target 0, the progress returning to 0) is left alone. Manual: a press within 3 s of the pick. Signature `zoom_ramp` (group global, players, target, progress, the move_toward and to_loadout calls, and the page offset, which must agree with `loadout_page`).
- No skip is marked experimental any more (option descriptions in every language, README, Nexus description).
- Tests: 77 checks; the zoom tests simulate the ramp (Automatic and again after going back to the map, no drop group, outside the briefing, the loadout page opened directly, Manual, Off, missing code).

Questions for the test: after clicking a drop point, does the loadout's window move start at once (log: "ended at 0.0x", then "loadout page 1 frames after the skip")? Is any part of the zoom still visible, or any glitch? In a squad as host and as client?

## 6-recon-2 results, 6-recon-3: the client's zoom, Off/Automatic quick skips

- As host, the zoom on the map was skipped (Automatic). As a squad client it played, and the log had no "Drop location zoom" line: the ramp branch's conditions (target 1.0, players in the drop group, progress below 1) never held on the client.
- The loadout update's other branch: without players in the drop group (+0x4ec0 == 0), a screen whose +0x27fe byte is clear opens the loadout page once the group's synced progress (+0x55f680, entry 0 of a per-group block copied from network messages by the system update 0x725160) is 1.0; with the byte set it doesn't switch there at all. 6-recon-3 guesses the client takes this branch and sets the synced value to 1.0 (log "(synced)"). The local copy is refreshed by the next message, but the page has switched by then. The other writers of the target (0xb8ff5d, 0xba5afd) set it to 0 and call set_page(0): resets, not the client's pick.
- Research log: while the briefing's map page is up, each change of the zoom state (target, players, progress, synced, the +0x27fe byte; rounded) is logged as "Zoom state: ...", up to 60 lines per briefing. It shows which branch the client takes if the guess is wrong. To be removed before the release.
- Hellpod to Loadout and Drop Location Zoom are Off / Automatic only (the user: too quick for a key press). Saved values from the three-choice options read as Automatic (Manual = 2 is now Automatic; 3 is out of range, so the default). Their descriptions lose the Manual sentence in every language. README and Nexus description updated for V6 (Drop Location Zoom, the two-choice options).
- Tests: 77 checks (the Manual hellpod and zoom tests are gone; added: old saved choices, the client branch, a leading screen without players).

Question for the test: as a squad client, is the zoom skipped (log "ended at ... (synced)")? If not, the "Zoom state" lines from the client's pick show what changed.

## 6-recon-3 results, V6

- As a squad client, the zoom was skipped: the client takes the synced branch, as guessed. The "Zoom state" research log is removed.
- Released as V6: the Skip cutscene key always listed, skips that wait through loading and keep a press made just before a scene, Drop Location Zoom, Hellpod to Loadout and Drop Location Zoom as Off / Automatic, no experimental tags.
