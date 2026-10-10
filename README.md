<img width="1920" height="1080" alt="thumbnail" src="https://github.com/user-attachments/assets/ce926f10-3180-41b0-ada4-a833200ba89e" />

# Impatient Diver

A Helldivers 2 Lua mod for [Bingus Shared Loader](https://github.com/CowboyBingus/BingusSharedLoader) that skips the ship's waiting scenes, takes you from the hellpod straight to the loadout, cuts the zoom after you pick a drop location and closes the galactic map in one press.

## Features

- **Log-in ship intro:** the camera flying into the ship and your Helldiver walking to the bridge after you log in.
- **Cryo pod transition:** your cryo pod rolling in and your Helldiver stepping out when you arrive on a ship. You take control at the pod exit, where the game would put you anyway.
- **FTL transition:** the FTL jump when the ship travels to another planet and when you join a lobby. Loading still happens; one Manual press while joining a lobby also skips the cryo pod after it.
- **Hellpod to Loadout:** your Helldiver climbing into the hellpod and the camera moving to the drop location screen. The drop location, the loadout and the launch are untouched.
- **Drop Location Zoom:** the quick zoom on the map after you pick a drop location; the loadout appears right away.
- The three cutscenes are each **Off**, **Manual** (spacebar, or a Mod Bindings Menu key) or **Automatic** (the default); Hellpod to Loadout and Drop Location Zoom, too quick for a key press, are **Off** or **Automatic** (the default).
- **Galactic Map Quick Exit:** Escape closes the galactic map at once from any level (mission, operation, planet or sector) instead of going back one level per press. Always on; a "Close galactic map" key can also be set in Mod Bindings Menu (for example a gamepad button).
- Settings in [Mod Options Menu](https://github.com/CowboyBingus/ModOptionsMenu) (escape menu > MODS > Impatient Diver), applied at once. Without it every feature is on.
- Texts follow the game's Text Language.
- Skips happen on your game only: teammates don't need the mod.

## Installation

1. Install [Bingus Shared Loader](https://www.nexusmods.com/helldivers2/mods/16292) (v17 or newer).
2. Optional: [Mod Options Menu](https://www.nexusmods.com/helldivers2/mods/16625) to change the settings, and [Mod Bindings Menu](https://www.nexusmods.com/helldivers2/mods/16478) for a skip key other than spacebar.
3. Install the ZIP from [Releases](https://github.com/Alomare/ImpatientDiver/releases) with [HD2 Arsenal](https://www.nexusmods.com/helldivers2/mods/4664) (or HD2 Mod Manager) and deploy. Keep Bingus Shared Loader last in the mod order, so it loads first.

The verdict is the first line of `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\ImpatientDiver_STATUS.log`.

## Technical Details

- **Cutscenes.** The ship sequences are scenes run by the game's cutscene manager, which keeps the previous, current and queued scene ids. The mod reads the current scene each frame and maps ids to names through the game's own id-to-name table, so a new or renumbered scene can't be mistaken for one it skips.
- **Fast-forward, not abort.** Each scene waits on timers: a phase ends when the scene clock passes a stamp plus a fixed wait. The mod moves the running phase's stamp back so the game's own update changes phase, with everything that phase change normally does (placing the Helldiver at the pod exit, restoring control). Aborting the scene instead left cinematic state behind that crashed the next hellpod launch. Loading waits are never skipped. During the FTL scenes the screen fader is held clear.
- **Hellpod to Loadout.** Climbing into the hellpod is a seat transition: the local Helldiver's seat record steps through a node graph, each step waiting until the scene clock passes a deadline. On the ship, when the seat starts moving into one of the ship's hellpods, the mod moves each deadline to now, so the game runs every step and the seat completion itself; the Hellpod briefing that opens then waits 2 s on a timer before building the drop location screen, which the mod expires. Leaving the hellpod and every other seat are left alone.
- **Drop Location Zoom.** Picking a drop point sets the loadout screen's zoom target to 1, and the screen opens its loadout page once the drop group's zoom progress, which moves toward the target at 1 per second, reaches it. The mod sets that progress to 1 right after the pick, so the game opens the loadout page itself; going back to the map is left alone.
- **Galactic map.** The map is the game's Hologram menu presenter. Each presenter has a close request that the presenter manager checks every frame; on Escape (or the Mod Bindings Menu key) the mod sets the map's, so the game closes it (and pops its screen) the way it does itself.
- **Finding the game's code.** Every global, structure offset and timer wait comes from code signatures ('??' wildcards) in game.dll, generated in one block by `research/signatures.py` from a game.dll dump and checked to match exactly once. At startup each is tried at the known build's address, else game.dll's executable sections are searched over a few frames; values are read from the matched instructions (rip-relative operands, displacements, immediates), and a value used by several signatures must agree. What can't be found turns off only the feature that needs it. The search engine (`tools/sigscan.lua` in the author's workspace) is shared with the author's other mods.
- **Texts.** `locales/en.lua` is the English source and `locales/<tag>.lua` the bundled translations, resolved by CowboyBingus' `src/bingus_text.lua` against the game's Text Language; the build places both ahead of the script. Option and binding texts are passed to Mod Options Menu v1.1 / Mod Bindings Menu v2.1 as functions, so they follow language changes.
- **Memory access.** Reads and writes go through `ReadProcessMemory` / `WriteProcessMemory` on the game's own process, which fail instead of crashing on a bad address.
- **Tests.** `tests/test_release.py` runs the built entry under LuaJIT against a game.dll dump (not included), with the cutscene manager, clock, fader, presenter manager and hellpod seats simulated.

Research notes: [NOTES.md](NOTES.md). Release notes: [CHANGELOG.md](CHANGELOG.md).

## Credits

- Built on [Bingus Shared Loader](https://github.com/CowboyBingus/BingusSharedLoader), [Mod Options Menu](https://github.com/CowboyBingus/ModOptionsMenu) and [Mod Bindings Menu](https://github.com/CowboyBingus/ModBindingsMenu) by CowboyBingus, whose `bingus_text.lua` provides the translations.
- Developed with Claude Opus 5.5 and the [HD2 Lua Mod Skill](https://github.com/MrChengl11/hd2-lua-mod-skill).

## License

Copyright (C) 2026 Alomare. Licensed under the [GNU General Public License v3.0 or later](LICENSE): you're free to use, study, change and share this mod, and anything you distribute that includes or changes its code must use the same license and come with its source. `src/bingus_text.lua` is CowboyBingus's, under the Zero-Clause BSD license.
