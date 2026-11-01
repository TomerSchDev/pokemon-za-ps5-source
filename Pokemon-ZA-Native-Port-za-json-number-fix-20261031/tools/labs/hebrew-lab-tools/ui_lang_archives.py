"""Count the UI archives that exist per language (ui/data/... _eng/_kor/... .arc): their textures can carry baked text."""
import collections, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from za_romfs import Game
g = Game(sys.argv[1])
suf = collections.Counter(); sizes = collections.Counter(); names = collections.defaultdict(set)
for name, recs in g.packs:
    m = re.match(r'arc/uidata(.*)_(eng|kor|fre|ger|ita|spa|ltm|jpn|sch|tch)\.arc\.trpak$', name)
    if m:
        suf[m.group(2)] += 1
        sizes[m.group(2)] += sum(r['size'] for r in recs)
        names[m.group(2)].add(m.group(1))
print(json.dumps({k: dict(archives=suf[k], bytes=sizes[k]) for k in suf}, indent=1))
print('eng-only:', sorted(names['eng'] - names['kor'])[:10], 'kor-only:', sorted(names['kor'] - names['eng'])[:10])
print('examples:', sorted(names['eng'])[:40])
