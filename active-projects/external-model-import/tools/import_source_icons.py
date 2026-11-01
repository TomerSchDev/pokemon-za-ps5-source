"""Import authentic Sword UI icons where a bridged model has none."""
from pathlib import Path
import argparse
import hashlib
import json
from integrate_model_assets import atomic
from sword_icon_identity import resolve


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path)
    p.add_argument('--repair-sword-icons', action='store_true', help='Re-resolve previously imported Sword icons using the real catalogue')
    args=p.parse_args()
    file=args.build/'integration.json';data=json.loads(file.read_text());added=[];missing=[]
    for model in data['models']:
        if model['icon_authentic'] and not (args.repair_sword_icons and 'icon_pokemon' in model.get('icon_source','')):continue
        n=model['national'];form=model['form'];sex=model['gender'];folder=model['folder'];stem=folder.split('/')[-1]
        try:source,identity=resolve(n,form,sex)
        except FileNotFoundError:missing.append(dict(national=n,form=form,folder=folder));continue
        raw=source.read_bytes();assert raw[:4]==b'BNTX'
        dest=args.build/'all-models/romfs/ik_pokemon/data'/folder/'icon'
        for rare in (0,1):atomic(dest/(stem+'_00_'+str(rare)+'.bntx'),raw)
        model['catalog']['icon_path']=folder+'/'+stem+'_00.bntx';model['icon_authentic']=True
        model['icon_source']=str(source);model['shiny_icon_distinct']=False
        model['icon_identity']=identity
        added.append(dict(national=n,form=form,source=str(source),identity=identity,sha256=hashlib.sha256(raw).hexdigest()))
    atomic(file,json.dumps(data,indent=1).encode())
    atomic(args.build/'icons.json',json.dumps(dict(added=added,missing=missing),indent=1).encode())
    print(json.dumps(dict(icons_added=len(added),missing=len(missing))))


if __name__=='__main__':main()
