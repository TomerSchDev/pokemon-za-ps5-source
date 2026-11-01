"""Contact sheets of the latest actual PC capture for each target in a batch."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json
from collect_pc_model_results import collect
from run_pc_gallery import ROOT,QA,Image,ImageDraw

def main():
    parser=argparse.ArgumentParser();parser.add_argument('batches',type=int,nargs='+');args=parser.parse_args()
    overview=collect();rows={t['key']:t for t in overview['targets']}
    names=json.loads((QA/'species-names.json').read_text(encoding='utf-8'))
    directory=QA/'wide/reviews';directory.mkdir(exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');output=[]
    for number in args.batches:
        planned=json.loads((QA/'wide'/('wide-import-%03d.json'%number)).read_text(encoding='utf-8'))['targets']
        targets=[rows[t['key']] for t in planned]
        sheet=Image.new('RGB',(1920,((len(targets)+5)//6)*340),'#182236');draw=ImageDraw.Draw(sheet)
        for i,target in enumerate(targets):
            x,y=(i%6)*320,(i//6)*340
            name=names[target['national']]
            draw.text((x+5,y+4),target['key']+' '+name,fill='white')
            if not target.get('frames'):continue
            path=ROOT/'qa/runs'/target['run']/'build/frames'/('frame_%05d.png'%target['frames'][0])
            if not path.exists():continue
            with Image.open(path) as frame:image=frame.convert('RGB')
            tile=image.crop((220,300,970,970));tile.thumbnail((320,255));sheet.paste(tile,(x,y+75))
            title=image.crop((220,210,855,294));title.thumbnail((320,43));sheet.paste(title,(x,y+30))
            color='white' if target['body_visible'] else '#ff907c'
            label='delta='+str(target.get('body_pixels_changed_gt10')) if target['body_visible'] else target['render_status']
            draw.text((x+5,y+18),label,fill=color)
        prefix='import-%03d-%s'%(number,stamp)
        for index,top in enumerate(range(0,sheet.height,1700),1):
            path=directory/(prefix+'-box%02d.jpg'%index)
            sheet.crop((0,top,1920,min(top+1700,sheet.height))).save(path,quality=90);output.append(str(path))
        (directory/(prefix+'-sources.json')).write_text(json.dumps({'targets':targets,'scope':'Actual PC Summary captures; pixel motion is not a full animation or combat pass.'},indent=1),encoding='utf-8')
    print(json.dumps({'sheets':output}),flush=True)

if __name__=='__main__':main()
