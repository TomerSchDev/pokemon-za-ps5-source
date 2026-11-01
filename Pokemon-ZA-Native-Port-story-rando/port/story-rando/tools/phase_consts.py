"""Scan main .text for MOVZ/MOVK materialising story-phase constants; map hits to atlas functions."""
import sys, re, json, bisect, sqlite3, struct
from pathlib import Path
REPO = Path(r'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port')
sys.path.insert(0, str(REPO / 'tools/za-atlas/P2'))
import extract
nso = extract.Nso(Path(r'C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\hebrew-lab\qa-game-reference-20261030\exefs\main'), 'main')
print('build', nso.build_id, hex(nso.base))
phases = set()
for line in open('phase.txt', encoding='utf-8'):
    t = line.split(' |')[0]
    if t.isdigit(): phases.add(int(t))
dlc = []
try:
    for line in open('dlc_phase.txt', encoding='utf-8'):
        t = line.split(' |')[0]
        if t.isdigit(): phases.add(int(t)); dlc.append(int(t))
except FileNotFoundError:
    pass
# exclude values too generic
generic = {10000, 20000, 30000, 50000, 100000}
want = {p for p in phases if p not in generic and p % 1000 != 0}
text = nso.segments[0]
code = text['bytes']; base = nso.base + text['off']
n = len(code) // 4
ins = struct.unpack_from('<%dI' % n, code)
hits = []
for i, w in enumerate(ins):
    if (w & 0x7F800000) != 0x52800000: continue  # MOVZ
    hw = (w >> 21) & 3; imm = (w >> 5) & 0xFFFF; rd = w & 31
    if hw != 0: continue
    val = imm
    for j in range(i + 1, min(i + 5, n)):
        w2 = ins[j]
        if (w2 & 0x7F800000) == 0x72800000 and (w2 & 31) == rd and ((w2 >> 21) & 3) == 1:
            val = imm | (((w2 >> 5) & 0xFFFF) << 16); break
    if val in want:
        hits.append((base + 4 * i, val))
db = sqlite3.connect(str(REPO.parent / 'za-atlas-data/atlas.sqlite'))
fns = sorted(int(a, 16) for (a,) in db.execute("select addr from functions where module='main'"))
by = {}
for addr, val in hits:
    k = bisect.bisect_right(fns, addr) - 1
    f = fns[k] if k >= 0 else 0
    by.setdefault(f, []).append(val)
rows = sorted(by.items(), key=lambda kv: -len(set(kv[1])))
out = [dict(fn='f_%x' % f, distinct=len(set(v)), values=sorted(set(v))) for f, v in rows]
json.dump(dict(total_hits=len(hits), functions=out), open('phase_consts.json', 'w'), indent=1)
print('hits', len(hits), 'functions', len(rows))
for r in out[:40]: print(r['fn'], r['distinct'], r['values'][:20])
