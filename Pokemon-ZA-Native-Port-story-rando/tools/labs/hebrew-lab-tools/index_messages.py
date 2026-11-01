"""Index (and optionally extract) the game's message files from a RomFS image, read-only.

usage: python index_messages.py <romfs.bin> <out dir> [--extract LANG,LANG...|all] [--fonts]
Writes <out>/message-index.json (paths, sizes, per language) and, with --extract, the decompressed files to
<out>/romfs/<game path>. Output must stay inside hebrew-lab (private game data, ignored by git).
"""
import argparse
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from za_romfs import Game, fnv1a64  # noqa: E402

LANGS = ['JPN_KANJI', 'JPN', 'English', 'French', 'Italian', 'German', 'Spanish', 'LATAM', 'Latam', 'Korean',
         'Simp_Chinese', 'Trad_Chinese', 'jpn']


def candidates(flat):
    """'ik_messagedatEnglishcommonmonsname.dat' -> possible slash-separated game paths"""
    out = []
    for pre in ('ik_message/dat/', 'ik_message/sort/', 'ik_message/grammar/', 'ik_message/'):
        key = pre.replace('/', '')
        if not flat.startswith(key):
            continue
        rest = flat[len(key):]
        for lang in LANGS:
            if rest.startswith(lang):
                tail = rest[len(lang):]
                for cat in ('common', 'script', 'sk', ''):
                    if tail.startswith(cat):
                        name = tail[len(cat):]
                        if cat:
                            out.append(pre + lang + '/' + cat + '/' + name)
                        else:
                            out.append(pre + lang + '/' + name)
        out.append(pre + rest)
    # generic: up to 3 extra slashes anywhere (short names only)
    if not out or len(flat) < 48:
        for k in range(1, 4):
            for cuts in itertools.combinations(range(1, len(flat)), k):
                parts, last = [], 0
                for c in cuts:
                    parts.append(flat[last:c]); last = c
                parts.append(flat[last:])
                out.append('/'.join(parts))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('romfs')
    ap.add_argument('out')
    ap.add_argument('--extract', default='')
    ap.add_argument('--fonts', action='store_true')
    a = ap.parse_args()
    g = Game(a.romfs)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    index = {}
    unresolved = []
    for name, recs in g.packs:
        if not name.startswith('arc/ik_message'):
            continue
        flat = name[4:-6]
        hashes = {r['hash']: r for r in recs}
        got = 0
        for c in candidates(flat):
            for v in {c, c[:-4] + '.dat' if c.endswith('.tbl') else c, c[:-4] + '.tbl' if c.endswith('.dat') else c}:
                h = fnv1a64(v)
                if h in hashes and v not in index:
                    r = hashes[h]
                    index[v] = dict(pack=name, size=r['size'], csize=r['csize'], files_in_pack=len(recs))
                    got += 1
            if got == len(recs):
                break
        if got < len(recs):
            unresolved.append(dict(pack=name, files=len(recs), resolved=got))
    with open(os.path.join(out, 'message-index.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(resolved=len(index), unresolved=unresolved, files=index), f, indent=1, sort_keys=True)
    print('message packs resolved:', len(index), 'unresolved:', len(unresolved))
    want = set(x for x in a.extract.split(',') if x)
    if want:
        n = 0
        for path in index:
            parts = path.split('/')
            lang = parts[2] if len(parts) > 3 else parts[-1].split('.')[0]
            if 'all' in want or lang in want or any(w in path for w in want):
                d = g.read(path)
                dst = os.path.join(out, 'romfs', *parts)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, 'wb') as f:
                    f.write(d)
                n += 1
        print('extracted', n, 'message files')
    if a.fonts:
        fonts = {}
        for name, recs in g.packs:
            if 'uifontbin' not in name:
                continue
            for r in recs:
                d = g.unpack(r)
                dst = os.path.join(out, 'fonts', name[4:-6], '%016x.bin' % r['hash'])
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, 'wb') as f:
                    f.write(d)
                fonts.setdefault(name, []).append(dict(hash='%016x' % r['hash'], size=len(d), magic=d[:8].hex()))
        with open(os.path.join(out, 'font-index.json'), 'w') as f:
            json.dump(fonts, f, indent=1)
        print('font packs:', len(fonts))


if __name__ == '__main__':
    main()
