"""Fail closed on swapped identities, missing payloads or changes to native species."""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from integrate_model_assets import Z,ROOT,atomic
from build_smoliv_model import schema
from register_species import key_catalog,contents_schema,CONTENTS
from fbcodec import same


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path);args=p.parse_args()
    integration=json.loads((args.build/'integration.json').read_text());models=integration['models'];assert not integration['errors']
    converted={}
    for kind in ('violet','legacy'):
        conversion=json.loads((ROOT/f'build/{kind}-model-candidates-r1/conversion.json').read_text())
        for rec in conversion['models']:converted[rec['target_folder']]=(kind,rec['sha256'])
    romfs=args.build/'all-models/romfs'
    old_cat=Z.catalog_schema().decode(Z.read(Z.CATALOG))['table']
    new_cat=Z.catalog_schema().decode((romfs/Z.CATALOG).read_bytes())['table']
    cat_bykey={key_catalog(r):r for r in new_cat}
    assert len(cat_bykey)==len(new_cat)
    assert all(same(r,cat_bykey[key_catalog(r)]) for r in old_cat)
    ps=Z.personal_schema();old_personal=ps.decode(Z.read(Z.PERSONAL))['Table'];new_personal=ps.decode((romfs/Z.PERSONAL).read_bytes())['Table']
    assert len(old_personal)==len(new_personal)
    present={r['Info']['SpeciesNational'] for r in new_personal if r.get('IsPresentInGame') and r['Info'].get('SpeciesNational')}
    expected_native={r['Info']['SpeciesNational'] for r in old_personal if r.get('IsPresentInGame') and r['Info'].get('SpeciesNational')}
    assert len(present)==len(expected_native)+len({m['national'] for m in models})
    for a,b in zip(old_personal,new_personal):
        if a.get('IsPresentInGame'):assert same(a,b)
        assert same(a['Info'],b['Info'])
        for k in set(a)|set(b):
            if k not in ('IsPresentInGame','Dex','Learnset','TechnicalMachine','EggMoves','ReminderMoves','Evolutions'):assert same(a.get(k),b.get(k))
    tracks_schema=schema('tracr','ZA/Flatbuffers');materials_schema=schema('trmtr')
    def files_under(root):
        stack=[str(root)]
        while stack:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):yield Path(entry.path)
    def inspect_model(m):
        folder=m['folder'];target=romfs/'ik_pokemon/data'/folder
        candidate=ROOT/'build'/('violet-model-candidates-r1' if m['source']=='violet' else 'legacy-model-candidates-r1')/'romfs/ik_pokemon/data'/folder
        target_files={p.relative_to(target).as_posix() for p in files_under(target)}
        catalog=cat_bykey[(m['internal'],m['form'],m['gender'])]
        for field in ('model_path','material_table_path','config_path'):
            assert catalog[field].startswith(folder+'/'),(m['national'],field)
            assert catalog[field][len(folder)+1:] in target_files,catalog[field]
        checked=0;immutable={}
        for source in files_under(candidate):
            if source.suffix in ('.trmdl','.trmmt','.trmbf','.trmsh','.trskl','.bntx','.tranm','.tracm') and 'locators' not in source.parts:
                dest=target/source.relative_to(candidate)
                # Donor locator skeletons are adapted control data; geometry rig remains source.
                if source.suffix=='.trskl' and source.stem!=Path(catalog['model_path']).stem:continue
                assert dest.relative_to(target).as_posix() in target_files,(m['national'],str(source))
                linked=os.path.samefile(source,dest)
                assert linked or sha(source)==sha(dest),(m['national'],str(source))
                relative=dest.relative_to(romfs).as_posix()
                _,hashes=converted[folder]
                if linked and 'romfs/'+relative in hashes:immutable[relative]=hashes['romfs/'+relative]
                checked+=1
        tracks=tracks_schema.decode((target/(folder.split('/')[-1]+'_base.tracr')).read_bytes())
        for track in tracks['track_list']['list']:
            for resource in track['track_resource'].values():assert resource['filename'] in target_files,(folder,resource)
        if m['source']=='sword':
            for path in target.glob('*.trmtr'):
                for material in materials_schema.decode(path.read_bytes())['materials']:
                    value=next(v for v in material['float_parameter'] if v['float_name']=='LayerMaskScale4')
                    assert value.get('float_value',0)==0
        if m['source']=='arceus':
            for path in target.glob('*.trmtr'):
                for material in materials_schema.decode(path.read_bytes())['materials']:
                    assert next(v for v in material['int_parameter'] if v['int_name']=='CategoryLabel').get('int_value',0)==6
        return checked,dict(national=m['national'],internal=m['internal'],form=m['form'],gender=m['gender'],folder=folder,authentic_candidate_payloads_verified=checked),immutable
    payloads=0;models_checked=[];immutable_hashes={}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for i,(count,record,immutable) in enumerate(pool.map(inspect_model,models),1):
            payloads+=count;models_checked.append(record);immutable_hashes.update(immutable)
            if i%100==0:print('AUDIT MODELS',i,'/',len(models),flush=True)
    cs=contents_schema();old_contents=cs.decode(Z.read(CONTENTS))['entries'];new_contents=cs.decode((romfs/CONTENTS).read_bytes())['entries']
    assert same(new_contents[:len(old_contents)],old_contents)
    assert {r['devNo'] for r in new_contents}=={r['Info']['SpeciesInternal'] for r in new_personal if r.get('IsPresentInGame') and r['Info'].get('SpeciesInternal')}
    def file_record(p):
        relative=p.relative_to(romfs).as_posix();digest=immutable_hashes.get(relative)
        return relative,dict(bytes=p.stat().st_size,sha256=digest or sha(p),
            hash_provenance='converter SHA-256 and identical NTFS file' if digest else 'fresh SHA-256')
    all_files=list(files_under(romfs));manifest={};reused=len(immutable_hashes)
    with ThreadPoolExecutor(max_workers=12) as pool:
        for i,(relative,record) in enumerate(pool.map(file_record,all_files),1):
            manifest[relative]=record
            if i%10000==0:print('AUDIT FILES',i,'/',len(all_files),flush=True)
    report=dict(registered_species=len(present),new_species=len(present-expected_native),models=len(models),
        native_catalog_entries_unchanged=len(old_cat),native_present_species_unchanged=len(expected_native),
        native_pokedex_contents_unchanged=len(old_contents),new_pokedex_contents=len(new_contents)-len(old_contents),
        genuine_candidate_payloads_verified=payloads,models_checked=models_checked,model_errors=integration['errors'],
        immutable_asset_hashes_reused=reused,archive_will_rehash_exact_bytes=True,
        file_count=len(manifest),total_bytes=sum(v['bytes'] for v in manifest.values()),files=manifest,
        all_species_runtime_tested=False,all_encounter_slots_visited=False,ps5_tested=False)
    atomic(args.build/'static-audit.json',json.dumps(report,indent=1).encode())
    print(json.dumps({k:v for k,v in report.items() if k not in ('models_checked','files')},indent=2),flush=True)


if __name__=='__main__':main()
