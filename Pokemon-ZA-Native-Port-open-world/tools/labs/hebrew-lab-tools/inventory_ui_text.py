"""Read-only inventory of English UI image text, with decoded native masks."""
import json,re,sys
from pathlib import Path
from PIL import Image,ImageDraw
from za_romfs import Game
from ui_header_codec import inspect_archive,decode_masks
from ui_header_extract import ROMFS
LAB=Path(__file__).resolve().parents[1]
OUT=LAB/'headers/extract-full'
OUT.mkdir(exist_ok=True)
g=Game(ROMFS)
paths=[]
for name,recs in g.packs:
    if not re.fullmatch(r'arc/uidata.*_eng\.arc\.trpak',name):continue
    flat=name[len('arc/uidata'):-len('.trpak')]
    candidates=['ui/data/'+flat[:i]+'/'+flat[i:] for i in range(1,len(flat))]
    valid=[p for p in candidates if g.has(p)]
    if len(valid)!=1:raise ValueError((name,valid))
    paths.extend([valid[0]])
    generic=valid[0].replace('_eng.arc','.arc')
    if g.has(generic):paths.append(generic)
inventory=[];previews=[]
for path in sorted(set(paths)):
    raw=g.read(path);meta=inspect_archive(raw)
    selected={n:m for n,m in meta.items() if 'grptext' in n or 'text_' in n}
    if not selected:continue
    folder=OUT/Path(path).stem;folder.mkdir(exist_ok=True)
    dest=folder/'archive.arc'
    if dest.exists() and dest.read_bytes()!=raw:raise ValueError('Changed source')
    if not dest.exists():dest.write_bytes(raw)
    inventory.append(dict(path=path,source=str(dest.relative_to(LAB)),textures=selected))
    for n,m in selected.items():
        if '_eng.arc' not in path or any(x in n for x in ['glow','scan','shadow','_ds']):continue
        if m['format'].lower() not in ('0x1d01','0x1e01'):continue
        try:channels=decode_masks(m,raw[m['payload_offset_in_archive']:m['payload_offset_in_archive']+m['payload_size']])
        except ValueError:continue
        mask=Image.frombytes('L',(m['width'],m['height']),channels[-1]);q=folder/(n.replace('^','_')+'.png');mask.save(q)
        previews.append((path,n,mask.copy()))
(LAB/'headers/reports/full-ui-text-inventory.json').write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
for start in range(0,len(previews),12):
    page=Image.new('RGB',(1000,12*140),'#202020');draw=ImageDraw.Draw(page)
    for row,(p,n,im) in enumerate(previews[start:start+12]):
        im.thumbnail((950,95));draw.text((10,row*140+2),f'{start+row}: {Path(p).stem} / {n}',fill='orange');page.paste(im,(20,row*140+30))
    page.save(OUT/f'contact-{start//12:02}.png')
print(json.dumps(dict(archives=len(inventory),previews=len(previews),unsupported=[dict(path=r['path'],name=n,format=m['format']) for r in inventory for n,m in r['textures'].items() if m['format'].lower() not in ('0x1d01','0x1e01')]),indent=2))
