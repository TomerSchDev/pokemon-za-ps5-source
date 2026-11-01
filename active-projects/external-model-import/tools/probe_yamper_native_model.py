"""PC diagnostic only: temporarily use the native control donor model for species 835."""
from pathlib import Path
import argparse,copy,hashlib,json,os,struct
from build_smoliv_model import Z,encode_checked,schema as control_schema
from integrate_model_assets import atomic
from storage_paths import data_root
from source_archives import FB

def parameter_summary(data):
    """Read stable TRACP fields; retain unknown native extensions as raw bytes."""
    fb=FB(data);outer=fb.table(fb.u32(0));node=fb.table(outer[0]+fb.u32(outer[0]));result={}
    specs=(('animations',('u32','u32','u32')),('moves',('f32','f32','f32')),('switches',('bool',)),('triggers',()))
    for group,(name,kinds) in enumerate(specs):
        rows=[]
        if group<len(node) and node[group]:
            count,first=fb.vec(node[group])
            for i in range(count):
                ptr=first+i*4;obj=ptr+fb.u32(ptr);fields=fb.table(obj)
                row=dict(name=fb.string(fields[0]))
                for j,kind in enumerate(kinds,1):
                    at=fields[j] if j<len(fields) else 0
                    row['field_'+str(j)]=(bool(data[at]) if kind=='bool' else struct.unpack_from('<f' if kind=='f32' else '<I',data,at)[0]) if at else (False if kind=='bool' else 0)
                vt=obj-struct.unpack_from('<i',data,obj)[0];end=obj+struct.unpack_from('<H',data,vt+2)[0]
                for j in range(len(kinds)+1,len(fields)):
                    at=fields[j]
                    if at:
                        after=min([v for v in fields if v and v>at]+[end])
                        row['unknown_field_'+str(j)+'_hex']=data[at:after].hex()
                rows.append(row)
        result[name]=rows
    return dict(root_node=result)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--national',type=int,default=835)
    parser.add_argument('--donor',type=int,default=172)
    parser.add_argument('--mods-root',type=Path)
    parser.add_argument('--native-stock',action='store_true',help='Use only the stock catalog; do not include the imported cohort')
    parser.add_argument('--inspect-controls',action='store_true')
    parser.add_argument('--module-only',choices=('state','parameter','layer','motion_detector'))
    parser.add_argument('--category-zero',action='store_true')
    parser.add_argument('--component',choices=('all','animations','support','model'),default='all')
    a=parser.parse_args()
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1'
    relative=Path('ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog')
    current=work/'mods/00-icon-identity-r2/romfs'/relative
    schema=Z.catalog_schema()
    import za_folder
    za_folder.GAME=str(lab/'hebrew-lab/qa-game-reference-20261030/romfs.bin');game=za_folder.game()
    table=schema.decode(game.read(str(relative).replace('\\','/')) if a.native_stock else current.read_bytes())
    donor=next(r for r in table['table'] if r['species_info'].get('species',0)==a.donor
               and not r['species_info'].get('form',0) and not r['species_info'].get('gender',0))
    matches=[i for i,r in enumerate(table['table']) if r['species_info'].get('species',0)==a.national
             and not r['species_info'].get('form',0) and not r['species_info'].get('gender',0)]
    assert len(matches)==1
    original=table['table'][matches[0]];replacement=copy.deepcopy(donor)
    if a.module_only or a.category_zero:
        assert a.donor==706 and a.mods_root
        assert (a.native_stock and a.national==661) or (not a.native_stock and a.national in (519,520) and a.category_zero)
        out=a.mods_root.resolve();assert out.is_relative_to(work.resolve()) and not out.exists()
        def read_effective(path):
            local=work/'mods/all-models/romfs'/path
            return local.read_bytes() if not a.native_stock and local.is_file() else game.read(path)
        def module_path(entry):
            paths=[r['path'] for r in entry['animations'] if r['path'].endswith('.tracn')]
            assert len(paths)==1
            prefix='ik_pokemon/data/'+paths[0]
            local=work/'mods/all-models/romfs'/prefix
            actual=prefix if game.has(prefix) or (not a.native_stock and local.is_file()) else prefix[:-6]+'_base.tracn'
            items=control_schema('tracn','SV/Flatbuffers/animation').decode(read_effective(actual))['list']
            rows=[r for r in items if r['animation_name']==('parameter' if a.category_zero else a.module_only)];assert len(rows)==1
            return str(Path(actual).parent/rows[0]['filename']).replace('\\','/')
        source=module_path(donor);target=module_path(original)
        raw=read_effective(source);old=read_effective(target)
        source_stem=Path(donor['model_path']).stem.encode();target_stem=Path(original['model_path']).stem.encode()
        if not a.category_zero:assert len(source_stem)==len(target_stem)
        data=old if a.category_zero else raw.replace(source_stem,target_stem)
        if a.category_zero:
            def category_offset(blob):
                fb=FB(blob);outer=fb.table(fb.u32(0));node=fb.table(outer[0]+fb.u32(outer[0]));n,first=fb.vec(node[0]);matches=[]
                for i in range(n):
                    at=first+i*4;fields=fb.table(at+fb.u32(at))
                    if fb.string(fields[0])=='category_int':
                        matches.append(fields[3] if len(fields)>3 and fields[3] else None)
                assert len(matches)==1
                return matches[0]
            at=category_offset(old);donor_at=category_offset(raw)
            assert at is not None and struct.unpack_from('<I',old,at)[0]==2
            assert donor_at is None or struct.unpack_from('<I',raw,donor_at)[0]==0
            patched=bytearray(old);struct.pack_into('<I',patched,at,0);data=bytes(patched)
            assert data[:at]==old[:at] and data[at+4:]==old[at+4:] and len(data)==len(old)
        else:assert len(data)==len(raw)
        if not a.native_stock:
            out.mkdir()
            import _winapi
            for name in ('00-icon-identity-r2','all-models'):
                base=(work/'mods'/name).resolve();_winapi.CreateJunction(str(base),str(out/name))
                assert os.path.samefile(base,out/name)
        atomic(out/'03-native-module-control/romfs'/target,data)
        report=dict(diagnostic_only=True,QA_pass_allowed=False,module='parameter.category_int.field_3:2->0' if a.category_zero else a.module_only,
                    original_game_unchanged=True,source=source,target=target,
                    source_sha256=hashlib.sha256(raw).hexdigest(),original_sha256=hashlib.sha256(old).hexdigest(),
                    sha256=hashlib.sha256(data).hexdigest(),namespace_replacements=raw.count(source_stem),
                    geometry_and_motion_clips_unchanged=True)
        atomic(out/'module-probe.json',json.dumps(report,indent=1).encode())
        print(json.dumps(report),flush=True)
        return
    if a.inspect_controls:
        modules={}
        for label,entry in (('original',original),('donor',donor)):
            values=[]
            for item in entry.get('animations',[]):
                path='ik_pokemon/data/'+item['path']
                if path.endswith('.tracn'):
                    actual=path if game.has(path) else path[:-6]+'_base.tracn'
                    raw=game.read(actual)
                    value=control_schema('tracn','SV/Flatbuffers/animation').decode(raw)
                    hashes={}
                    for module in value['list']:
                        data=game.read(str(Path(actual).parent/module['filename']).replace('\\','/'))
                        hashes[module['animation_name']]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                        if module['animation_name'] in ('parameter','motion_detector'):
                            hashes[module['animation_name']]['decoded']=parameter_summary(data) if module['animation_name']=='parameter' else control_schema('trmdt','SV/Flatbuffers/animation').decode(data)
                    values.append(dict(catalog_path=path,path=actual,value=value,modules=hashes))
            modules[label]=values
        parameters={label:values[0]['modules']['parameter']['decoded']['root_node'] for label,values in modules.items()}
        differences={}
        for group in set(parameters['original'])|set(parameters['donor']):
            left={r['name']:r for r in parameters['original'].get(group,[])}
            right={r['name']:r for r in parameters['donor'].get(group,[])}
            differences[group]={name:dict(original=left.get(name),donor=right.get(name)) for name in sorted(set(left)|set(right)) if left.get(name)!=right.get(name)}
        print(json.dumps(dict(read_only=True,parameter_differences=differences,motion_detector={label:values[0]['modules']['motion_detector']['decoded'] for label,values in modules.items()})),flush=True)
        return
    if a.component!='all':
        replacement=copy.deepcopy(original)
        fields={'animations':('animations',),'support':('config_path','locators','defence_path'),
                'model':('model_path','material_table_path')}[a.component]
        for field in fields:
            if field in donor:replacement[field]=copy.deepcopy(donor[field])
            else:replacement.pop(field,None)
    replacement['species_info']=original['species_info']
    replacement['icon_path']=original['icon_path']
    table['table'][matches[0]]=replacement
    if a.mods_root:
        destination=a.mods_root.resolve()
        assert destination.is_relative_to(work.resolve()) and not destination.exists()
        destination.mkdir()
        import _winapi
        for name in (() if a.native_stock else ('00-icon-identity-r2','all-models')):
            source=(work/'mods'/name).resolve()
            _winapi.CreateJunction(str(source),str(destination/name))
            assert os.path.samefile(source,destination/name)
    else:assert a.national==835 and a.donor==172,'Use isolated --mods-root for other comparisons'
    overlay=(a.mods_root or work/'mods')/'00-ablation-yamper-native-model-r1/romfs'
    atomic(overlay/relative,encode_checked(schema,table))
    report=a.mods_root/'native-model-probe.json' if a.mods_root else work/'yamper-native-model-probe-r1.json'
    atomic(report,json.dumps(dict(PC_only=True,diagnostic_only=True,
        native_stock=a.native_stock,tested_species=a.national,displayed_model_species=a.donor if a.component in ('all','model') else a.national,
        animation_donor=a.donor,component=a.component,QA_pass_allowed=False,
        purpose='Distinguish imported model/controller failure from species/fixture failure',
        original=original,replacement=replacement),indent=1).encode())
    print(json.dumps(dict(overlay=str(overlay),component=a.component,
                          displayed_model_species=a.donor if a.component in ('all','model') else a.national,
                          animation_donor=a.donor,QA_pass_allowed=False)),flush=True)


if __name__=='__main__':main()
