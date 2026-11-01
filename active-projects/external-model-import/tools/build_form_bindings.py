"""Restore alternate-form selectors lost when native base control entries were cloned."""
from pathlib import Path
import copy,json,sys,collections
from storage_paths import data_root
from catalog_inventory import Z
from build_smoliv_model import encode_checked
from fbcodec import same

ROOT=data_root();QA=ROOT/'qa/all-pokemon-20261030-r2'
def build(destination):
    assert destination.resolve().is_relative_to(QA.resolve()) and not destination.exists()
    inventory=json.loads((QA/'inventory-v3.json').read_text(encoding='utf-8'))
    imported={(t['internal'],t['form'],t['gender']) for t in inventory['targets'] if t['imported']}
    sc=Z.catalog_schema();value=sc.decode((ROOT/'build/all-species-r1/all-models/romfs'/Z.CATALOG).read_bytes())
    original=copy.deepcopy(value);changes=[];counts=collections.Counter()
    for entry,before in zip(value['table'],original['table']):
        info=entry['species_info'];key=tuple(info.get(k,0) for k in ('species','form','gender'))
        if key not in imported:
            assert same(entry,before);continue
        if not key[1]:continue
        patches=[]
        for group in ('animations','locators'):
            for ref in entry.get(group,[]):
                if ref.get('form_number',0)!=key[1]:
                    patches.append({'group':group,'old':ref.get('form_number',0),'new':key[1]})
                    ref['form_number']=key[1];counts[group]+=1
        if patches:changes.append({'catalog_key':key,'patches':patches})
    native_count=sum(tuple(e['species_info'].get(k,0) for k in ('species','form','gender')) not in imported for e in value['table'])
    path=destination/'romfs'/Z.CATALOG;path.parent.mkdir(parents=True);path.write_bytes(encode_checked(sc,value))
    report={'changed_entries':len(changes),'references':dict(counts),'native_entries_unchanged':native_count,
            'source_build_unchanged':True,'changes':changes,'runtime_validation':'pending'}
    (destination/'form-bindings.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
    return report

if __name__=='__main__':
    r=build(Path(sys.argv[1]));print({k:v for k,v in r.items() if k!='changes'})
