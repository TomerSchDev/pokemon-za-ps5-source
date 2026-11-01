"""Assemble observed checkpoint evidence; never runs or changes the game."""
from pathlib import Path
import hashlib,json,shutil
from datetime import datetime,timezone
root=Path(__file__).resolve().parent
q=root/'quickstart';ev=q/'evidence';ev.mkdir(exist_ok=True)
checkpoint='Daytime city street outside the Pokemon Center, Mission 03 before Wild Zone 1'
starters={}
for name,run,shot,species in [('Totodile','45-city-totodile-30',2,158),('Chikorita','47-city-chikorita',2,152),('Tepig','48-city-tepig',2,498)]:
    save=q/'templates'/name/'main'
    pic=root/'runs'/run/'build'/f'live-{shot:06}.png'
    assert pic.is_file() and pic.stat().st_size>0
    shutil.copy2(pic,ev/f'{name.lower()}-city.png')
    starters[name]=dict(species=species,level=7,sha256=hashlib.sha256(save.read_bytes()).hexdigest(),game_reload_verified=True,
        movement_verified=True,evidence=f'evidence/{name.lower()}-city.png',run=run,
        verification_scope='Loaded this fixed template in the game, visually checked starter icon and movement in city; not a full story playthrough')
manifest=dict(schema=1,checkpoint=checkpoint,game_version='1.0.0',trainer='Test',later_tutorials_remain=True,
    base_save_sha256='4f2f95e2a9479aec45255928c825ccb04f2d4f9acdea26608e45a8a34d183cf3',starters=starters)
(q/'templates.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
for run,label in [('45-city-totodile-30','experimental-30'),('46-city-totodile-60','experimental-forced60'),('49-city-stable-30','stable-30')]:
    src=root/'runs'/run/'benchmark.json'
    if src.is_file():shutil.copy2(src,ev/f'{label}-benchmark.json')
for src in ['city-inspect.json','city-chikorita-reopen.json','city-tepig-reopen.json']:
    d=json.loads((root/'save-lab'/src).read_text(encoding='utf-8-sig'))
    small={k:d[k] for k in ['sha256','hash_valid','roundtrip_hash_valid','roundtrip_identical','trainer','revision','coordinates','party']}
    (ev/src).write_text(json.dumps(small,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
