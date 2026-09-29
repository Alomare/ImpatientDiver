# Impatient Diver

A Helldivers 2 Lua mod (Bingus Shared Loader) that skips the log-in ship intro, the cryo pod transition and the FTL
transition, each set to Off, Manual or Automatic in Mod Options Menu.

## Technical Description

- **Cutscenes.** The ship sequences are scenes run by the game's cutscene manager, which keeps the previous, current
  and queued scene ids. The mod reads the current scene each frame and maps ids to names through the game's own
  id-to-name table, so a new or renumbered scene can't be mistaken for one it skips.
- **Fast-forward, not abort.** Each scene waits on timers: a phase ends when the scene clock passes a stamp plus a
  fixed wait. The mod moves the running phase's stamp back so the game's own update changes phase, with everything
  that phase change normally does (placing the Helldiver at the pod exit, restoring control). Aborting the scene
  instead left cinematic state behind that crashed the next hellpod launch. Loading waits are never skipped.
- **FTL fades.** During the FTL scenes the screen fader is held clear.
- **Input.** Manual mode reads spacebar through the engine's Lua API, plus an optional
  [Mod Bindings Menu](https://github.com/CowboyBingus/ModBindingsMenu) binding.
- **Finding the game's code.** Every address comes from code signatures ('??' wildcards) in game.dll: the cutscene
  manager and clock globals from rip-relative loads, the timer checks by their wait constants, and the scene name
  table from its switch. Each is tried at the known build's address first, else game.dll's executable sections are
  searched over a few frames, and a signature must match exactly once. What can't be found turns off only the skip
  that needs it.
- **Memory access.** Reads and writes go through `ReadProcessMemory` / `WriteProcessMemory` on the game's own
  process, which fail instead of crashing on a bad address.
- **Status.** `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\ImpatientDiver_STATUS.log`, first line = verdict.

Research notes: [NOTES.md](NOTES.md). The offline tests (`tests/`) run the script under LuaJIT against a game.dll
dump, which is not included.

## Credits

- Built on [Bingus Shared Loader](https://github.com/CowboyBingus/BingusSharedLoader),
  [Mod Options Menu](https://github.com/CowboyBingus/ModOptionsMenu) and
  [Mod Bindings Menu](https://github.com/CowboyBingus/ModBindingsMenu) by CowboyBingus.
- Developed with Claude Opus 5.5 and the [HD2 Lua Mod Skill](https://github.com/MrChengl11/hd2-lua-mod-skill).

## Nexus

https://www.nexusmods.com/helldivers2/mods/16624
