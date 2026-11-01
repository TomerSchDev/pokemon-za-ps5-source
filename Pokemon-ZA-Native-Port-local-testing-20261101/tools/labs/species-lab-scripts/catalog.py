"""Parse ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog (Z-A 2.0.2) into JSON: species-info fields + paths."""
import json, struct, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/scripts')
from fbwalk import u32, i32, u16, try_string, try_table, field_sizes

S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
d = open(S + '/samples/ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog', 'rb').read()

def fields(p):
    offs, tsz = try_table(d, p)
    return [(i, p + o, field_sizes(offs, tsz)[o]) if o else None for i, o in enumerate(offs)]

def ref(fp): return fp + u32(d, fp)

def vec(fp):
    v = ref(fp); n = u32(d, v)
    return [ref(v + 4 + 4 * k) for k in range(n)]

def scalars(p):
    out = {}
    for f in fields(p):
        if not f: continue
        i, fp, s = f
        out['f%d' % i] = d[fp] if s == 1 else u16(d, fp) if s in (2, 3) else u32(d, fp)
    return out

root = u32(d, 0)
rf = fields(root)
entries = []
for e in vec(rf[1][1]):
    ef = fields(e)
    rec = {}
    for f in ef:
        if not f: continue
        i, fp, s = f
        if i == 0:
            rec['info'] = scalars(ref(fp))
        elif i in (1, 2, 3, 6, 7, 8):
            rec['f%d' % i] = try_string(d, ref(fp))
        elif i in (4, 5) or i > 8:
            items = []
            for t in vec(fp):
                st = try_string(d, t)
                if st is not None:
                    items.append(st); continue
                tf = fields(t)
                sub = {}
                for g in tf:
                    if not g: continue
                    j, gp, gs = g
                    st = try_string(d, ref(gp)) if gs >= 4 else None
                    sub['f%d' % j] = st if st is not None else (d[gp] if gs == 1 else u16(d, gp) if gs in (2, 3) else u32(d, gp))
                items.append(sub)
            rec['f%d' % i] = items
    entries.append(rec)
json.dump(entries, open(S + '/out/catalog.json', 'w'), indent=1)
print('entries', len(entries))
keys = set()
for r in entries: keys |= set(r)
print('entry fields', sorted(keys))
ik = set()
for r in entries: ik |= set(r.get('info', {}))
print('info fields', sorted(ik))
for r in entries[:3] + entries[100:103] + entries[-5:]:
    print(r.get('info'), r.get('f1'), 'anims', len(r.get('f4', [])), 'skel', len(r.get('f5', [])), {k: v for k, v in r.items() if k not in ('info', 'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f8')})
