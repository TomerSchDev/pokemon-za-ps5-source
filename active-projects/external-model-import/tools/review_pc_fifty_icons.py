"""Render the effective base/evolution icons for human identity review."""
from pathlib import Path
from io import BytesIO
import hashlib,json,sys
from PIL import Image,ImageDraw,ImageFont


def main():
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1'
    sys.path.insert(0,str(lab/'pokeza-recomp-ps5/third_party/LAS-Randomizer'))
    from RandomizerCore.Tools.bntx_editor.bntx_editor import BNTXEditor
    targets=json.loads((work/'selection.json').read_text())['targets']
    out=work/'icon-review-r2';out.mkdir(exist_ok=True)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
    canvas=Image.new('RGB',(1700,1500),(235,239,245));draw=ImageDraw.Draw(canvas)
    records=[]
    for i,target in enumerate(targets):
        x=(i%5)*340;y=(i//5)*150
        draw.text((x+6,y+4),f"{i+1:02d} {target['name']} > {target['evolution']['name']}",font=font,fill='black')
        for j,model in enumerate((target['model'],target['evolution']['model'])):
            folder=Path(model['model_path']).parent
            icon=Path(model['catalog'].get('icon_path',str(folder/(folder.name+'_00.bntx'))))
            relative=Path('ik_pokemon/data')/icon.parent/'icon'/(icon.stem+'_0.bntx')
            candidates=[p/'romfs'/relative for p in sorted((work/'mods').iterdir()) if p.is_dir() and not p.name.startswith(('_','.'))]
            source=next((p for p in candidates if p.is_file()),None)
            if source is None:raise FileNotFoundError(str(relative))
            raw=source.read_bytes();editor=BNTXEditor();editor.openFile(raw)
            with Image.open(BytesIO(editor.exportTexByIndex(0))) as image:
                image=image.convert('RGBA');canvas.paste(image,(x+5+j*164,y+26),image)
            records.append(dict(key=model['key'],source=str(source),sha256=hashlib.sha256(raw).hexdigest()))
        draw.line((x,y+149,x+340,y+149),fill=(100,110,120))
    canvas.save(out/'cohort-icon-identity.png')
    (out/'icons.json').write_text(json.dumps(dict(records=records,human_review_required=True),indent=1))
    print(json.dumps(dict(images=len(records),sheet=str(out/'cohort-icon-identity.png'))),flush=True)


if __name__=='__main__':main()
