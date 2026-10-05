# Changelog

Releases are named "Impatient Diver V&lt;n&gt;" (tag `v<n>`). Each section is that release's notes.

## V5 (2026-10-05)

- Added Galactic Map Quick Exit: Escape closes the galactic map from any level. A Mod Bindings Menu key can also be set.
- Added Hellpod to Loadout (experimental, Automatic by default): skips climbing into the hellpod, up to the drop location screen.
- Skips no longer stop during long loading screens.
- Translated into every game language.
- Cutscene timings are read from the game code, so retimed cutscenes keep their skip after game updates.

## V4 (2026-09-29)

- Stricter code search after game updates: a skip whose code isn't found exactly once is turned off.

## V3

- Settings moved to Mod Options Menu: each skip is Off, Manual or Automatic (default Automatic).
- With every skip Off, the mod doesn't read game memory.

## V2

- Fixed a crash during the hellpod descent after the log-in intro was skipped.

## 1.0.1

- Removed screen fader writes during the FTL transition.

## 1.0.0

- First release: skips the log-in ship intro, the cryo pod transition and the FTL transition, automatically or with a key press.
