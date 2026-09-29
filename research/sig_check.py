"""Checks the release build's code signatures against the Ghidra-ready game.dll dump (offsets == RVAs):
how often each pattern matches and what it resolves to.

Usage: python -B research/sig_check.py <game dll dump>
"""
import re
import struct
import sys

SIGS = {
    'interrupt_site': '48 8B 0D ?? ?? ?? ?? 39 91 0C 19 00 00 0F 84 ?? ?? ?? ?? 48 83 C4 30 5B E9 ?? ?? ?? ??',
    'interrupt_head': '48 89 5C 24 10 48 89 6C 24 18 56 57 41 56 48 83 EC 50',
    'audio_site': 'BA 56 6B CA 41 E8 ?? ?? ?? ?? BA E2 02 6C 61 E8',
    'clock_13p2': '48 8B 05 ?? ?? ?? ?? 49 8B 88 90 00 00 00 48 81 C1 60 E3 16 00 48 39 48 18',
    't13p3': '48 8B 8A 88 00 00 00 48 81 C1 E0 70 72 00 48 39 48 18',
    't13p4': '49 8B 88 88 00 00 00 48 81 C1 35 82 00 00 48 39 48 18',
    't12p3': '48 8B 8A 88 00 00 00 48 81 C1 25 A0 33 00 48 39 48 18',
    't11p2': '48 8B 81 88 00 00 00 48 05 1A E9 61 00 48 39 42 18',
    't15p3': '48 8B 81 88 00 00 00 48 05 40 4B 4C 00 49 39 40 18',
    'fader': ('48 83 EC 38 48 8B 0D ?? ?? ?? ?? 33 D2 48 81 C1 28 01 00 00 48 89 54 24 20 F2 0F 10 44 24 20 0F 28 D1 '
              '0F 57 C9 0F 2E D1 8B 81 94 07 00 00 89 81 9C 07 00 00 C7 81 A0 07 00 00 00 00 80 3F'),
    'names': 'FF C9 83 F9 ?? 0F 87 ?? ?? ?? ?? 48 8D 15 ?? ?? ?? ?? 8B 8C 8A ?? ?? ?? ?? 48 03 CA FF E1',
}


def compile_sig(text):
    parts = text.split()
    rx = b''.join(b'.' if p == '??' else re.escape(bytes([int(p, 16)])) for p in parts)
    return re.compile(rx, re.S)


def rip(d, at, length):
    return at + length + struct.unpack_from('<i', d, at + length - 4)[0]


def cstr(d, at):
    return d[at:d.index(b'\0', at)].decode('ascii', 'replace')


def names_from(d, at):
    count = d[at + 4] + 1
    table = struct.unpack_from('<I', d, at + 21)[0]
    out = {}
    for i in range(count):
        code = struct.unpack_from('<I', d, table + i * 4)[0]
        if d[code:code + 3] != b'\x48\x8d\x05' or d[code + 7] != 0xc3:
            return None
        out[i + 1] = cstr(d, rip(d, code, 7))
    return out


def main(path):
    d = open(path, 'rb').read()
    for name, text in SIGS.items():
        hits = [m.start() for m in compile_sig(text).finditer(d)]
        extra = ''
        if hits and name == 'interrupt_site':
            h = hits[0]
            extra = 'manager %#x interrupt %#x' % (rip(d, h, 7), rip(d, h + 24, 5))
        elif hits and name == 'audio_site':
            extra = 'post_audio ' + ' '.join('%#x' % rip(d, h + 5, 5) for h in hits)
        elif hits and name in ('clock_13p2', 'fader'):
            extra = 'global %#x' % rip(d, hits[0] + (0 if name == 'clock_13p2' else 4), 7)
        elif name == 'names':
            good = [(h, names_from(d, h)) for h in hits]
            good = [(h, n) for h, n in good if n and 'ship_teleporter_arrival' in n.values()]
            extra = 'valid: ' + '; '.join('%#x %s' % (h, n) for h, n in good)
        print('%-15s %4d hits %s %s' % (name, len(hits), [hex(h) for h in hits[:4]], extra))


if __name__ == '__main__':
    main(sys.argv[1])
