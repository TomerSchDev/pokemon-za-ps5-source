"""Stage every model variant required by the missing ZA species, retaining source assets/provenance.

This is a source bank, not an installable ZA mod: raw older-game models are never labelled converted.
SV dependencies are resolved by hashed paths; LA/Sword archives are indexed with each original catalogue.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import sys
from catalog_inventory import VIOLET,ARCEUS,SWORD,LAB,Z
from source_archives import TrinitySource,Gfpak,fnv1a64
from folder_assets import resolve_folder

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('out',type=Path)
    parser.add_argument('--stage',action='store_true')
    a=parser.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    rows=json.loads((ROOT/'evidence/source-catalogues.json').read_text(encoding='utf-8'))
    coverage=json.loads((ROOT/'evidence/species-coverage.json').read_text(encoding='utf-8'))
    existing={r['national_species'] for r in coverage if r['native_za']}
    chosen={}
    for game in ('violet','arceus','sword'):
        for row in rows[game]:
            species=row['national_species']
            if 1<=species<=1025 and species not in existing and row.get('model_available',True):
                if species not in chosen:
                    chosen[species]=game
    game=TrinitySource(VIOLET)
    folders={}
    plan=[]
    for row in rows['violet']:
        species=row['national_species']
        if chosen.get(species)!='violet' or not row.get('model_available',True):
            continue
        folder=str(Path(row['model']).parent).replace('\\','/')
        folders.setdefault(folder,[]).append(row)
    for i,(folder,entries) in enumerate(sorted(folders.items()),1):
        paths,unknown,deps=resolve_folder(game,folder)
        record=dict(source='violet',folder=folder,species=sorted({r['national_species'] for r in entries}),
                    catalogue_entries=entries,files=len(paths),bytes=sum(r['size'] for r in paths.values()),
                    unresolved=[dict(hash=f'{r["hash"]:016x}',bytes=r['size'],pack=r['pack']) for r in unknown])
        if a.stage:
            hashes={}
            for path in paths:
                data=game.read(path)
                target=a.out/'violet'/path
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(data)
                hashes[path]=hashlib.sha256(data).hexdigest()
            record['sha256']=hashes
        plan.append(record)
        if i%20==0:
            print(f'VIOLET {i}/{len(folders)} folders, {sum(r["bytes"] for r in plan)} bytes',flush=True)
    # Older games stay as the original, small GFPAK archives in this source stage. Conversion is a distinct phase.
    for source,root in (('arceus',ARCEUS),('sword',SWORD)):
        archives={}
        for row in rows[source]:
            if chosen.get(row['national_species'])!=source or not row.get('model_available',True):
                continue
            archive=row['archive'] if source=='sword' else 'bin/archive/pokemon/'+Path(row['model']).stem+'.gfpak'
            archives.setdefault(archive,[]).append(row)
        for archive,entries in sorted(archives.items()):
            path=root/archive
            record=dict(source=source,archive=archive,species=sorted({r['national_species'] for r in entries}),
                        catalogue_entries=entries,files=1,bytes=path.stat().st_size,conversion_required=True)
            if a.stage:
                data=path.read_bytes()
                target=a.out/source/archive
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(data)
                record['sha256']=hashlib.sha256(data).hexdigest()
            plan.append(record)
    summary=dict(staged=a.stage,models=len(plan),files=sum(r['files'] for r in plan),bytes=sum(r['bytes'] for r in plan),
                 species_by_source=dict(collections.Counter(chosen.values())),species_total=len(chosen),
                 missing_species=[r['national_species'] for r in coverage if not r['native_za'] and not r['sources']])
    (a.out/'source-bank.json').write_text(json.dumps(dict(summary=summary,models=plan),indent=1),encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    main()
