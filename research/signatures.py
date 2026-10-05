"""Impatient Diver's code signatures (NOTES.md): checked against the game.dll dump and written into
skip_intro_animation.lua between the SIGNATURES markers, with the shared signature engine (tools/sigscan.lua)
between the SIGNATURE ENGINE markers.

Every signature is optional: each feature needs only its own (the mod turns off just the features whose code isn't
found). Timer checks read their stamp offset and wait from the code, so a retimed scene keeps working.

Usage (from the workspace root): python -B mods/ImpatientDiver/research/signatures.py [--check]
  --check   only verify: every signature matches once and the script's blocks are current (exit 1 otherwise)
"""
import sys
from pathlib import Path

MOD = Path(__file__).resolve().parents[1]
ROOT = MOD.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import sigspec  # noqa: E402

SCRIPT = MOD / 'skip_intro_animation.lua'


def timer(name, start, end, stamp, wait):
    """A scene timer check: mov reg,[ctx+stamp]; add reg,wait; cmp [clock+18h],reg (span made unique around it)."""
    return {'name': name, 'start': start, 'end': end, 'optional': True,
            'fields': {name + '_stamp': (stamp, 'u32'), name + '_wait': (wait, 'u32')}}


SPECS = [
    # `if (manager->current != 0) interrupt_current_scene(manager, 0)`: the cutscene manager global and its current
    # scene id (previous at -4, queued at +4). (The interrupt itself is not used.)
    {'name': 'interrupt_site', 'start': 0xad6ca2, 'end': 0xad6cbf, 'optional': True,
     'fields': {'manager': (0x346d530, 'rip'), 'current': (0x190c, 'u32')}},
    # Scene 13 phase 2's timer, with the scene clock (u64 microseconds at clock + 0x18).
    {'name': 't13p2', 'start': 0x1178030, 'end': 0x1178057, 'optional': True,
     'fields': {'clock': (0x3326348, 'rip'), 't13p2_stamp': (0x90, 'u32'), 't13p2_wait': (0x16e360, 'u32'),
                'clock_now': (0x18, 'u8')}},
    timer('t13p3', 0x1177f9b, 0x1177fbc, 0x88, 0x7270e0),
    timer('t13p4', 0x1177ec4, 0x1177ee3, 0x88, 0x8235),
    timer('t12p3', 0x117df3d, 0x117df5a, 0x88, 0x33a025),
    timer('t11p2', 0x117dee2, 0x117defe, 0x88, 0x61e91a),
    timer('t15p3', 0x1179efb, 0x1179f24, 0x88, 0x4c4b40),
    timer('t7p1', 0x117dbb1, 0x117dbde, 0x88, 0x2dc6c0),
    timer('t7p2', 0x117db78, 0x117dbbe, 0x88, 0x51615),
    # ship_bridge_intro's update (game.dll + 0x116d7a0): each phase waits 1 to 2.5 s.
    timer('t3_2s', 0x116d7d8, 0x116d817, 0x88, 0x1e8480),
    timer('t3_125', 0x116d809, 0x116d829, 0x88, 0x1312d0),
    timer('t3_175', 0x116d8bb, 0x116d8db, 0x88, 0x1ab3f0),
    timer('t3_25', 0x116d92f, 0x116d966, 0x88, 0x2625a0),
    timer('t3_1s', 0x116d949, 0x116d966, 0x88, 0xf4240),
    timer('t3_15', 0x116d97a, 0x116d997, 0x88, 0x16e360),
    # The game state (`cmp [game + 0xac21c], 4` in the hellpod launch's mission check: 3 on the ship, 4 in a mission).
    {'name': 'game_state', 'start': 0x11d5b23, 'end': 0x11d5b35, 'optional': True,
     'fields': {'game': (0x3326340, 'rip'), 'game_state': (0xac21c, 'u32')}},
    # Hellpod to loadout: entering the hellpod is a seat transition (seater component [0x3326d78], 64-byte
    # records), then the seat opens the Hellpod briefing (presenter 14), whose loadout screen waits 2 s before its UI.
    # The local Helldiver: the player manager's avatar reference (+0x3a8, while a local player is active, +0x88) ...
    {'name': 'local_ref', 'start': 0x4db76b, 'end': 0x4db78e, 'optional': True,
     'fields': {'players': (0x3326468, 'rip'), 'local_active': (0x88, 'u32'), 'avatar_ref': (0x3a8, 'u32'),
                'resolver': (0xfd9ba0, 'call')}},
    # ... which the game turns into an entity id with this resolver (0xfd9ba0): the entity manager's reference map
    # (buckets, capacity, empty key, multiplier), then the id at manager + index * 24 + ids * 8.
    {'name': 'ref_resolver', 'start': 0xfd9ba4, 'end': 0xfd9c5b, 'optional': True,
     'fields': {'entities': (0x346bf98, 'rip'), 'ent_capacity': (0xf22ed0, 'u32'),
                'ent_multiplier': (0xf22ed8, 'u32'), 'ent_map': (0xf22ec8, 'u32'), 'ent_empty': (0xf22ed4, 'u32'),
                'ent_ids': (0x1e65e4, 'u32')}},
    # The seater component (the instant seat entry, 0x639830): its map of seater entity ids to records (buckets,
    # capacity, empty key, multiplier) and the records array (64 bytes each).
    {'name': 'seaters', 'start': 0x639846, 'end': 0x6398b8, 'optional': True,
     'fields': {'seaters': (0x3326d78, 'rip'), 'seat_capacity': (0x28, 'u8'), 'seat_multiplier': (0x30, 'u8'),
                'seat_map': (0x20, 'u8'), 'seat_empty': (0x2c, 'u8'), 'seat_records': (0x48, 'u8')}},
    # The seat transition's wait (0x639b40): while moving (+0x30) toward a target node (+0x18), each edge waits until
    # the clock passes the record's deadline (+0x28, u64 microseconds on the scene clock).
    {'name': 'seat_wait', 'start': 0x639d57, 'end': 0x639d91, 'optional': True,
     'fields': {'seat_moving': (0x30, 'u8'), 'seat_target': (0x18, 'u8'), 'seat_clock': (0x3326348, 'rip'),
                'seat_deadline': (0x28, 'u8'), 'seat_clock_now': (0x18, 'u8')}},
    # The ship's hellpods: the hellpod manager's count (+8) and entity pointers (+0x68; the entity id at +8).
    {'name': 'hellpods', 'start': 0xadbaaf, 'end': 0xadbace, 'optional': True,
     'fields': {'hellpods': (0x3326428, 'rip'), 'pod_list': (0x68, 'u8')}},
    # The Hellpod loadout screen (MenuScreenType 11): [[stack] + slot] when the stack's type is 11 ...
    {'name': 'screen', 'start': 0x1082ef0, 'end': 0x1082f09, 'optional': True,
     'fields': {'screen_stack': (0x347ce38, 'rip'), 'screen_slot': (0xb0, 'u32'), 'local_index': (0x27d0, 'u32')}},
    # ... and its intro countdown: while the intro phase is set, timer -= dt; at 0 the phase moves on (phase 1 is the
    # 2 s wait before the briefing UI is built).
    {'name': 'briefing_intro', 'start': 0x146909f, 'end': 0x14690ca, 'optional': True,
     'fields': {'intro_phase': (0x27398c, 'u32'), 'intro_timer': (0x273988, 'u32')}},
    # Drop location zoom: the loadout screen's page (`set_page` 0x1470d90: page at screen + 8, 0 = drop location map,
    # 1 = loadout) ...
    {'name': 'loadout_page', 'start': 0x1470db3, 'end': 0x1470de3, 'optional': True,
     'fields': {'page': (8, 'u8')}},
    # ... and the zoom after a drop location is picked (the loadout screen's update 0x1468320): the pick sets the
    # screen's zoom target (+ 0x2739c4) to 1.0; while the drop group ([0x3326aa0] + 0x4ec0) has players, the zoom
    # (+ 0x4f64) moves toward the target at 1.0 per second (`move_toward` 0x173cb30), and once both are 1.0 on the
    # map page the screen calls `to_loadout` (0x146f510: set_page(1)). Without players, a screen whose + 0x27fe byte is
    # clear waits for the group's synced progress (+ 0x55f680, copied from network messages) to be 1.0 instead.
    {'name': 'zoom_ramp', 'start': 0x14684ef, 'end': 0x1468584, 'optional': True,
     'fields': {'zoom_group': (0x3326aa0, 'rip'), 'zoom_players': (0x4ec0, 'u32'), 'zoom_target': (0x2739c4, 'u32'),
                'zoom_progress': (0x4f64, 'u32'), 'move_toward': (0x173cb30, 'call'), 'page': (8, 'u8'),
                'zoom_synced': (0x55f680, 'u32'), 'zoom_leader': (0x27fe, 'u32'),
                'to_loadout': (0x146f510, 'call')}},
    # The screen fade setter: the fader global, + 0x128, then duration/alpha/start/target.
    {'name': 'fader', 'start': 0x11d66c0, 'end': 0x11d671e, 'optional': True,
     'fields': {'fader': (0x347cda8, 'rip'), 'fader_offset': (0x128, 'u32'), 'fader_alpha': (0x794, 'u32'),
                'fader_start': (0x79c, 'u32'), 'fader_target': (0x7a0, 'u32'), 'fader_duration': (0x784, 'u32')}},
    # The scene id-to-name switch: dec ecx; cmp ecx,max; ja; lea rdx,[image]; mov ecx,[rdx+rcx*4+table]. The script
    # reads the names from the match itself (scene_names), so nothing is a field here.
    {'name': 'names', 'start': 0x117e950, 'end': 0x117e96e, 'optional': True, 'wild': (0x13, 0x117ea18)},
    # Galactic map quick exit. "Is the briefing presenter open?" (0x662520): the UI state global, its presenter
    # manager (+0x4288), the presenter stack (+0x14) and depth (+0x28).
    {'name': 'presenters', 'start': 0x662520, 'end': 0x662557, 'optional': True,
     'fields': {'ui': (0x347ce28, 'rip'), 'presenters': (0x4288, 'u32'), 'depth': (0x28, 'u8'), 'stack': (0x14, 'u8')}},
    # PresenterManager::open: `if (current != 0) close_current(manager)`: the current presenter's offset.
    {'name': 'presenter_open', 'start': 0x14c038e, 'end': 0x14c039c, 'optional': True,
     'fields': {'current_presenter': (0xc, 'u8'), 'close': (0x14c0900, 'call')}},
    # PresenterManager::update: closes each presenter whose close request (check(manager + 0xd8, presenter)) is set.
    {'name': 'presenter_update', 'start': 0x14bf890, 'end': 0x14bf8aa, 'optional': True,
     'fields': {'collection': (0xd8, 'u32'), 'check': (0x14bdc20, 'call'), 'close': (0x14c0900, 'call')}},
    # ... check's cases 14-16: the Hologram presenter (15, the galactic map) keeps its close request at
    # [collection + 0x98] + 0x10.
    {'name': 'hologram_request', 'start': 0x14bdcbb, 'end': 0x14bdcde, 'optional': True,
     'fields': {'holo_slot': (0x98, 'u32'), 'close_flag': (0x10, 'u8')}},
]


def main():
    rows = sigspec.build(SPECS)
    sigspec.report(rows)
    if '--check' in sys.argv:
        problems = sigspec.check(SCRIPT, rows)
        for p in problems:
            print('STALE:', p)
        sys.exit(1 if problems else 0)
    sigspec.write(SCRIPT, rows)
    print('written to', SCRIPT.name)


if __name__ == '__main__':
    main()
