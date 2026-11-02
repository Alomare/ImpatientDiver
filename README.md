<img width="1920" height="1080" alt="thumbnail" src="https://github.com/user-attachments/assets/ce926f10-3180-41b0-ada4-a833200ba89e" />

# Impatient Diver

A Helldivers 2 Lua mod for [Chef Shared Loader](https://github.com/Th3chef/Chef-Shared-Loader) that skips the intro videos and the ship's waiting scenes, and takes you from the hellpod straight to the loadout. Mod loaders list it as Impatient Diver (CSL/EAC).

Since V9 it runs on the game's plain Lua 5.1, without FFI or memory access. V8 and older ran on Bingus Shared Loader and can't run on the current game.

## Features

- **Intro videos** (an option when you install the mod): the three start-up logos and the two title screen videos last a third of a second, with their sounds silent. The title's "press a button" screen stays.
- **Log-in ship intro:** the camera flying into the ship and your Helldiver walking to the bridge after you log in.
- **Cryo pod transition:** your cryo pod rolling in and your Helldiver stepping out when you arrive on a ship.
- **FTL transition:** the FTL jump when the ship travels to another planet, and the shots of the ship when you join or leave a lobby. Loading still takes its time.
- **Hellpod to Loadout:** your Helldiver climbing into the hellpod and the camera moving to the drop location map.
- **Drop Location Zoom:** the zoom after you pick a drop point, also when you go back to the map and pick another one. In a squad only the host can speed it up: everyone's zoom follows the host's.

Each scene is a row in the F9 menu: **Instant** (the default), **Fast** (8x speed) or **Off**. Texts are in English.

Scenes are only sped up while the mod recognises them. Never in a mission, in the hellpod launch or in the return from a mission.

## Installation

1. Install the latest [Chef Shared Loader](https://www.nexusmods.com/helldivers2/mods/17760) (1.5.1 or newer) and keep it at the top priority.
2. Install the ZIP from [Releases](https://github.com/Alomare/ImpatientDiver/releases) with [HD2 Arsenal](https://www.nexusmods.com/helldivers2/mods/4664) (or HD2 Mod Manager) and deploy. Remove V8 or older first if you still have one.

The log is `%APPDATA%\Arrowhead\Helldivers2\ImpatientDiver.log`.

## Known limits

- **Voice languages.** The silent intro covers the English voice line. With another voice language installed, the title video's line still plays over a black screen until you press a key. Untick the Intro videos option if you prefer the full videos.
- **Game updates.** The Intro videos option carries a copy of three of the game's sound banks, as of the build it was made for. If an update changes them, untick the option until there's a new version.
- **Squadmates** may see your Helldiver leave the cryo pod early. They don't need the mod.
- **Picking a drop point again right after going back to the map:** while the camera is still moving back, the zoom plays at normal speed.

## Technical Details

- **Speed.** Scenes go through the engine's own clock: `Application.set_time_step_policy('external_multiplier', 8)` for Fast, and one `'jump'` of 1 s a frame for Instant, up to a budget per scene, then 8x for what is left. The game ends each scene itself, so your Helldiver is placed and control comes back as always.
- **Telling the scenes apart.** The mod reads no game memory: it recognises scenes from what the engine's Lua API shows: which worlds exist and what they hold, the main camera, and the Helldiver's animation state.
- **The intro patch** is a data patch, built with Audiodiver's core and FileDiver.
- **Tests.** `tests/test_release.py` runs the script under Lua 5.1 with a fake loader and engine; `tests/mutate.py` checks that the tests catch each guard being removed.

How it works in the game: [RESEARCH.md](RESEARCH.md). Contributing: [CONTRIBUTING.md](CONTRIBUTING.md). Release notes: [CHANGELOG.md](CHANGELOG.md).

## Credits

- Runs on [Chef Shared Loader](https://github.com/Th3chef/Chef-Shared-Loader) by Th3chef.
- Developed with Claude Opus 5.5 and the [HD2 Lua Mod Skill](https://github.com/MrChengl11/hd2-lua-mod-skill).
- Game data read with [FileDiver](https://github.com/xypwn/filediver).

## License

Copyright (c) 2026 Alomare. Licensed under the [MIT License](LICENSE). V8 and older were released under the GPL-3.0-or-later and stay available under it.
