"""Read-only: FlatBuffers vtable sizes ("struct lengths") of Z-A Trinity model files, for comparison with the public
LA/SV parser by Random Talking Bush (PokemonSwitch_GFBMDL-TRMDL.ms, 2022-11-26), which branches on exactly these sizes:
  TRMDL root 0x12 (LA) / 0x14, 0x18 (SV only);  TRMSH root 0x0A;  TRMSH mesh 0x1E (LA) / 0x22 (SV only);
  vertex attribute 0x0C / 0x0E;  TRMBF root 0x08;  TRMBF buffer 0x08 (LA) / 0x0A (SV only);
  TRSKL root 0x0C / 0x0E;  TRSKL bone 0x12 / 0x14 / 0x16;  bone SRT 0x0A;  TRMTR root 0x08;  material 0x24.
Usage: trinity_headers.py <model folder under samples, e.g. ik_pokemon/data/pm0025/pm0025_00_00> <stem>"""
import collections, struct, sys
B = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab/samples/'

class FB:
    def __init__(s, path): s.d = open(path, 'rb').read()
    def u16(s, p): return struct.unpack_from('<H', s.d, p)[0]
    def u32(s, p): return struct.unpack_from('<I', s.d, p)[0]
    def i32(s, p): return struct.unpack_from('<i', s.d, p)[0]
    def vt(s, t):
        v = t - s.i32(t); n = s.u16(v)
        return n, [s.u16(v + 4 + 2 * i) for i in range((n - 4) // 2)]
    def root(s): return s.u32(0)
    def field(s, t, i):
        n, offs = s.vt(t)
        return t + offs[i] if i < len(offs) and offs[i] else None
    def ref(s, p): return p + s.u32(p)
    def vec(s, p):
        v = s.ref(p); n = s.u32(v)
        return [s.ref(v + 4 + 4 * k) for k in range(n)]
    def vec_scalar(s, p, size):
        v = s.ref(p); n = s.u32(v)
        return [v + 4 + size * k for k in range(n)]
    def string(s, p):
        q = s.ref(p); n = s.u32(q); return s.d[q + 4:q + 4 + n].decode('utf-8', 'replace')
    def u32f(s, t, i, default=0):
        p = s.field(t, i); return s.u32(p) if p is not None else default

def report(folder, stem):
    out = {}
    m = FB(B + folder + '/' + stem + '.trmdl')
    r = m.root(); out['trmdl.root'] = hex(m.vt(r)[0])
    out['trmdl.fields_present'] = [i for i, o in enumerate(m.vt(r)[1]) if o]
    out['trmdl.mesh_ref'] = sorted({hex(m.vt(t)[0]) for t in m.vec(m.field(r, 1))})
    out['trmdl.skel_ref'] = hex(m.vt(m.ref(m.field(r, 2)))[0])
    out['trmdl.f9_value'] = m.u32f(r, 9)
    s = FB(B + folder + '/' + stem + '.trmsh')
    r = s.root(); out['trmsh.root'] = hex(s.vt(r)[0])
    meshes = s.vec(s.field(r, 1))
    out['trmsh.mesh'] = sorted({hex(s.vt(t)[0]) for t in meshes})
    attrs = collections.Counter(); attr_vt = set(); sub_vt = set()
    for t in meshes:
        for decl in s.vec(s.field(t, 3)):
            for a in s.vec(s.field(decl, 0)):
                attr_vt.add(hex(s.vt(a)[0]))
                attrs[(s.u32f(a, 1), s.u32f(a, 2), s.u32f(a, 3))] += 1
        for sub in s.vec(s.field(t, 4)):
            sub_vt.add(hex(s.vt(sub)[0]))
    out['trmsh.vertex_attr_vt'] = sorted(attr_vt)
    out['trmsh.vertex_attrs(type,layer,format)'] = sorted(attrs)
    out['trmsh.submesh_vt'] = sorted(sub_vt)
    out['trmsh.trmbf'] = s.string(s.field(r, 2))
    b = FB(B + folder + '/' + stem + '.trmbf') if False else None  # trmbf not extracted (large); see note
    k = FB(B + folder + '/' + stem + '.trskl')
    r = k.root(); out['trskl.root'] = hex(k.vt(r)[0]); out['trskl.fields_present'] = [i for i, o in enumerate(k.vt(r)[1]) if o]
    bones = k.vec(k.field(r, 1))
    out['trskl.bone_count'] = len(bones)
    out['trskl.bone_vt'] = dict(collections.Counter(hex(k.vt(t)[0]) for t in bones))
    out['trskl.srt_vt'] = sorted({hex(k.vt(k.ref(k.field(t, 1)))[0]) for t in bones if k.field(t, 1) is not None})
    out['trskl.first_bones'] = [k.string(k.field(t, 0)) for t in bones[:14]]
    t = FB(B + folder + '/' + stem + '.trmtr')
    r = t.root(); out['trmtr.root'] = hex(t.vt(r)[0])
    mats = t.vec(t.field(r, 1))
    out['trmtr.material_vt'] = sorted({hex(t.vt(x)[0]) for x in mats})
    shaders = set()
    for x in mats:
        name = t.string(t.field(x, 0))
        p = t.field(x, 1)
        if p is not None:
            for sh in t.vec(p):
                q = t.field(sh, 0)
                if q is not None: shaders.add(t.string(q))
    out['trmtr.materials'] = len(mats)
    out['trmtr.shader_names'] = sorted(shaders)
    return out

if __name__ == '__main__':
    for k, v in report(sys.argv[1], sys.argv[2]).items():
        print(f'{k}: {v}')
