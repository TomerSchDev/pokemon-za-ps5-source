"""Two isolated translated units; baseline game archive and generated C untouched."""
from pathlib import Path
import hashlib,json,struct,sys
source,nso,out=map(Path,sys.argv[1:]);out.mkdir(parents=True,exist_ok=True)
raw=nso.read_bytes();assert raw[:4]==b'NSO0'
assert raw[0x40:0x60].rstrip(b'\0').hex()=='b1f12fd919eae86ab8a978317677e64bce443d1f'
expected={'main_145.c':'0b63266d262f3ef96690bddbc8d9a824f113067d380d40d061ce4d745f345374',
          'main_209.c':'59b436b66d81004403380e1d746b7c56b76883ffaccd749b1f183dee1ef0c945'}
records=[]
for name,digest in expected.items():
    data=(source/name).read_bytes();assert hashlib.sha256(data).hexdigest()==digest
    text=data.decode().replace('\r\n','\n')
    if name=='main_145.c':
        target='L_7000447554:;\n'
        assert text.count(target)==1
        # This label follows the target's virtual eligibility check, before the
        # normal score/roll logic. Zero scores and the original blocked flag stay.
        text=text.replace(target,target+'    { extern uint32_t za_cheat_capture_score(uint32_t, uint64_t); c->v[8] = za_cheat_capture_score((uint32_t)c->v[8], c->x[19]); }\n')
        assert text.index('if (((c->x[0] >> 0) & 1) == 0) { goto L_7000447460; }')<text.index(target)
    else:
        target='void f_7000656f80(Cpu *c) {';assert text.count(target)==1
        text=text.replace(target,'static void za_original_fix_init_spec(Cpu *c) {')
        text+='''\nvoid f_7000656f80(Cpu *c) {
    extern uint32_t za_cheat_spec_before(uint64_t);
    extern void za_cheat_spec_after(uint64_t, uint32_t);
    uint64_t spec = c->x[0];
    uint32_t token = za_cheat_spec_before(spec);
    za_original_fix_init_spec(c);
    za_cheat_spec_after(spec, token);
}\n'''
    target=out/name;encoded=text.encode()
    if target.exists():assert target.read_bytes()==encoded
    else:target.write_bytes(encoded)
    records.append({'name':name,'original_sha256':digest,'patched_sha256':hashlib.sha256(encoded).hexdigest()})
report={'build_id':raw[0x40:0x60].rstrip(b'\0').hex(),'baseline_unchanged':True,'modified_units':records,
        'capture_hook':'After target eligibility, before score/roll; score<=0 and block flag preserved',
        'shiny_hook':'Original FixInitSpec called once; temporary extra rolls restored; optional PID correction after original',
        'console_tested':False}
(out/'hook-manifest.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
