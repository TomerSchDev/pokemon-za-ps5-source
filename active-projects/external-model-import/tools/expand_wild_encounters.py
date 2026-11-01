"""Experimental spawn profile using existing outside-wild-zone encounter slots.

All story/tutorial rows and at least one original row per native species/form are
preserved. A table assignment is not proof that every slot has been visited.
"""
from pathlib import Path
import argparse
import collections
import copy
import json
import math
from integrate_model_assets import Z,atomic,ROOT
from build_smoliv_model import encode_checked
from fbcodec import same


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path);args=p.parse_args()
    models=json.loads((args.build/'integration.json').read_text())['models']
    base={}
    for m in models:
        if not m['form'] and not m['gender']:base[m['internal']]=m
    personal=Z.personal_schema().decode(Z.read(Z.PERSONAL))['Table']
    byid={(r['Info']['SpeciesInternal'],r['Info'].get('Form',0)):r for r in personal}
    es=Z.bfbs_schema(Z.ENCOUNT);enc=es.decode(Z.read(Z.ENCOUNT+'.bin'))
    original=copy.deepcopy(enc);rows=[r for db in enc['values'] for r in db['root']]
    remaining=collections.Counter((r.get('devNo',0),r.get('formNo',0)) for r in rows)
    candidates=[r for r in rows if r.get('id','').startswith('ect_outzone_')]
    assert len(candidates)==905
    available=list(candidates);assignments=[]
    for internal,m in sorted(base.items(),key=lambda v:v[1]['national']):
        if internal==935:continue  # Keep the already proven Smoliv Wild Zone 1 slot.
        source=byid[(internal,0)];info=source['Info']
        def score(r):
            if remaining[(r.get('devNo',0),r.get('formNo',0))]<=1:return -1e20
            target=byid[(r['devNo'],r.get('formNo',0))];ti=target['Info']
            st={source.get('Type1',0),source.get('Type2',0)};tt={target.get('Type1',0),target.get('Type2',0)}
            result=5*(ti.get('BodyType')==info.get('BodyType'))+2*len(st&tt)
            result+=5*(r['devNo']==m['donor_species'])
            result-=abs(math.log(max(1,info.get('Height',1))/max(1,ti.get('Height',1))))
            result-=8*((10 in st)!=(10 in tt));result-=8*((2 in st)!=(2 in tt))
            return result
        row=max(available,key=lambda r:(score(r),r['id']))
        assert score(row)>-1e19,'Not enough slots preserving native identities'
        before=copy.deepcopy(row);remaining[(row['devNo'],row.get('formNo',0))]-=1;available.remove(row)
        row['devNo']=internal;row['formNo']=0;row['sex']=-1
        assignments.append(dict(national=m['national'],internal=internal,id=row['id'],
            previous_species=before['devNo'],minLevel=row.get('minLevel'),maxLevel=row.get('maxLevel')))
    if 935 in base:
        row=next(r for r in rows if r['id']=='ect_a0102_w01_v01_z659')
        row['devNo']=935
        assignments.append(dict(national=928,internal=935,id=row['id'],previous_species=659,minLevel=row['minLevel'],maxLevel=row['maxLevel']))
    native_identities={(r.get('devNo',0),r.get('formNo',0)) for db in original['values'] for r in db['root']}
    new_identities={(r.get('devNo',0),r.get('formNo',0)) for r in rows}
    assert native_identities<=new_identities
    changed_ids={r['id'] for r in assignments}
    old_byid={r['id']:r for db in original['values'] for r in db['root']}
    assert all(same(old_byid[r['id']],r) for r in rows if r['id'] not in changed_ids)
    assert {r['internal'] for r in assignments}==set(base)
    atomic(args.build/'all-models/romfs'/(Z.ENCOUNT+'.bin'),encode_checked(es,enc))
    report=dict(new_species_assigned=len(assignments),native_species_form_identities_preserved=len(native_identities),
                unchanged_rows=len(rows)-len(assignments),assignments=assignments,
                story_and_tutorial_rows_unchanged=True,all_assigned_slots_runtime_visited=False,
                profile='Experimental existing outside-wild-zone slots; map availability requires field QA')
    atomic(args.build/'spawns.json',json.dumps(report,indent=1).encode())
    print(json.dumps({k:v for k,v in report.items() if k!='assignments'},indent=2),flush=True)


if __name__=='__main__':main()
