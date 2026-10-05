# Changelog

Releases are named "Impatient Diver V&lt;n&gt;" (tag `v<n>`). Each section is that release's notes.

## V6 (2026-10-05)

- Added Drop Location Zoom (Automatic by default): skips the camera zoom on the map after picking a drop location, as host or squad member.
- Fixed the Skip cutscene key missing from Mod Bindings Menu when every skip is Automatic (set the key again if it was lost).
- Fixed the skip key sometimes needing several presses: skips no longer give up during slow loading, a press during loading between cutscenes or just before one starts now counts, and timings no longer depend on the frame rate.
- Hellpod to Loadout and Drop Location Zoom now only offer Off and Automatic.
- Hellpod to Loadout is no longer marked experimental.

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
