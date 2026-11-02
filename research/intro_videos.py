"""The intro videos: the three start-up logos and the two title screen videos, each cut to its first third of a second.

    python -B research/intro_videos.py <out dir> [--data <game data dir>] [--check]

Each video is a Bink 2 file (bk2 resource: a 16-byte main part, the file in .stream). The cut keeps the header, the
frame table of the first frames and their data (the first is a keyframe, the others build on it). The videos are read
from the game's data with FileDiver's res_get (Script/_shared/filediver). The command line writes a patch of the videos
alone with Audiodiver's patch writer (ProjectAudiodiver/Audiodiver/core), whose header the game loads; the mod's intro option
carries them in its sound patch instead (intro_sounds.py), since the title videos also wait for their sound.
--check has ffprobe read each cut file (needs FFmpeg on PATH): one video stream with the frames kept.
"""
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = os.path.normpath(os.path.join(HERE, '..', '..', '..', '..'))    # <Helldivers 2>/Mods
FILEDIVER = os.path.join(MODS, 'Script', '_shared', 'filediver')
AUDIODIVER = os.path.join(MODS, '..', 'ProjectAudiodiver', 'Audiodiver', 'core')
GAME_DATA = r'C:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\data'
BK2 = 0x5ee65304478f8db5
KEEP_SECONDS = 1 / 3   # a one-frame video never counted as ended (9-recon-1)

# (resource name hash, what it is): StateSplash's table and the title screen's two videos (RESEARCH.md, "Intro videos")
VIDEOS = [
    (0x917be57698744617, 'start-up logo 1'),
    (0x3d7f04931c0dd5f2, 'start-up logo 2'),
    (0xc08afc84be2bc3fa, 'start-up logo 3'),
    (0x5263c1fe0615c6ad, 'title video 0x2b1a74c2'),
    (0xc4038098ec6384ab, 'title video 0xde13da08'),
]


def read_video(data_dir, fid, most):
    """The video's main part and the first `most` bytes of its file."""
    with tempfile.TemporaryDirectory() as tmp:
        prefix = os.path.join(tmp, 'v')
        subprocess.run(['go', 'run', './cmd/res_get', data_dir, 'bk2', '%016x' % fid, prefix, str(most)],
                       cwd=FILEDIVER, check=True, capture_output=True)
        main = open(prefix + '.main.bin', 'rb').read()
        head = open(prefix + '.stream.bin', 'rb').read()
    return main, head


def frame_table(head):
    """(table offset, frame count): the table is where its first entry points just past it (frames + 1 entries),
    with the keyframe bit set."""
    sig, _, frames = struct.unpack_from('<4sII', head, 0)
    if sig[:3] != b'KB2':
        raise ValueError('not a Bink 2 file: %r' % sig)
    for at in range(0x2c, 0x200, 4):
        first = struct.unpack_from('<I', head, at)[0]
        if first & 1 and first & ~1 == at + 4 * (frames + 1):
            return at, frames
    raise ValueError('no frame table found')


def frames_kept(head):
    """How many frames the cut keeps: KEEP_SECONDS at the video's frame rate, at least one, at most all."""
    num, den = struct.unpack_from('<II', head, 0x1c)
    return max(1, min(frame_table(head)[1], round(num / max(den, 1) * KEEP_SECONDS)))


def cut_end(head):
    """Where the kept frames end in the file: the bytes a cut needs."""
    at, _ = frame_table(head)
    return struct.unpack_from('<I', head, at + 4 * frames_kept(head))[0] & ~1


def cut(head):
    """The video cut to its first frames_kept frames."""
    at, frames = frame_table(head)
    n = frames_kept(head)
    offsets = struct.unpack_from('<%dI' % (n + 1), head, at)
    start, end = offsets[0] & ~1, offsets[n] & ~1
    body = head[start:end]
    if len(body) != end - start:
        raise ValueError('the kept frames are cut short')
    shift = (at + 4 * (n + 1)) - start          # the table shrinks: every offset moves back by the entries dropped
    sizes = [(offsets[i + 1] & ~1) - (offsets[i] & ~1) for i in range(n)]
    out = bytearray(head[:at])
    struct.pack_into('<I', out, 0x08, n)              # frames
    struct.pack_into('<I', out, 0x0c, max(sizes))     # largest frame
    struct.pack_into('<I', out, 0x10, n)              # frames (again)
    out += struct.pack('<%dI' % n, *[((o & ~1) + shift) | (o & 1) for o in offsets[:n]])
    out += struct.pack('<I', end + shift)
    out += body
    struct.pack_into('<I', out, 0x04, len(out) - 8)
    return bytes(out)


def probe(video, path):
    """ffprobe's reading of the file's streams and packets. FFmpeg reads Bink 2 up to revision i, which has the same
    header and frame table as the game's revision n, so the copy it reads is relabelled."""
    open(path, 'wb').write(video[:3] + b'i' + video[4:])
    r = subprocess.run(['ffprobe', '-v', 'error', '-count_packets', '-show_entries',
                        'stream=codec_type,width,height,nb_read_packets', '-of', 'compact=nk=1', path],
                       capture_output=True, text=True)
    os.remove(path)
    return (r.stdout + r.stderr).strip().replace('\n', ' | ')


def carried(data_dir=GAME_DATA, check_dir=None):
    """The cut videos as Audiodiver patch entries (patch.Carried). check_dir: where ffprobe's copies go (--check)."""
    sys.path.insert(0, AUDIODIVER)
    from audiodiver.patch import Carried
    out = []
    for fid, what in VIDEOS:
        main_part, head = read_video(data_dir, fid, 1 << 20)
        if cut_end(head) > len(head):
            main_part, head = read_video(data_dir, fid, cut_end(head))
        video = cut(head)
        out.append(Carried(fid, BK2, main_part, stream=video))
        line = '%016x %-24s %d frames -> %d, %d bytes' % (fid, what, frame_table(head)[1], frames_kept(head), len(video))
        if check_dir:
            line += ' | ffprobe: ' + probe(video, os.path.join(check_dir, '%016x.bk2' % fid))
        print(line)
    return out


def build(out, data_dir=GAME_DATA, check=False):
    """Writes a patch of the videos alone (9ba626afa44a3aa3.patch_0 and its .stream / .gpu_resources) to out."""
    sys.path.insert(0, AUDIODIVER)
    from audiodiver.patch import write_patch
    os.makedirs(out, exist_ok=True)
    entries = carried(data_dir, out if check else None)
    path = os.path.join(out, '9ba626afa44a3aa3.patch_0')
    write_patch(path, {}, {}, {}, carried=entries)
    if not os.path.exists(path + '.gpu_resources'):   # empty, as in the game's own patches
        open(path + '.gpu_resources', 'wb').close()


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    data_dir = args[args.index('--data') + 1] if '--data' in args else GAME_DATA
    build(args[0], data_dir, '--check' in args)
    print('patch written to', args[0])


if __name__ == '__main__':
    main()
