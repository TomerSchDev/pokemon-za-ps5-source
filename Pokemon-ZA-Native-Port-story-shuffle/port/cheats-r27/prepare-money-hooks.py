"""Audit and patch five isolated 2.0.2 translated units; never edits its inputs."""
from pathlib import Path
import argparse, hashlib, json

BUILD_ID = 'b1f12fd919eae86ab8a978317677e64bce443d1f'
EXPECTED = {
    'main_220.c': 'f0f55e339300a9a84c91f3da6dd2814137b9da116af475492446654d56a58c6f',
    'main_303.c': '026c3b3236d4cc71e96a282595fc001ff2e022cbce39ae7d14f9eb995fc2f517',
    'main_315.c': '00d57d87200d00ef023eaad209524630a41424262df9c01b69488ec9023ff910',
    'main_384.c': '79d6d6175e5cc0d3ad11e81875a236f2abba0416c6634d50595124af5d345fbf',
    'main_1035.c': 'c8f1043b49049f8bbba246df63e6333a57611958307237f3ea0a1eb985d0426e',
}
PATCHES = {
    'main_220.c': ('L_70006bfd98:;\n', 'L_70006bfd98:;\n    { extern void za_cheat_money_component(uint64_t); za_cheat_money_component(c->x[23]); }\n'),
    'main_303.c': ('L_70009c18d8:;\n', 'L_70009c18d8:;\n    { extern void za_cheat_money_component(uint64_t); za_cheat_money_component(c->x[0]); }\n'),
    'main_315.c': ('L_7000a7195c:;\n    c->x[0] = (uint64_t)(0ull | c->x[19]);',
                   'L_7000a7195c:;\n    { extern void za_cheat_money_component(uint64_t); za_cheat_money_component(c->x[19]); }\n    c->x[0] = (uint64_t)(0ull | c->x[19]);'),
    'main_384.c': ('L_7000dbb28c:;\n', 'L_7000dbb28c:;\n    { extern void za_money_lifecycle_reset(void); za_money_lifecycle_reset(); }\n'),
    'main_1035.c': ('L_700291eaf0:;\n', 'L_700291eaf0:;\n    { extern void za_money_lifecycle_reset(void); za_money_lifecycle_reset(); }\n'),
}
GETTER_PATCH = ('L_700291eb18:;\n', 'L_700291eb18:;\n    { extern void za_cheat_money_component(uint64_t); za_cheat_money_component(c->x[0]); }\n')
LOAD_PATCH = ('    c->x[30] = 0x7000dbb2e8ull; f_7000976bac(c);\n    { uint64_t ea = c->x[19] + 0x40ull; ST32(ea, (uint32_t)c->x[0]); }\n',
              '    c->x[30] = 0x7000dbb2e8ull; f_7000976bac(c);\n    { uint64_t ea = c->x[19] + 0x40ull; ST32(ea, (uint32_t)c->x[0]); }\n    { extern void za_cheat_money_component(uint64_t); za_cheat_money_component(c->x[19]); }\n')
def sha(data): return hashlib.sha256(data).hexdigest()
def prepare(source, nso, out):
    source, nso, out = map(Path, (source, nso, out))
    raw = nso.read_bytes()
    if raw[:4] != b'NSO0' or raw[0x40:0x60].rstrip(b'\0').hex() != BUILD_ID:
        raise ValueError('unapproved game NSO/build ID')
    # Validate all sources and prepare all outputs before any write.
    prepared = []
    for name, expected in EXPECTED.items():
        data = (source / name).read_bytes()
        if sha(data) != expected: raise ValueError('unapproved source SHA-256: ' + name)
        text = data.decode('utf-8').replace('\r\n', '\n')
        old, new = PATCHES[name]
        if text.count(old) != 1: raise ValueError('hook anchor is not unique: ' + name)
        text = text.replace(old, new)
        if name == 'main_1035.c':
            old_get,new_get=GETTER_PATCH
            if text.count(old_get)!=1:raise ValueError('getter anchor is not unique')
            text=text.replace(old_get,new_get)
        if name == 'main_384.c':
            old_load,new_load=LOAD_PATCH
            if text.count(old_load)!=1:raise ValueError('load anchor is not unique')
            text=text.replace(old_load,new_load)
        encoded = text.encode('utf-8')
        target = out / name
        if target.resolve() == (source/name).resolve(): raise ValueError('output aliases source')
        if target.exists() and target.read_bytes() != encoded: raise ValueError('refusing to overwrite: ' + str(target))
        prepared.append((name, data, encoded))
    report = dict(build_id=BUILD_ID, baseline_unchanged=True, console_tested=False,
        hook='UI reader f_70006bfce0, Save f_70009c18d8, lookup f_7000a718c8, Get f_700291eb18; Load post-store establishes readiness',
        lifecycle='clear pending and OFF at money Load and Reset; null/invalid lookup also clears',
        units=[dict(name=n, original_sha256=sha(d), patched_sha256=sha(e)) for n,d,e in prepared])
    out.mkdir(parents=True, exist_ok=True)
    for name, _, encoded in prepared:
        target = out/name
        if not target.exists(): target.write_bytes(encoded)
    (out/'money-hook-manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    return report
if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('source',type=Path); p.add_argument('nso',type=Path); p.add_argument('out',type=Path)
    a=p.parse_args(); print(json.dumps(prepare(a.source,a.nso,a.out),indent=2))
