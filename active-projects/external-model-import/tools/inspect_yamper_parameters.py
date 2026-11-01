"""Inspect native and effective movement/model parameters for the battle probe."""
from pathlib import Path
import argparse,json
from build_smoliv_model import Z
import za_folder

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--species',type=int,nargs='+',default=[172,706,835,836])
    parser.add_argument('--label',default='yamper')
    a=parser.parse_args()
    assert a.label.replace('-','').isalnum()
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1'
    za_folder.GAME=str(lab/'hebrew-lab/qa-game-reference-20261030/romfs.bin');g=za_folder.game();result={}
    catalogs={}
    for stem in ('pokemon/poke_model_param','character/pokemon/poke_movement_param'):
        p='param_chr/catalog/bin/sources/flatbuffers/'+stem+'.data.bin'
        catalogs[p]={'exists':g.has(p)}
        if g.has(p):
            value=Z.name_list_schema().decode(g.read(p));catalogs[p].update(count=len(value['names']),examples=value['names'][:12],yamper_present='0835_00_00' in value['names'])
    result['catalogs']=catalogs
    print(json.dumps(catalogs),flush=True)
    for path,key in ((Z.MODEL_PARAM,'devId'),(Z.MOVEMENT_PARAM,'devNo')):
        s=Z.bfbs_schema(path);result[path]={}
        for label,data in (('native',g.read(path+'.bin')),('effective',(work/'mods/all-models/romfs'/(path+'.bin')).read_bytes())):
            rows=s.decode(data)['values']
            result[path][label]={str(n):[v for v in rows if v['root'][0].get(key,0)==n] for n in a.species}
    report=work/(a.label+'-parameters-inspection-r1.json')
    assert not report.exists(),'Keep prior inspection evidence'
    report.write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({'report':str(report)}),flush=True)

if __name__=='__main__':main()
