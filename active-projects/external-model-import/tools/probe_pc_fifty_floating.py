"""Isolated diagnostic: disable one native species' isForceFloat model parameter.

Preserve every other decoded field and original game. This cannot establish a
family pass or serve as a final fix; it only tests the floating-path hypothesis.
"""
import argparse,copy,hashlib,json,os
from pathlib import Path
from build_smoliv_model import Z,encode_checked
from integrate_model_assets import atomic
import za_folder

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--national',type=int,required=True)
    p.add_argument('--mods-root',type=Path,required=True)
    a=p.parse_args()
    assert a.national==661,'Only the proved native flying control is supported'
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1'
    out=a.mods_root.resolve();assert out.is_relative_to(work.resolve()) and not out.exists()
    za_folder.GAME=str(lab/'hebrew-lab/qa-game-reference-20261030/romfs.bin')
    g=za_folder.game();sc=Z.bfbs_schema(Z.MODEL_PARAM);raw=g.read(Z.MODEL_PARAM+'.bin')
    tree=sc.decode(raw);before=copy.deepcopy(tree)
    rows=[r for item in tree['values'] for r in item['root']
          if r.get('devId')==a.national and not r.get('formId',0) and not r.get('sex',0)]
    assert len(rows)==1 and rows[0]['isForceFloat'] is True
    rows[0]['isForceFloat']=False;data=encode_checked(sc,tree)
    rows[0]['isForceFloat']=True;assert tree==before,'Unexpected second change'
    atomic(out/'03-native-floating-control/romfs'/(Z.MODEL_PARAM+'.bin'),data)
    report=dict(diagnostic_only=True,QA_pass_allowed=False,original_game_unchanged=True,
                source_sha256=hashlib.sha256(raw).hexdigest(),sha256=hashlib.sha256(data).hexdigest(),
                species=a.national,only_change=dict(field='isForceFloat',before=True,after=False))
    atomic(out/'floating-probe.json',json.dumps(report,indent=1).encode())
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
