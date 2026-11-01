from pathlib import Path
import hashlib,json
own=Path(__file__).resolve().parent
root=own.parents[1]
ref=Path(r'C:\Users\Tomer\Documents\Codex\2026-10-22\ns2jb-nintendo-switch-2-switch-1\research\pokeza-pc\update-2.0.2-20261025')
(own/'research/source-pins.json').write_text(json.dumps({n:hashlib.sha256((ref/'aot/main'/n).read_bytes()).hexdigest() for n in ['main_097.c','main_333.c']},indent=2))
data=json.loads((own/'research/items-pkhex.json').read_text())
# Useful items first, then TMs; no ambiguous/illegal ids in the menu.
items=sorted(data['items'],key=lambda x:(x['pocket']==6,x['id']))
(own/'items.inc').write_text(''.join('{%d,%d,%d,%s},\n'%(i['id'],i['cap'],i['pocket'],json.dumps(i['name'])) for i in items))
(own/'research/menu-catalog.json').write_text(json.dumps(items,indent=2))
test=own/'test';test.mkdir(exist_ok=True)
old=own.parent/'cheats-r27'
for n in ['pc_compat.c','run-pc.py']:(test/n).write_bytes((old/'test'/n).read_bytes())
build=(old/'test/build-pc.py').read_text()
build=build.replace('prepare-money-hooks.py','prepare-items-hooks.py')
build=build.replace("str(out/'lasrecomp.def'),'-l',str(out/'lasrecomp.dll.a')","'lasrecomp.def','-l','lasrecomp.dll.a'")
build=build.replace("('main_220.c','main_303.c','main_315.c','main_384.c','main_1035.c')","('main_097.c','main_333.c','main_220.c','main_303.c','main_315.c','main_384.c','main_1035.c')")
build=build.replace("own/'za_money.cpp'","own.parent/'cheats-r27/za_money.cpp',own/'za_items.c'")
build=build.replace("'-I'+str(own),","'-I'+str(own),'-I'+str(own.parent/'cheats-r27'),'-DZA_ITEMS_TRACE=1',")
build=build.replace("('pc_command','pc_compat','za_money')","('pc_command','pc_compat','za_money','za_items')")
(test/'build-pc.py').write_text(build)
print('Prepared pinned hooks, 199-item allowlist and isolated PC builder')
