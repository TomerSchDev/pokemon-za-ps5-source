"""Read-only audit of previously imported Sword fallback icons against the real catalogue."""
from pathlib import Path,PureWindowsPath
import hashlib,json
from storage_paths import data_root
from sword_icon_identity import resolve


def main():
    root=data_root();build=root/'build/all-species-r1'
    models=json.loads((build/'integration.json').read_text())['models']
    checked=[];missing=[]
    for m in models:
        if not m.get('icon_source') and m['icon_authentic']:continue
        try:source,identity=resolve(m['national'],m['form'],m['gender'])
        except FileNotFoundError:
            missing.append(dict(national=m['national'],form=m['form'],gender=m['gender'],folder=m['folder']))
            continue
        expected=hashlib.sha256(source.read_bytes()).hexdigest()
        stem=Path(m['folder']).name
        installed=build/'all-models/romfs/ik_pokemon/data'/m['folder']/'icon'/(stem+'_00_0.bntx')
        actual=hashlib.sha256(installed.read_bytes()).hexdigest() if installed.is_file() else None
        previous_source=source.parent/PureWindowsPath(m['icon_source']).name if m.get('icon_source') else None
        recorded=hashlib.sha256(previous_source.read_bytes()).hexdigest() if previous_source and previous_source.is_file() else None
        checked.append(dict(national=m['national'],form=m['form'],gender=m['gender'],folder=m['folder'],
                            expected_source=str(source),identity=identity,expected_sha256=expected,installed_sha256=actual,
                            installed_matches_recorded_source=actual==recorded if recorded else None,
                            repair_needed=actual!=expected,missing_installed_icon=actual is None))
    result=dict(read_only=True,models_total=len(models),resolved=len(checked),unresolved=len(missing),
                mismatching_existing=sum(r['repair_needed'] and not r['missing_installed_icon'] for r in checked),
                missing_icons=sum(r['missing_installed_icon'] for r in checked),records=checked,unresolved_records=missing,
                scope='Sword fallback icons only; converted source icons retained')
    out=Path(__file__).resolve().parents[3]/'pc-fifty-20261031-r1/all-imports-icon-audit-r1.json'
    out.write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','unresolved_records')}),flush=True)


if __name__=='__main__':main()
