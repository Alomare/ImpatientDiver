"""The intro option's patch: the cut videos (intro_videos.py) and the intro's sounds made silent and short.

    python -B research/intro_sounds.py <out dir> [--data <game data dir>]

The title screen's videos end only when their voice line has played, and each start-up logo has a sound of its own,
so cutting the pictures alone leaves a black screen while the sound plays. The patch is built with Audiodiver's core
(ProjectAudiodiver/Audiodiver/core): each sound below is replaced with its built-in silence with the timing fitted to it (what
Audiodiver calls "skip"), so it ends at once:
- every clip of content/audio/intro_logos (the logos' sounds and the title screen's stinger; nothing else is in it);
- the two voice lines the title videos play, in every voice language the game has installed: in a language's
  content/audio/<code>/cutscenes bank, each is the one Sound under its parent object. A language not installed where
  the patch is built keeps its lines, and its players hear them over a black screen until they press a key.
"""
import os
import struct
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import intro_videos                  # noqa: E402

sys.path.insert(0, intro_videos.AUDIODIVER)
from audiodiver import bank as wbank, wem   # noqa: E402
from audiodiver.build import make_patch, PATCH   # noqa: E402
from audiodiver.game import murmur64_hash   # noqa: E402
from audiodiver.index import AudioIndex, LANGUAGES   # noqa: E402
from audiodiver.project import Project, Replacement   # noqa: E402

INTRO_LOGOS = 'content/audio/intro_logos'
# the title videos' voice lines, by the parent object of their Sound in each language's bank: the Sound ids themselves
# differ by language and change with game updates, the parents stay. Game build 26251122 took the short line out of the
# English bank, so that video has none to wait for there; another language's bank may still have it.
LONG_LINE = 631201114
VOICE_PARENTS = {
    LONG_LINE: 'title video 0xde13da08: "Super Earth. Our home. Prosperity..." (100.7 s, the video 98 s)',
    394469756: 'title video 0x2b1a74c2: "Super Earth. Liberty. Democracy..." (10.0 s, the video 8 s)',
}


def bank_id(name):
    return murmur64_hash(name.encode())


def parent_of(t, body):
    """A node's parent object: the u32 after the bus id, which ends just before its settings (bank.props_at)."""
    return struct.unpack_from('<I', body, wbank.props_at(t, body) - 5)[0]


def sources(ix, log=print):
    """[(source id, what it is)] of the sounds the option makes silent."""
    out = []
    b = ix.banks[bank_id(INTRO_LOGOS)]
    for sid in dict.fromkeys([*b['refs'], *b['media']]):
        out.append((sid, 'intro_logos clip'))
    for code, language in LANGUAGES.items():
        bid = bank_id('content/audio/%s/cutscenes' % code)
        if bid not in ix.banks:
            continue
        _, hirc = wbank.parse(ix.bank_files(bid)[0])
        under = {}
        for oid, (t, body) in hirc.items():
            if t == wbank.SOUND:
                under.setdefault(parent_of(t, body), []).append(oid)
        for parent, what in VOICE_PARENTS.items():
            found = under.get(parent, [])
            if len(found) != 1:
                log('  %s: %d Sounds under parent %d, the line is left as it is' % (language, len(found), parent))
                assert code != 'us' or parent != LONG_LINE, 'English has to have the long line: its parent changed?'
                continue
            t, body = hirc[found[0]]
            out.append((wbank.source_ids(t, body)[0], '%s, %s' % (language, what)))
    return out


def build(out_dir, data_dir=intro_videos.GAME_DATA, log=print):
    """Writes out_dir/9ba626afa44a3aa3.patch_0 (+ .stream, .gpu_resources): the silent sounds and the cut videos."""
    ix = AudioIndex(log=lambda *a: None)
    picked = sources(ix, log)
    for sid, what in picked:
        ms = wem.length_ms(ix.wem(sid)[:4096])
        log('  silent: %d, %s s (%s)' % (sid, '%.1f' % (ms / 1000) if ms else '?', what))
    project = Project(name='Impatient Diver intro', every_bank=True,
                      replacements=[Replacement(target=sid, audio='', silence=True, fit_timing=True) for sid, _ in picked])
    project.path = Path(out_dir) / 'intro.audi'
    os.makedirs(out_dir, exist_ok=True)
    make_patch(project, ix, Path(out_dir), log=log, carried=intro_videos.carried(data_dir))
    path = os.path.join(out_dir, PATCH)
    for suffix in ('.stream', '.gpu_resources'):   # present even when empty, as in the game's own patches
        if not os.path.exists(path + suffix):
            open(path + suffix, 'wb').close()


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    data_dir = args[args.index('--data') + 1] if '--data' in args else intro_videos.GAME_DATA
    build(args[0], data_dir)
    print('patch written to', args[0])


if __name__ == '__main__':
    main()
