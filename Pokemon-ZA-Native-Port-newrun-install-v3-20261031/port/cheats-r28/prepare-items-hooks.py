"""Hash-pinned additive hooks, in fresh copies; retain all r27 money hooks."""
from pathlib import Path
import hashlib,importlib.util,json,sys
own=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('money',own.parent/'cheats-r27/prepare-money-hooks.py')
money=importlib.util.module_from_spec(spec);spec.loader.exec_module(money)
def sha(p):return hashlib.sha256(p).hexdigest()
def prepare(source,nso,out):
    source,nso,out=map(Path,(source,nso,out))
    expected=json.loads((own/'research/source-pins.json').read_text())
    modifications={
      'main_097.c': [('L_70002bc8ec:;\n','L_70002bc8ec:;\n    { extern void za_items_pump(void*); za_items_pump(c); }\n')],
      'main_333.c': [('L_7000b49360:;\n','L_7000b49360:;\n    { extern void za_items_reset(void); za_items_reset(); }\n')],
      'main_339.c': [('L_7000bba2cc:;\n','L_7000bba2cc:;\n    { extern void za_items_pump(void*); za_items_pump(c); }\n')],
    }
    prepared=[]
    for n,patches in modifications.items():
        raw=(source/n).read_bytes()
        if sha(raw)!=expected[n]:raise ValueError('unapproved source '+n)
        text=raw.decode().replace('\r\n','\n')
        for old,new in patches:
            if text.count(old)!=1:raise ValueError('nonunique anchor '+n)
            text=text.replace(old,new)
        target=out/n
        if target.resolve()==(source/n).resolve() or target.exists():raise ValueError('output must be fresh')
        prepared.append((n,text.encode(),sha(raw)))
    report=money.prepare(source,nso,out)
    target=out/'main_220.c';text=target.read_text()
    anchor='za_cheat_money_component(c->x[23]); }'
    if text.count(anchor)!=1:raise ValueError('money UI anchor is not unique')
    target.write_text(text.replace(anchor,anchor+'\n    { extern void za_items_pump(void*); za_items_pump(c); }'),encoding='utf-8',newline='\n')
    for n in ('main_384.c','main_1035.c'):
        target=out/n;text=target.read_text()
        text=text.replace('za_money_lifecycle_reset();','za_money_lifecycle_reset(); extern void za_items_reset(void); za_items_reset();')
        target.write_text(text,encoding='utf-8',newline='\n')
    for n,data,_ in prepared:(out/n).write_bytes(data)
    manifest=dict(build_id=money.BUILD_ID,units=[dict(name=n,original_sha256=h,patched_sha256=sha(d)) for n,d,h in prepared],game_add_path=['f_700048963c','f_700048994c','f_7000a5a268'],inventory_writes='original game code only',alpha_enabled=False)
    (out/'items-hook-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
if __name__=='__main__':print(json.dumps(prepare(*sys.argv[1:]),indent=2))
