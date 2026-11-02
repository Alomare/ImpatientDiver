"""Builds internal/build/Impatient-Diver-<version>.zip for HD2 Arsenal: the mod for Chef Shared Loader (option "core")
and the intro patch (option "intro": the cut videos and the intro's sounds made silent, intro_sounds.py).

    python -B research/build_release.py [--release] [--version V] [--data <game data dir> | --intro-from <a build's zip>]

--release also copies the ZIP to releases/ (a pushed release ZIP becomes a GitHub release). --version builds an internal
version (10-recon-1) without touching mod.json; it still needs M.version to match in the script. --intro-from takes the
intro patch as it is from an earlier ZIP instead of building it from the game's data.
Needs the maintainer's workspace: Chef Shared Loader's tools, FileDiver and Audiodiver.
"""
import json
import os
import re
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
CHEF_TOOLS = os.path.normpath(os.path.join(MOD, '..', '..', '_shared', 'Chef-Shared-Loader', 'tools'))
NAME = 'Impatient Diver (CSL/EAC)'   # what mod loaders show (mod.json's displayName names the GitHub releases)

sys.path.insert(0, CHEF_TOOLS)
sys.path.insert(0, HERE)
import hd2_patch                     # noqa: E402  (Chef Shared Loader's patch writer)
from pack_addon import HEADER, zip_dir   # noqa: E402  (the Lua patch header Chef Shared Loader ships with)


def main():
    args = sys.argv[1:]
    data_dir = args[args.index('--data') + 1] if '--data' in args else None
    intro_from = args[args.index('--intro-from') + 1] if '--intro-from' in args else None
    spec = json.load(open(os.path.join(MOD, 'mod.json'), encoding='utf-8'))
    version = args[args.index('--version') + 1] if '--version' in args else spec['version']
    src = open(os.path.join(MOD, spec['entry']), 'rb').read()
    first = src.split(b'\n', 1)[0].decode()
    assert first == '-- HD2-Addon: ' + spec['name'], first
    assert b"\r" not in src, 'the entry must have LF line endings'
    in_script = re.search(rb"local M = \{ version = '([^']+)' \}", src).group(1).decode()
    assert in_script == version, 'M.version is %s, building %s' % (in_script, version)

    stage = os.path.join(MOD, 'internal', 'build', 'pack')
    shutil.rmtree(stage, ignore_errors=True)
    core = os.path.join(stage, 'core')
    os.makedirs(core)
    hd2_patch.write_lua_archive(os.path.join(core, '9ba626afa44a3aa3.patch_0'),
                                [(hd2_patch.resource_hash(spec['name']), hd2_patch.lua_resource(src))], HEADER)
    if intro_from:
        with zipfile.ZipFile(intro_from) as z:
            names = [n for n in z.namelist() if n.startswith('intro/') and not n.endswith('/')]
            assert names, 'no intro patch in ' + intro_from
            z.extractall(stage, names)
    else:
        import intro_sounds              # (Audiodiver's core, and FileDiver through go)
        import intro_videos
        intro_sounds.build(os.path.join(stage, 'intro'), data_dir or intro_videos.GAME_DATA)
    for leftover in os.listdir(os.path.join(stage, 'intro')):
        if not leftover.startswith('9ba626afa44a3aa3.patch_'):
            os.remove(os.path.join(stage, 'intro', leftover))

    manifest = {
        'Version': 1, 'Guid': spec['guid'], 'Name': NAME, 'Description': spec['description'],
        'IconPath': 'icon.png',
        'Options': [
            {'Name': 'Scene skips', 'Description': 'The log-in intro, the cryo pod, the FTL, the hellpod entry and the '
             'drop zoom play instantly or at 8x, as you set each one in the F9 menu.', 'Image': 'icon.png',
             'Include': ['core']},
            {'Name': 'Intro videos', 'Description': 'The start-up logos and the two title screen videos last a third '
             'of a second, with their sounds silent. A game update can make this part stale: untick it if the game '
             "misbehaves at start-up until there's a new version.", 'Image': 'icon.png', 'Include': ['intro']},
        ],
    }
    shutil.copy(os.path.join(MOD, 'icon.png'), os.path.join(stage, 'icon.png'))
    json.dump(manifest, open(os.path.join(stage, 'manifest.json'), 'w', encoding='utf-8'), indent=2)
    out = os.path.join(MOD, 'internal', 'build', 'Impatient-Diver-%s.zip' % version)
    zip_dir(stage, out)
    shutil.rmtree(stage)
    print(out, os.path.getsize(out), 'bytes')
    if '--release' in args:
        os.makedirs(os.path.join(MOD, 'releases'), exist_ok=True)
        shutil.copyfile(out, os.path.join(MOD, 'releases', os.path.basename(out)))
        print('copied to releases/')


if __name__ == '__main__':
    main()
