"""Read-only audit of every SARC member in common/English UI packs.

Pack names identify only the first member. Resolve nested archive paths against
the exact file hash using their native layout names, then retain native sources.
"""
import argparse,json,re
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from za_romfs import Game,fnv1a64
from ui_header_extract import sarc_members
from ui_header_codec import inspect_archive,decode_masks
from ui_color_codec import decode_color

LAB=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--game',required=True);a=p.parse_args()
    out=LAB/'headers/extract-nested';out.mkdir(exist_ok=True)
    inventories=[LAB/'headers/reports/full-ui-text-inventory.json',LAB/'headers/extract-common-extra/inventory.json',LAB/'headers/extract-common-extra/inventory-extra-english.json']
    known={r['path'] for f in inventories for r in json.loads(f.read_text(encoding='utf-8'))}
    known_hashes={fnv1a64(p) for p in known};directories={str(Path(p).parent).replace('\\','/') for p in known}
    g=Game(Path(a.game)/'romfs.bin');records=[];seen=set();unknown=[];previews=[]
    packs=[(n,rr) for n,rr in g.packs if n.startswith('arc/uidata') and not re.search(r'_(kor|fre|ger|ita|spa|ltm|jpn|sch|tch)\.',n)]
    for name,rr in packs:
        flat=name[len('arc/uidata'):-len('.trpak')]
        for i in range(1,len(flat)):
            path='ui/data/'+flat[:i]+'/'+flat[i:]
            if g.has(path):directories.add(str(Path(path).parent).replace('\\','/'))
    for pack,rr in packs:
        for r in rr:
            if r['hash'] in seen or r['hash'] in known_hashes:continue
            seen.add(r['hash']);raw=g.unpack(r)
            if not raw.startswith(b'SARC'):continue
            members=list(sarc_members(raw));stems={Path(m['name']).stem for m,b in members if m['name'].endswith('.bflyt')}
            paths={d+'/'+s+suffix+'.arc' for d in directories for s in stems for suffix in ('','_eng')}
            paths=[p for p in paths if fnv1a64(p)==r['hash']]
            if len(paths)!=1:
                unknown.append(dict(pack=pack,hash=hex(r['hash']),layout_stems=sorted(stems)));continue
            path=paths[0];meta=inspect_archive(raw)
            selected={n:m for n,m in meta.items() if any(s in n for s in ('grptext','grptxt','text_','_title','_logo'))}
            if not selected:continue
            folder=out/Path(path).stem;folder.mkdir(exist_ok=True);source=folder/'archive.arc'
            if source.exists() and source.read_bytes()!=raw:raise ValueError('Source changed')
            source.write_bytes(raw);record=dict(path=path,source=str(source.relative_to(LAB)),textures=selected);records.append(record)
            for n,m in selected.items():
                start=m['payload_offset_in_archive'];payload=raw[start:start+m['payload_size']]
                try:
                    if m['format'] in ('0x1d01','0x1e01'):
                        ch=decode_masks(m,payload);alpha=np.frombuffer(ch[-1],np.uint8).reshape(m['height'],m['width'])
                        rgba=np.full((*alpha.shape,4),255,np.uint8);rgba[:,:,3]=alpha;im=Image.fromarray(rgba)
                    else:im=Image.fromarray(decode_color(m,payload))
                except ValueError as e:record.setdefault('unsupported',[]).append([n,str(e)]);continue
                file=folder/(n.replace('^','_')+'.png');im.save(file)
                if path.endswith('_eng.arc') or not g.has(path.replace('.arc','_eng.arc')):
                    previews.append((str(file.relative_to(out)),im))
            print(path,len(selected),flush=True)
    (out/'inventory.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
    (out/'unresolved.json').write_text(json.dumps(unknown,indent=2)+'\n',encoding='utf-8')
    for page in range((len(previews)+9)//10):
        sheet=Image.new('RGB',(1100,1400),(34,34,34));draw=ImageDraw.Draw(sheet)
        for row,(name,im) in enumerate(previews[page*10:(page+1)*10]):
            draw.text((8,row*140+5),name,fill='orange');im.thumbnail((1000,108));sheet.paste(im,(20,row*140+28),im)
        sheet.save(out/f'contact-{page:02d}.png')
    print(json.dumps(dict(archives=len(records),previews=len(previews),unresolved=len(unknown))),flush=True)

if __name__=='__main__':main()
