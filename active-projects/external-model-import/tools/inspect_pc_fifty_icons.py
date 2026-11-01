"""Decode original dump icons for asset-identity diagnostics; no image synthesis or edits."""
from pathlib import Path
from io import BytesIO
import hashlib,json,sys
from storage_paths import extracted_root

def main():
    lab=Path(__file__).resolve().parents[3]
    sys.path.insert(0,str(lab/'pokeza-recomp-ps5/third_party/LAS-Randomizer'))
    from RandomizerCore.Tools.bntx_editor.bntx_editor import BNTXEditor
    from PIL import Image
    root=extracted_root()/'Pokemon-Sword_0100abf008968000_v458752/romfs/bin/appli/icon_pokemon'
    out=lab/'pc-fifty-20261031-r1/icon-diagnostic-r1';out.mkdir(exist_ok=True)
    records=[]
    for number in (743,835,836,907,908):
        source=next(root.glob('poke_icon_%04d_00*_n.bntx'%number))
        raw=source.read_bytes();editor=BNTXEditor();editor.openFile(raw)
        tex=editor.bntx.textures[0]
        dds=editor.exportTexByIndex(0)
        target=out/(source.stem+'.png')
        with Image.open(BytesIO(dds)) as picture:picture.save(target)
        records.append({'source':str(source),'sha256':hashlib.sha256(raw).hexdigest(),'texture':tex.name,'width':tex.width,'height':tex.height,'format':tex.format_,'png':str(target)})
    (out/'diagnostic.json').write_text(json.dumps(records,indent=1),encoding='utf-8')
    print(json.dumps(records),flush=True)

if __name__=='__main__':main()
