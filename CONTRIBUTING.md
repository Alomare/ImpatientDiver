# Contributing to Impatient Diver

Thanks for your interest in Impatient Diver. This guide is for anyone who wants to help: players reporting a bug and Lua developers. You don't need to know how the game works inside to report a bug.

## How the mod is built

Impatient Diver is a Lua 5.1 mod for Helldivers 2 that runs under [Chef Shared Loader](https://github.com/Th3chef/Chef-Shared-Loader), whose [MODDING.md](https://github.com/Th3chef/Chef-Shared-Loader/blob/main/docs/MODDING.md) describes what a mod can reach.

- `skip_intro_animation.lua` is the whole mod's code: one plain Lua script.
- The Intro videos option is a data patch, built by `research/intro_sounds.py` and `research/intro_videos.py`.
- [README.md](README.md) explains what the mod does; [RESEARCH.md](RESEARCH.md) explains how it tells the game's scenes apart. Read both before changing code.

**What you can and can't do locally.** You can run the tests: `pip install lupa`, then `python -B tests/test_release.py`. The ZIP needs the maintainer's workspace, so send your change as a pull request and the maintainer builds a test version for you to try.

## Reporting a bug

Open an [issue](https://github.com/Alomare/ImpatientDiver/issues) with:

1. **What happened,** what you expected, and the steps to make it happen again.
2. **The logs,** from `%APPDATA%\Arrowhead\Helldivers2\`: `ImpatientDiver.log` and `chef_loader.log`.
3. **Whether the game updated** shortly before.
4. **Your other mods** and their order in your mod manager.
5. **Solo or in a squad,** and if in a squad, whether you were the host.
6. **Your settings** for that scene, and your voice language if it's about the intro.

Crash dumps can contain personal paths from your PC: don't post them publicly.

## Changing the code

For anything bigger than a small fix, **open an issue first**. Some ideas were already tried and dropped for reasons that aren't obvious from the code.

| Path | What it is |
| --- | --- |
| `skip_intro_animation.lua` | The mod. |
| `tests/test_release.py` | The offline tests. Add a check for what you change. |
| `tests/mutate.py` | Removes each guard in turn and expects the tests to fail. A new guard gets a mutant. |
| `research/` | The build and the intro patch. |
| `mod.json` | The manifest. Never change `guid`. |
| `CHANGELOG.md`, `releases/` | Release notes and ZIPs, written by the maintainer at release time. |

In a pull request, keep to one topic, and say what changes for players and how you tested it. Leave the version, `CHANGELOG.md` and `releases/` alone. Match the code around your change: 2-space indentation, lines up to 120 characters, `local` everything, comments that say what the game does and why.

## Rules the code follows

1. **Speed up only while a recognised scene plays.** No speed keys, and nothing that works as a speed hack.
2. **Never in a mission, the hellpod launch or the return from a mission.** Tests enforce it.
3. **Only our own Helldiver's posture counts,** never another player's.
4. **Back to normal speed when a scene ends,** or after its cap, and when the mod stops (`on_stop`).
5. **Engine asserts crash the game, and `pcall` can't catch them.** Check `Unit.alive` before every call on a kept unit, and `Unit.has_animation_state_machine` before animation calls.
6. **No game memory, no game code.** The mod uses the engine's Lua API only.
7. **Waits that depend on loading are paced in game time,** with the jumps left out; real time comes from `os.clock`.

## Sharing a research finding

Findings about the game are welcome even without code. Open an issue or a pull request against [RESEARCH.md](RESEARCH.md), with the game build and whether you saw it in the running game. Never paste the game's decompiled code or files from its archives, or code from other mods without a compatible license.

## License of contributions

This mod is licensed under the [MIT License](LICENSE). By contributing, you agree that your contribution is licensed the same way. Contributors are credited in the release notes, and in the README for larger contributions.
