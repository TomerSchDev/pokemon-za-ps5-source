"""Inspect common-only UI packs not represented by an English variant."""
import json,re
from pathlib import Path
from PIL import Image,ImageDraw
import numpy as np
from za_romfs import Game
from ui_header_extract import ROMFS
from ui_header_codec import inspect_archive,decode_masks
from ui_color_codec import decode_color
LAB=Path(__file__).resolve().parents[1]
out=LAB/'headers/extract-common-extra';out.mkdir(exist_ok=True)
known={a['path'] for a in json.loads((LAB/'headers/reports/full-ui-text-inventory.json').read_text())}
g=Game(ROMFS);records=[];previews=[]
for name,_ in g.packs:
    if not name.startswith('arc/uidata') or not name.endswith('.arc.trpak') or re.search(r'_(eng|kor|fre|ger|ita|spa|ltm|jpn|sch|tch)\.arc\.trpak$',name):continue
    flat=name[len('arc/uidata'):-len('.trpak')]
    paths=[f'ui/data/{flat[:i]}/{flat[i:]}' for i in range(1,len(flat))]
    paths=[p for p in paths if g.has(p)]
    if len(paths)!=1:raise ValueError((name,paths))
    path=paths[0]
    if path in known:continue
    raw=g.read(path);meta=inspect_archive(raw)
    selected={n:m for n,m in meta.items() if any(s in n for s in ('grptext','grptxt','text_','_title','_logo'))}
    record=dict(path=path,textures=selected);records.append(record)
    for n,m in selected.items():
        folder=out/Path(path).stem;folder.mkdir(exist_ok=True);(folder/'archive.arc').write_bytes(raw)
        p=m['payload_offset_in_archive'];payload=raw[p:p+m['payload_size']]
        try:
            if m['format'] in ('0x1d01','0x1e01'):
                ch=decode_masks(m,payload);alpha=np.frombuffer(ch[-1],np.uint8).reshape(m['height'],m['width'])
                rgba=np.full((*alpha.shape,4),255,np.uint8);rgba[:,:,3]=alpha;im=Image.fromarray(rgba)
            else:im=Image.fromarray(decode_color(m,payload))
        except ValueError as e:record.setdefault('unsupported',[]).append([n,str(e)]);continue
        filename=folder/(n.replace('^','_')+'.png');im.save(filename)
        previews.append((str(filename.relative_to(out)),im))
    print(path,len(selected),flush=True)
(out/'inventory.json').write_text(json.dumps(records,indent=2)+'\n')
for page in range((len(previews)+9)//10):
    sheet=Image.new('RGB',(1100,1400),(34,34,34));draw=ImageDraw.Draw(sheet)
    for row,(name,im) in enumerate(previews[page*10:(page+1)*10]):
        draw.text((8,row*140+5),name,fill='orange');im.thumbnail((1000,108));sheet.paste(im,(20,row*140+28),im)
    sheet.save(out/f'contact-{page:02d}.png')
print(json.dumps(dict(archives=len(records),previews=len(previews))))
