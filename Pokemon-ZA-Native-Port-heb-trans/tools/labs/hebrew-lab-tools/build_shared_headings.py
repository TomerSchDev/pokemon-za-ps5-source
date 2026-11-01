"""Compile the inspected common screen headings, preserving native effects/icons."""
import json
import shutil
from pathlib import Path
import numpy as np
from PIL import Image
from build_header_mod import bbox,digest,glyph_mask,make_layers
from ui_header_codec import inspect_archive,decode_masks,encode_masks,patch_archive

LAB=Path(__file__).resolve().parents[1]
BASE=LAB/'headers/build/interface-headings-20261030-r2'
OUTPUT=LAB/'headers/build/interface-headings-20261030-r3'
LABELS={
 '02':('חפצים',0),'05':('משחק מקושר',100),'07':('נתוני הפוקימון',0),
 '08':('מתנה מסתורית',100),'13':('אימון על',0),'14':('קרבות מדורגים',100),
 '15':('קרבות פרטיים',100),'16':('החלפה מקושרת',100),
}

def main():
    if OUTPUT.exists():raise FileExistsError('Preserve previous heading revision')
    pending=[]
    for suffix in ('','_eng'):
        stem='cmn_opguide_body_00'+suffix
        source=LAB/'headers/extract-settings'/stem/'archive.arc'
        original=source.read_bytes();meta=inspect_archive(original);changes={};reports=[];images={}
        for index,(hebrew,keep) in LABELS.items():
            names={'primary':f'grptext_cmn_opguide_title_{index}^s',
                   'glow':f'grptext_cmn_opguide_title_glow_{index}^t',
                   'scan':f'grptext_cmn_opguide_title_scanline_{index}^s'}
            primary=meta[names['primary']];p=primary['payload_offset_in_archive']
            raw=original[p:p+primary['payload_size']]
            old=np.frombuffer(decode_masks(primary,raw)[0],np.uint8).reshape(primary['height'],primary['width'])
            measure=old.copy();measure[:,:keep]=0
            mask,info=glyph_mask(hebrew,primary['width'],primary['height'],bbox(measure))
            for role,name in names.items():
                m=meta[name];start=m['payload_offset_in_archive'];before=original[start:start+m['payload_size']]
                channels=[np.frombuffer(c,np.uint8).reshape(m['height'],m['width']).copy() for c in decode_masks(m,before)]
                layers=make_layers(mask,role,channels,keep,old,7)
                native=encode_masks(m,[a.tobytes() for a in layers],before)
                decoded=[np.frombuffer(c,np.uint8).reshape(m['height'],m['width']) for c in decode_masks(m,native)]
                icon_ok=all(np.array_equal(a[:,:keep],b[:,:keep]) for a,b in zip(channels,decoded))
                error=max(int(np.abs(a.astype(np.int16)-b.astype(np.int16)).max()) for a,b in zip(layers,decoded))
                if not icon_ok or error>37 or len(native)!=len(before):raise ValueError((name,icon_ok,error))
                changes[name]=native;images[name.replace('^','_')]=decoded[-1]
                reports.append(dict(texture=name,role=role,logical=hebrew,typography=info,
                                    preserved_icon_columns=keep,icon_preserved=icon_ok,maximum_quantization_error=error,
                                    source_sha256=digest(before),sha256=digest(native)))
        patched,verification=patch_archive(original,changes,expected_sha256=digest(original))
        relative=Path('ui/data/cmn_opguide')/(stem+'.arc')
        report=dict(source=str(source.relative_to(LAB)),source_sha256=digest(original),
                    file=relative.as_posix(),sha256=digest(patched),bytes=len(patched),
                    textures=reports,verification=verification,visual_qa='pending')
        pending.append((relative,patched,report,images))
    shutil.copytree(BASE,OUTPUT)
    checks=json.loads((OUTPUT/'verification.json').read_text(encoding='utf-8'))
    for relative,patched,report,images in pending:
        target=OUTPUT/'mods/hebrew/romfs'/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(patched)
        preview=OUTPUT/'previews'/relative.stem;preview.mkdir()
        for name,pixels in images.items():Image.fromarray(pixels).save(preview/(name+'.png'))
        checks.append(report)
    (OUTPUT/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(archives=len(checks),new_headings=len(LABELS),new_textures=48,visual_qa='pending')))

if __name__=='__main__':main()
