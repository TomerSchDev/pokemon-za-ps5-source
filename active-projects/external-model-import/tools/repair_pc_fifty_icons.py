"""Create a PC-only icon correction overlay and compare the copied cohort's icons."""
from pathlib import Path,PureWindowsPath
import hashlib,json
from sword_icon_identity import resolve
from integrate_model_assets import atomic
from build_smoliv_model import Z,encode_checked
from storage_paths import data_root


def main():
    lab=Path(__file__).resolve().parents[3]
    work=lab/'pc-fifty-20261031-r1'
    selection=json.loads((work/'selection.json').read_text())
    overlay=work/'mods/00-icon-identity-r2/romfs'
    provenance={r['folder']:r for r in json.loads((data_root()/'build/all-species-r1/integration.json').read_text())['models']}
    registry_path=Path('ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog')
    registry_schema=Z.catalog_schema()
    registry=registry_schema.decode((work/'mods/all-models/romfs'/registry_path).read_bytes())
    registry_changes=[]
    records=[];unavailable=[];retained=[];seen=set()
    for target in selection['targets']:
        for model in (target['model'],target['evolution']['model']):
            key=model['key']
            if key in seen:continue
            seen.add(key)
            n=model['national'];form=model['form'];gender=model['gender']
            original=provenance[Path(model['model_path']).parent.as_posix()]
            if original['icon_authentic'] and not original.get('icon_source'):
                retained.append(dict(key=key,source=original['source'],reason='Retained converted source icon; no national-number fallback was used'))
                continue
            try:source,identity=resolve(n,form,gender)
            except FileNotFoundError:
                unavailable.append(dict(key=key,source=model['source'],reason='No Sword source; retained existing icon for separate identity review'))
                continue
            raw=source.read_bytes();assert raw[:4]==b'BNTX'
            sha=hashlib.sha256(raw).hexdigest()
            previous_source=source.parent/PureWindowsPath(original['icon_source']).name if original.get('icon_source') else None
            previous_source_sha=hashlib.sha256(previous_source.read_bytes()).hexdigest() if previous_source else None
            model_path=Path(model['model_path']);folder=model_path.parent
            icon=Path(model['catalog'].get('icon_path',str(folder/(folder.name+'_00.bntx'))));stem=icon.stem
            if not model['catalog'].get('icon_path'):
                matches=[r for r in registry['table'] if r.get('species_info',{}).get('species',0)==model['internal']
                         and r.get('species_info',{}).get('form',0)==form and r.get('species_info',{}).get('gender',0)==gender]
                assert len(matches)==1,(key,len(matches))
                matches[0]['icon_path']=icon.as_posix();registry_changes.append(key)
            copies=[]
            for rare in (0,1):
                relative=Path('ik_pokemon/data')/folder/'icon'/(stem+'_'+str(rare)+'.bntx')
                old=work/'mods/all-models/romfs'/relative
                old_sha=hashlib.sha256(old.read_bytes()).hexdigest() if old.is_file() else None
                if rare==0 and previous_source_sha and old_sha!=previous_source_sha:
                    raise ValueError('Installed icon does not match the recorded source: '+key)
                # The existing base is hardlinked by prior runs: never mutate it.
                atomic(overlay/relative,raw)
                assert hashlib.sha256((overlay/relative).read_bytes()).hexdigest()==sha
                copies.append(dict(path=relative.as_posix(),previous_sha256=old_sha,changed=old_sha!=sha))
            records.append(dict(key=key,national=n,source=str(source),identity=identity,sha256=sha,previous_source=str(previous_source) if previous_source else None,previous_source_sha256=previous_source_sha,files=copies))
    if registry_changes:atomic(overlay/registry_path,encode_checked(registry_schema,registry))
    report=dict(overlay=str(overlay),resolved=len(records),changed_models=sum(any(f['changed'] for f in r['files']) for r in records),registry_icons_added=registry_changes,
                retained_original_icons=retained,retained_for_review=unavailable,records=records,runtime_verified=False)
    atomic(work/'icon-identity-repair-r2.json',json.dumps(report,indent=1).encode())
    print(json.dumps(dict(overlay=str(overlay),resolved=report['resolved'],changed_models=report['changed_models'],registry_icons_added=registry_changes,retained_original_icons=len(retained),unresolved=len(unavailable))),flush=True)


if __name__=='__main__':main()
