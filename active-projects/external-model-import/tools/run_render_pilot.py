"""Reuse the existing bounded PC harness with a new isolated data/save root."""
from pathlib import Path
import sys
import os
import json
import subprocess
from storage_paths import data_root
ROOT=data_root()
LAB=ROOT.parent
sys.path.insert(0,str(LAB/'pilot/tools'))
import run_pilot
run_pilot.PILOT=ROOT/'qa'
run_pilot.EXE=LAB/'pilot/runtime/lasrecomp.exe'
snapshot_provenance=None
# Optional read-only mod snapshots; save and cache copies never use hardlinks.
if '--link-mods' in sys.argv:
    sys.argv.remove('--link-mods')
    mods=Path(sys.argv[sys.argv.index('--mods')+1]).resolve()
    junction='--junction-mods' in sys.argv
    if junction:sys.argv.remove('--junction-mods')
    staged=None
    if '--use-staged-mods' in sys.argv:
        at=sys.argv.index('--use-staged-mods');staged=Path(sys.argv[at+1]).resolve();del sys.argv[at:at+2]
        assert staged.is_relative_to((ROOT/'qa/runs').resolve()) and staged.name=='mods' and staged.is_dir()
    copytree=run_pilot.shutil.copytree
    def stage(src,dst,*args,**kwargs):
        if Path(src).resolve()==mods:
            if junction:
                target=Path(dst).resolve();assert target.is_relative_to((ROOT/'qa/runs').resolve()) and not target.exists()
                target.mkdir()
                for child in mods.iterdir():
                    if not child.is_dir():continue
                    link=target/child.name
                    quote=lambda value:"'"+str(value).replace("'","''")+"'"
                    command='New-Item -ItemType Junction -Path '+quote(link)+' -Target '+quote(child)+' | Out-Null'
                    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],check=True,capture_output=True)
                return str(target)
            if staged:
                target=Path(dst).resolve()
                assert target.is_relative_to((ROOT/'qa/runs').resolve()) and target.name=='mods' and not target.exists()
                os.rename(staged,target)
                return str(target)
            kwargs['copy_function']=os.link
        return copytree(src,dst,*args,**kwargs)
    run_pilot.shutil.copytree=stage
    if '--reuse-mod-hashes' in sys.argv:
        at=sys.argv.index('--reuse-mod-hashes');previous=Path(sys.argv[at+1]);del sys.argv[at:at+2]
        previous_data=json.loads(previous.read_text())
        cached=previous_data.get('mods')
        if cached is None:cached={'mods/all-models/romfs/'+name:value['sha256'] for name,value in previous_data['files'].items()}
        run_pilot.MOD_HASH_MANIFEST=cached
        original_sha=run_pilot.sha256
        checked=set()
        if staged:
            for key in cached:
                relative=Path(key).relative_to('mods');parent=relative.parent
                if parent not in checked:
                    assert os.path.samefile(staged/relative,mods/relative),'Staged file identity mismatch'
                    checked.add(parent)
        snapshot_provenance=dict(read_only_mod_hardlinks=True,hash_source=str(previous),NTFS_identity_checked_directories=len(checked),
                                 saves_are_separate_copies=True)
        if junction:snapshot_provenance.update(read_only_mod_hardlinks=False,read_only_mod_junctions=True,source_frozen_during_run=True)
        run_name=sys.argv[1];snapshot=ROOT/'qa/runs'/run_name/'mods'
        def snapshot_sha(path):
            path=Path(path)
            if path.is_relative_to(snapshot):
                relative=path.relative_to(snapshot);source=mods/relative
                assert os.path.samefile(path,source),'Mod snapshot lost file identity'
                key='mods/'+relative.as_posix()
                if key in cached:return cached[key]
            return original_sha(path)
        run_pilot.sha256=snapshot_sha
run_pilot.main()
if snapshot_provenance:
    record_path=ROOT/'qa/runs'/sys.argv[1]/'run.json'
    record=json.loads(record_path.read_text());record['mod_snapshot']=snapshot_provenance
    record_path.write_text(json.dumps(record,indent=1),encoding='utf-8')
