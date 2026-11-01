"""Fetch only public format descriptions and compile reflection schemas with official flatc."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'ref'
BASE='https://raw.githubusercontent.com/pkZukan/PokeDocs/main/'


def fetch(path):
    target=REF/path
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(urllib.request.urlopen(BASE+path).read())
    for name in re.findall(r'include\s+"([^"]+)"',target.read_text(encoding='utf-8-sig')):
        fetch(str(Path(path).parent/name).replace('\\','/'))
    return target


def main():
    names=['SV/Flatbuffers/model/'+n+'.fbs' for n in ('trmdl','trmsh','trmbf','trmtr','trmmt','trskl','trpokecfg')]
    names+=['SV/Flatbuffers/animation/'+n+'.fbs' for n in ('tracr','tracm','tracn','tracl','tracp','tracs','tralk','trmdt','traef')]
    names+=['LA/Flatbuffers/Model/'+n+'.fbs' for n in ('trmdl','trmsh','trmtr','trskl','trmbf','trmmt','trpokecfg')]
    names+=['SWSH/Flatbuffers/Model/gfbmdl.fbs','ZA/Flatbuffers/tracr.fbs']
    provenance=[]
    for path in names:
        target=fetch(path)
        subprocess.run([str(ROOT/'tools/bin/flatc.exe'),'-b','--schema','-o',str(target.parent),str(target)],check=True,capture_output=True)
        provenance.append(dict(source=BASE+path,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    (REF/'provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    print('Compiled',len(names),'format schemas',flush=True)


if __name__=='__main__':
    main()
