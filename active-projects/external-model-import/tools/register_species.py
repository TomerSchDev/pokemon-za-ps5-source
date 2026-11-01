"""Merge genuine model bridges into independent species, personal and Pokedex tables."""
from pathlib import Path
import argparse
import copy
import json
import struct
import sys
from integrate_model_assets import ROOT,atomic,Z
from build_smoliv_model import encode_checked
from source_archives import TrinitySource
from catalog_inventory import VIOLET,SWORD,ARCEUS
import za_folder
from fbcodec import Schema,same
from movesets import is_dummied
sys.path.insert(0,str(ROOT.parents[1]/'hebrew-lab/tools'))
import gfmsg

CONTENTS='world/exl/pokedex_contents_data/pokedex_contents_data/pokedex_contents_data.bin'


def contents_schema():
    s=Schema();s.add_table('Entry',[('id','u32'),('devNo','u32'),('book','u32')])
    s.add_table('Contents',[('entries',('vec',('table','Entry')))]);s.root='Contents';return s


class TextSources:
    def __init__(self):self.violet=None;self.cache={}
    def get(self,game,suffix):
        key=(game,suffix)
        if key not in self.cache:
            if game=='violet':
                if self.violet is None:self.violet=TrinitySource(VIOLET)
                reader=self.violet.read;base='message/dat/English/common/'
            else:
                folder=SWORD if game=='sword' else ARCEUS
                reader=lambda p:(folder/p).read_bytes();base='bin/message/English/common/'
            path=base+'zukan_comment_'+suffix
            msg=gfmsg.MsgFile(reader(path+'.dat'));tbl=gfmsg.read_tbl(reader(path+'.tbl'))
            self.cache[key]={name:gfmsg.decode_units(msg.lines[i]) for i,(_,name) in enumerate(tbl) if i<len(msg.lines)}
        return self.cache[key]
    def description(self,model,suffix):
        n=model['national'];internal=model['internal'];form=model['form']
        order=list(dict.fromkeys([model['source'],'violet','sword','arceus']))
        for game in order:
            number=internal if game=='violet' else n
            for version in (suffix,'A','B'):
                text=self.get(game,version).get(f'ZKN_COMMENT_{version}_{number:03d}_{form:03d}','')
                if not text:text=self.get(game,version).get(f'ZKN_COMMENT_{version}_{number:03d}_000','')
                if text and '{VAR ' not in text:
                    return text,dict(game=game,version=version,number=number,source_form=form)
        return None,None


def key_catalog(e):
    r=e['species_info'];return tuple(r.get(k,0) for k in ('species','form','gender'))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path);args=p.parse_args()
    integration=json.loads((args.build/'integration.json').read_text())
    models=integration['models'];assert models
    romfs=args.build/'all-models/romfs'
    donors={r['species']:r for r in json.loads((ROOT/'evidence/native-control-donors.json').read_text())['donors']}
    keys={};duplicates=[]
    for m in models:
        key=(m['internal'],m['form'],m['gender'])
        if key in keys:duplicates.append(dict(key=key,kept=keys[key]['folder'],skipped=m['folder']))
        else:keys[key]=m
    models=list(keys.values())
    # A cloned base donor has form selector 0. Each alternate model must select
    # its own animations and locator set, as native alternate catalog entries do.
    for model in models:
        if model['form']:
            for group in ('animations','locators'):
                for reference in model['catalog'].get(group,[]):reference['form_number']=model['form']
    personal_schema=Z.personal_schema();personal=personal_schema.decode(Z.read(Z.PERSONAL));original=copy.deepcopy(personal)
    activated={(m['internal'],m['form']) for m in models}
    native_present={(r['Info']['SpeciesInternal'],r['Info'].get('Form',0)) for r in original['Table'] if r.get('IsPresentInGame')}
    all_present=activated|native_present
    # Stable across sample/full builds; preserve the already shipped Smoliv No.365.
    coverage=json.loads((ROOT/'evidence/species-coverage.json').read_text())
    supported=sorted(r['national_species'] for r in coverage if not r['native_za'] and r['sources'] and r['target_internal'] is not None and r['national_species']!=928)
    dex={n:366+i for i,n in enumerate(supported)};dex[928]=365
    changed=[]
    for i,row in enumerate(personal['Table']):
        info=row['Info'];key=(info['SpeciesInternal'],info.get('Form',0))
        if key not in activated:continue
        assert key not in native_present
        row['IsPresentInGame']=True;row['Dex']={'Index':dex[info['SpeciesNational']],'Group':0}
        row['Learnset']=[m for m in row.get('Learnset',[]) if not is_dummied(m['Move'])]
        for k in ('TechnicalMachine','EggMoves','ReminderMoves'):row[k]=[m for m in row.get(k,[]) if not is_dummied(m)]
        row['Evolutions']=[e for e in row.get('Evolutions',[]) if (e.get('SpeciesInternal',0),e.get('Form',0)) in all_present]
        changed.append(i)
    assert all(same(a,b) for i,(a,b) in enumerate(zip(original['Table'],personal['Table'])) if i not in changed)
    atomic(romfs/Z.PERSONAL,encode_checked(personal_schema,personal))
    cat_schema=Z.catalog_schema();catalog=cat_schema.decode(Z.read(Z.CATALOG));native_catalog=copy.deepcopy(catalog['table'])
    native_keys={key_catalog(r):r for r in native_catalog}
    assert not set(keys).intersection(native_keys)
    catalog['table']+= [m['catalog'] for m in models];catalog['table'].sort(key=key_catalog)
    assert len({key_catalog(r) for r in catalog['table']})==len(catalog['table'])
    assert all(same(native_keys[k],r) for r in catalog['table'] if (k:=key_catalog(r)) in native_keys)
    atomic(romfs/Z.CATALOG,encode_checked(cat_schema,catalog))
    table_counts={}
    for path,ds,fs in ((Z.MODEL_PARAM,'devId','formId'),(Z.MOVEMENT_PARAM,'devNo','formNo')):
        s=Z.bfbs_schema(path);table=s.decode(Z.read(path+'.bin'))
        def key(db):return tuple(db['root'][0].get(k,0) for k in (ds,fs,'sex'))
        native={key(db):copy.deepcopy(db) for db in table['values']}
        for m in models:
            k=(m['internal'],m['form'],m['gender'])
            if k in native:continue
            donor=donors[m['donor_species']]
            db=copy.deepcopy(donor['model_param' if path==Z.MODEL_PARAM else 'movement'])
            row=db['root'][0];row[ds],row[fs],row['sex']=k
            table['values'].append(db)
        table['values'].sort(key=key)
        assert len({key(db) for db in table['values']})==len(table['values'])
        assert all(same(native[k],db) for db in table['values'] if (k:=key(db)) in native)
        atomic(romfs/(path+'.bin'),encode_checked(s,table));table_counts[path]=len(table['values'])-len(native)
    g=za_folder.game()
    for base,lst in ((Z.WILD_SINGLE,Z.WILD_SINGLE_LIST),(Z.CHARA_ANIME,Z.CHARA_ANIME_LIST)):
        ls=Z.name_list_schema();names=ls.decode(g.read(lst));old_names=list(names['names'])
        for m in models:
            name=f"{m['internal']:04d}_{m['form']:02d}_{m['gender']:02d}"
            if name in names['names']:continue
            source=f"{m['donor_species']:04d}_00_00"
            for ext in ('.bin','.bfbs'):atomic(romfs/(base+name+ext),g.read(base+source+ext))
            names['names'].append(name)
        names['names'].sort();assert set(old_names)<=set(names['names'])
        atomic(romfs/lst,encode_checked(ls,names))
    s=contents_schema();content=s.decode(Z.read(CONTENTS));original_content=copy.deepcopy(content['entries'])
    added=[]
    for n in sorted({m['national'] for m in models},key=lambda n:dex[n]):
        m=next(m for m in models if m['national']==n)
        entry={'id':max(r['id'] for r in content['entries'])+1,'devNo':m['internal']}
        content['entries'].append(entry);added.append(dict(national=n,dex=dex[n],**entry))
    assert same(content['entries'][:len(original_content)],original_content)
    atomic(romfs/CONTENTS,encode_checked(s,content))
    sources=TextSources();texts=[];missing=[];metadata_fallbacks=[]
    names_message=gfmsg.MsgFile(Z.read('ik_message/dat/English/common/monsname.dat'))
    type_names=['Normal','Fighting','Flying','Poison','Ground','Rock','Bug','Ghost','Steel','Fire','Water','Grass','Electric','Psychic','Ice','Dragon','Dark','Fairy']
    personal_bykey={(r['Info']['SpeciesInternal'],r['Info'].get('Form',0)):r for r in personal['Table']}
    for suffix in ('A','B'):
        path='ik_message/dat/English/common/zukan_comment_'+suffix
        dat=gfmsg.MsgFile(Z.read(path+'.dat'));tbl=gfmsg.read_tbl(Z.read(path+'.tbl'))
        assert len(tbl)==len(dat.lines)+1 and tbl[-1][1]=='msg_zukan_comment_'+suffix+'_max'
        old_lines=copy.deepcopy(dat.lines);old_tbl=list(tbl)
        index_by_name={name:i for i,(_,name) in enumerate(tbl)}
        for m in models:
            if m['gender']:continue
            label=f"ZKN_COMMENT_{suffix}_{m['internal']:03d}_{m['form']:03d}"
            text,provenance=sources.description(m,suffix)
            if text is None:
                native_row=personal_bykey[(m['internal'],m['form'])]
                name=gfmsg.decode_units(names_message.lines[m['internal']])
                types=list(dict.fromkeys(type_names[native_row.get(k,0)] for k in ('Type1','Type2')))
                text=name+' is a '+('- and '.join(types))+'-type Pokémon.'
                provenance=dict(generated_from_native_name_and_types=True,original_flavor_unavailable_in_supplied_games=True)
                metadata_fallbacks.append(label)
            if label in index_by_name:
                index=index_by_name[label]
                old_text=gfmsg.decode_units(dat.lines[index])
                if old_text and '{VAR ' not in old_text:continue
                dat.lines[index]=gfmsg.encode_text(text)
            else:
                index=len(dat.lines);dat.lines.append(gfmsg.encode_text(text));dat.params.append(0)
                tbl.insert(index,(gfmsg.fnv1a64(label),label));index_by_name[label]=index
            texts.append(dict(label=label,index=index,text=text,provenance=provenance))
        encoded=b'AHTB'+struct.pack('<I',len(tbl))
        for h,name in tbl:
            b=name.encode()+b'\0';encoded+=struct.pack('<QH',h,len(b))+b
        assert gfmsg.read_tbl(encoded)==tbl
        atomic(romfs/(path+'.dat'),dat.encode());atomic(romfs/(path+'.tbl'),encoded)
    # Keep Smoliv's proven ordinary Wild Zone 1 encounter; the broad spawning
    # expansion is a separate change, so story/tutorial encounters stay native.
    if any(m['internal']==935 for m in models):
        es=Z.bfbs_schema(Z.ENCOUNT);enc=es.decode(Z.read(Z.ENCOUNT+'.bin'))
        hit=next(r for db in enc['values'] for r in db['root'] if r.get('id')=='ect_a0102_w01_v01_z659')
        hit['devNo']=935;atomic(romfs/(Z.ENCOUNT+'.bin'),encode_checked(es,enc))
    report=dict(species=len({m['national'] for m in models}),model_variants=len(models),
        native_catalog_entries_preserved=len(native_catalog),native_personal_rows_preserved=len(personal['Table'])-len(changed),
        personal_rows_activated=len(changed),parameter_rows_added=table_counts,pokedex_added=added,
        native_pokedex_contents_preserved=len(original_content),description_entries=texts,missing_descriptions=missing,
        descriptions_using_metadata_summary=metadata_fallbacks,
        duplicates=duplicates,runtime_tested=False,all_species_have_wild_spawns=False,
        no_native_species_replaced=True)
    (args.build/'registration.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('description_entries','pokedex_added','duplicates')},indent=2),flush=True)


if __name__=='__main__':main()
