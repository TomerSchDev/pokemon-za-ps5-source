"""Map assets using each game's real species catalogue, never infer species from pm folder names."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
from source_archives import TrinitySource, FB

HERE = Path(__file__).resolve().parent
from storage_paths import data_root,extracted_root
LAB = data_root().parent
sys.path.insert(0, str(LAB / 'pilot/tools'))
from fbcodec import Schema
import za_schemas as Z

EXTRACTED = extracted_root()
VIOLET = EXTRACTED / 'Pokemon-Violet_01008f6008c5e000_v720896/romfs'
ARCEUS = EXTRACTED / 'Pokemon-Legends-Arceus_01001f5010dfa000_v262144/romfs'
SWORD = EXTRACTED / 'Pokemon-Sword_0100abf008968000_v458752/romfs'


def species_meta_schema(s):
    s.add_table('Species', [('species','u16'),('form','u16'),('gender','u8'),('shiny','u8')])
    s.add_table('Version', [('major','u16'),('minor','u16')])
    s.add_table('Animation', [('name','string'),('path','string')])


def catalogue(data, kind):
    s = Schema()
    species_meta_schema(s)
    fields = [('info',('table','Species')),('model','string')]
    if kind == 'sword':
        fields += [('config','string'),('archive','string'),('animations',('vec',('table','Animation')))]
    else:
        fields += [('materials','string'),('config','string')]
        if kind == 'arceus':
            fields += [('unk','u8'),('animations',('vec',('table','Animation'))),('effects',('vec',('table','Animation'))),('arceus_type','u32')]
        else:
            # We only need the first four fields. Remaining catalogue fields are decoded with ZA's published schema.
            decoded=Z.catalog_schema().decode(data)
            return [dict(info=r.get('species_info',{}), model=r.get('model_path',''), materials=r.get('material_table_path',''),
                         config=r.get('config_path',''), original=r) for r in decoded['table']]
    s.add_table('Entry', fields)
    s.add_table('Catalogue',[('version',('table','Version')),('table',('vec',('table','Entry')))])
    s.root='Catalogue'
    return s.decode(data)['table']


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('out',type=Path)
    a=parser.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    violet=TrinitySource(VIOLET)
    path='pokemon/catalog/catalog/poke_resource_table.trpmcatalog'
    rows={'violet':catalogue(violet.read(path),'violet'),
          'arceus':catalogue((ARCEUS/'bin/pokemon/table/poke_resource_table.trpmcatalog').read_bytes(),'arceus'),
          'sword':catalogue((SWORD/'bin/pokemon/table/poke_resource_table.gfbpmcatalog').read_bytes(),'sword')}
    za=Z.catalog_schema().decode((LAB/'samples/ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog').read_bytes())['table']
    # SV and ZA use Gen 9 internal IDs; LA/Sword use their own national-number mappings.
    personal=Z.personal_schema().decode((LAB/'samples/avalon/data/personal_array.bin').read_bytes())['Table']
    national={r['Info']['SpeciesInternal']:r['Info']['SpeciesNational'] for r in personal if r['Info'].get('SpeciesNational')}
    za_species={r['Info']['SpeciesInternal'] for r in personal if r.get('IsPresentInGame') and r['Info'].get('SpeciesInternal')}
    za_national={national.get(s,s) for s in za_species}
    source_sets={}
    for game,entries in rows.items():
        source_sets[game]=set()
        for row in entries:
            internal=row.get('info',{}).get('species',0)
            row['national_species']=national.get(internal,internal) if game=='violet' else internal
            row['source']=game
            row['model_available']=violet.has('pokemon/data/'+row['model']) if game=='violet' else ((SWORD/row['archive']).is_file() if game=='sword' else (ARCEUS/('bin/archive/pokemon/'+Path(row['model']).stem+'.gfpak')).is_file())
            if row['model_available'] and 1<=row['national_species']<=1025:
                source_sets[game].add(row['national_species'])
    coverage=[]
    for species in range(1,1026):
        sources=[game for game,present in source_sets.items() if species in present]
        coverage.append(dict(national_species=species, native_za=species in za_national, sources=sources,
                             target_internal=next((i for i,n in national.items() if n==species),None)))
    summary=dict(native_za_species=len(za_national), source_species={k:len(v-{0}) for k,v in source_sets.items()},
                 missing_from_all=[r['national_species'] for r in coverage if not r['native_za'] and not r['sources']],
                 available_missing={game:len((present-{0})-za_national) for game,present in source_sets.items()},
                 catalogue_rows={k:len(v) for k,v in rows.items()},
                 coverage_species=len({r['national_species'] for r in coverage if r['native_za'] or r['sources']}))
    (a.out/'source-catalogues.json').write_text(json.dumps(rows,indent=1),encoding='utf-8')
    (a.out/'species-coverage.json').write_text(json.dumps(coverage,indent=1),encoding='utf-8')
    (a.out/'coverage-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)
    print('SMOLIV',json.dumps([r for r in rows['violet'] if r['info'].get('species')==935],indent=2),flush=True)


if __name__=='__main__':
    main()
