"""Read-only core asset audit and shared-state-machine coverage for imported models.

Runtime, icon identity and visual correctness are separate verdicts. A representative
never changes another model's individual gameplay status. Output contains metadata,
hashes and source paths, never game payloads or saves. Resume only matching inputs.
"""
import argparse,collections,hashlib,json,os,posixpath,re,time
from pathlib import Path
os.environ['ZA_ROMFS_PATH']=str(Path(__file__).resolve().parents[3]/'hebrew-lab/qa-game-reference-20261030/romfs.bin')
from build_smoliv_model import Z,schema
from storage_paths import data_root
from audit_missing_controller_modules import entries
from probe_yamper_native_model import parameter_summary
from native_donors import node_names
from retarget_layer_channels import root_names,target_names
from movesets import is_dummied

def sha(data):return hashlib.sha256(data).hexdigest()
def read_json(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write_json(path,value):
    temp=path.with_suffix(path.suffix+'.new')
    temp.write_text(json.dumps(value,indent=1,ensure_ascii=False),encoding='utf-8');os.replace(temp,path)

def canonical_state(raw,folder,internal):
    """Normalize ONLY the namespace substitutions performed by renamed().

    Keep the entire opaque state graph, offsets and every other byte intact.
    This fingerprint compares shared graph data; it is not a runtime verdict.
    """
    pm,stem=folder.split('/')
    pairs=((stem.encode(),b'pm0000_00_00'),(pm.encode(),b'pm0000'),
           (('PLAY_PV_%04d'%internal).encode(),b'PLAY_PV_0000'))
    result=raw;replacements={}
    for old,new in pairs:
        assert len(old)==len(new)
        replacements[old.decode()]=result.count(old)
        result=result.replace(old,new)
    assert len(result)==len(raw)
    return result,replacements

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--resume',action='store_true')
    p.add_argument('--budget-seconds',type=int,default=225);a=p.parse_args()
    assert 15<=a.budget_seconds<=240
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1'
    out=a.out.resolve();assert out.is_relative_to(work.resolve())
    assert a.resume==out.exists(),'Use a new output, or explicit --resume'
    out.mkdir(parents=True,exist_ok=a.resume);started=time.monotonic()
    root=data_root();qa=root/'qa/all-pokemon-20261030-r2'
    inv_path=qa/'inventory-v4.json';integration_path=root/'build/all-species-r1/integration.json'
    inv_raw=inv_path.read_bytes();integration_raw=integration_path.read_bytes()
    inventory=json.loads(inv_raw);integration=json.loads(integration_raw)
    targets=[r for r in inventory['targets'] if r['imported']]
    assert len(targets)==833 and len({r['key'] for r in targets})==833
    by_folder={r['folder']:r for r in integration['models']}
    base=root/'build/all-species-r1/all-models/romfs'
    # Exact priority order used by the existing effective dependency audit.
    model_layers=[qa/name/'romfs' for name in ('variant-texture-repairs-r1','native-control-repairs-r3',
                   'validated-render-fixes-r1','motion-overlay','rate-overlay')]+[base]
    assert all(r.is_dir() for r in model_layers)
    inputs=dict(audit_revision=2,audit_source_sha256=sha(Path(__file__).read_bytes()),
                inventory_sha256=sha(inv_raw),integration_sha256=sha(integration_raw),
                inventory=str(inv_path),integration=str(integration_path),
                effective_model_priority=[str(r) for r in model_layers],
                caveat='Read-only effective model stack; not a hardware deployment manifest.')
    if a.resume:assert read_json(out/'inputs.json')==inputs,'Inputs changed; create another audit version'
    else:write_json(out/'inputs.json',inputs)
    rows={}
    journal=out/'model-results.jsonl'
    if journal.exists():
        for line in journal.read_text(encoding='utf-8').splitlines():
            if line.strip():
                row=json.loads(line);assert row['key'] not in rows;rows[row['key']]=row
    assert set(rows)<={r['key'] for r in targets}
    personal=Z.personal_schema().decode((base/Z.PERSONAL).read_bytes())['Table']
    personal_by={(r['Info']['SpeciesInternal'],r['Info'].get('Form',0)):r for r in personal}
    present={k for k,r in personal_by.items() if r.get('IsPresentInGame')}
    catalog_keys={(r['internal'],r['form']) for r in inventory['targets']}
    track_schema=schema('tracr','ZA/Flatbuffers')
    folder_cache={}
    def index(folder):
        if folder not in folder_cache:
            files={}
            for layer in reversed(model_layers):
                directory=layer/'ik_pokemon/data'/folder
                if not directory.is_dir():continue
                def walk_error(error):raise error
                for parent,dirs,names in os.walk(directory,onerror=walk_error):
                    for name in names:
                        file=Path(parent)/name;files[file.relative_to(directory).as_posix()]=file
            folder_cache[folder]=files
        return folder_cache[folder]
    def asset(folder,name):
        assert not Path(name).is_absolute()
        relative=posixpath.normpath(str(folder)+'/'+name)
        assert not relative.startswith('../')
        parts=Path(relative).parts
        assert len(parts)>=3
        return index('/'.join(parts[:2])).get('/'.join(parts[2:]))
    with journal.open('a',encoding='utf-8',buffering=1) as log:
        for target in targets:
            if target['key'] in rows:continue
            if time.monotonic()-started>a.budget_seconds-15:break
            folder=Path(target['model_path']).parent.as_posix();stem=Path(folder).name
            row={k:target[k] for k in ('key','national','internal','form','gender','source')}
            row.update(folder=folder,gameplay_status='not_inferred',visual_status='not_inferred',
                       icon_identity_status='not_checked_by_this_core_audit',problems=[])
            try:
                record=by_folder[folder];row['donor_species']=record['donor_species']
                files=index(folder);catalog=target['catalog']
                for field in ('model_path','material_table_path','config_path'):
                    name=catalog[field];assert name.startswith(folder+'/'),field+' identity mismatch'
                    assert name[len(folder)+1:] in files,'Missing '+field+': '+name
                modules=entries(files[stem+'_base.tracn'].read_bytes())
                module_by={m['animation_name']:m['filename'] for m in modules}
                absent=[m for m in modules if m['filename'] not in files]
                if absent:row['problems'].append(dict(missing_modules=absent))
                parameter=files[module_by['parameter']].read_bytes()
                summary=parameter_summary(parameter)['root_node']
                categories=[r['field_3'] for r in summary['animations'] if r['name']=='category_int']
                assert len(categories)==1
                row['category_int']=categories[0];row['parameter_sha256']=sha(parameter)
                state=files[module_by['state']].read_bytes();row['state_sha256']=sha(state)
                canonical,replacements=canonical_state(state,folder,target['internal'])
                row['canonical_state_sha256']=sha(canonical);row['namespace_replacements']=replacements
                row['controller_module_types']=sorted(module_by)
                tracks=track_schema.decode(files[module_by['resource']].read_bytes())['track_list']['list']
                missing=[];refs=0
                for track in tracks:
                    for resource in track.get('track_resource',{}).values():
                        name=resource.get('filename')
                        if name:
                            refs+=1
                            if asset(folder,name) is None:missing.append(dict(track=track['track_name'],file=name))
                row['track_count']=len(tracks);row['resource_references_checked']=refs
                if missing:row['problems'].append(dict(missing_track_resources=missing))
                skeleton=Path(target['model_path']).stem+'.trskl'
                bones=set(node_names(files[skeleton].read_bytes()))
                registered={s.lower() for s in root_names(files[module_by['layer']].read_bytes())}
                # Violet skeletons also contain unused LOD mesh/light nodes.
                # Compare the source controller's actual registry, as the
                # established retarget audit does; retain all skeleton extras.
                expected={s.lower() for s in target_names(target,root)}
                absent_bones=sorted(expected-registered)
                row['skeleton_nodes']=len(bones)
                row['source_channel_nodes_checked']=len(expected)
                row['skeleton_nodes_outside_registry']=sorted(bones-registered)
                if absent_bones:row['problems'].append(dict(bone_registry_missing_nodes=absent_bones))
                ps=personal_by[(target['internal'],target['form'])]
                row['body_type']=ps['Info'].get('BodyType',0)
                moves=sorted({m['Move'] for m in ps.get('Learnset',[]) if m.get('Move')})
                dummied=[m for m in moves if is_dummied(m)]
                row['learnset_moves_checked']=len(moves)
                if dummied:row['problems'].append(dict(unimplemented_learnset_moves=dummied))
                evolutions=ps.get('Evolutions',[]);bad_evo=[]
                for evo in evolutions:
                    k=(evo.get('SpeciesInternal',0),evo.get('Form',0))
                    if k[0] and (k not in present or k not in catalog_keys):bad_evo.append(evo)
                row['evolution_references_checked']=len(evolutions)
                row['evolution_methods']=sorted({str(e.get('Condition',e.get('Method','unknown'))) for e in evolutions})
                if bad_evo:row['problems'].append(dict(unresolved_evolution_targets=bad_evo))
                mapping=record.get('animation_mapping',[])
                fallback=[m['target'] for m in mapping if 'attack' in m.get('target','').lower()
                          and any(s in m.get('source','').lower() for s in ('wait','idle'))]
                row['attack_tracks_mapped_to_idle']=fallback
                signature=dict(state_sha256=row['canonical_state_sha256'],category_int=row['category_int'],
                               pipeline=row['source'],module_types=row['controller_module_types'])
                row['shared_state_group']=sha(json.dumps(signature,sort_keys=True).encode())[:16]
                row['mechanism_bucket']=row['source']+'/category-'+str(row['category_int'])+'/modules-'+sha('|'.join(row['controller_module_types']).encode())[:8]
                row['core_static_status']='fail' if row['problems'] else 'pass'
            except Exception as error:
                row['core_static_status']='error';row['problems'].append(dict(error=str(error)))
            rows[row['key']]=row;log.write(json.dumps(row,ensure_ascii=False)+'\n')
            if len(rows)%25==0:print(json.dumps(dict(audited=len(rows),total=len(targets))),flush=True)
    groups=collections.defaultdict(list)
    for row in rows.values():
        if row.get('shared_state_group'):groups[row['shared_state_group']].append(row)
    groups_out=[];chosen=set()
    for group,members in sorted(groups.items()):
        candidates=[r for r in members if r['core_static_status']=='pass']
        preferred={835:0,749:1,519:2}
        ordered=sorted(candidates,key=lambda r:(preferred.get(r['national'],3),bool(r['form'] or r['gender']),r['key']))
        representative=ordered[0]['key'] if ordered else None
        if representative:chosen.add(representative)
        groups_out.append(dict(group=group,members=[r['key'] for r in members],count=len(members),
                               source=members[0]['source'],category_int=members[0]['category_int'],
                               canonical_state_sha256=members[0]['canonical_state_sha256'],representative=representative,
                               runtime_verdict='pending',individual_visual_or_gameplay_pass_inferred=False))
    assert sum(r['count'] for r in groups_out)==sum(bool(r.get('shared_state_group')) for r in rows.values())
    assert inv_path.read_bytes()==inv_raw and integration_path.read_bytes()==integration_raw
    complete=len(rows)==len(targets)
    buckets=collections.defaultdict(list)
    for row in rows.values():
        if row.get('mechanism_bucket'):buckets[row['mechanism_bucket']].append(row['key'])
    # Greedy initial regression panel: cover source/category/module buckets,
    # body types and form/gender risks. Exact graph differences stay explicit.
    def features(row):
        return {row['mechanism_bucket'],'body-'+str(row['body_type']),
                'form-'+str(bool(row['form'])),'gender-'+str(bool(row['gender']))}
    candidates=[r for r in rows.values() if r['core_static_status']=='pass']
    uncovered=set().union(*(features(r) for r in candidates)) if candidates else set()
    panel=[]
    preferred={835:0,749:1,519:2}
    while uncovered:
        ordered=sorted(candidates,key=lambda r:(-len(features(r)&uncovered),
                       preferred.get(r['national'],3),bool(r['form'] or r['gender']),r['key']))
        choice=ordered[0];covers=sorted(features(choice)&uncovered)
        assert covers
        panel.append(dict(key=choice['key'],covers=covers,runtime_status='pending'))
        uncovered-=features(choice);candidates.remove(choice)
    report=dict(version=2,audit_complete=complete,audited=len(rows),total=len(targets),
                source_game_and_build_unchanged=True,core_static_counts=dict(collections.Counter(r['core_static_status'] for r in rows.values())),
                shared_state_groups=len(groups_out),representatives=len(chosen),
                raw_state_fingerprints=len({r['state_sha256'] for r in rows.values() if 'state_sha256' in r}),
                normalized_state_fingerprints=len({r['canonical_state_sha256'] for r in rows.values() if 'canonical_state_sha256' in r}),
                mechanism_buckets=dict(sorted(buckets.items())),initial_regression_panel=panel,
                initial_regression_panel_count=len(panel),unique_imported_national_species=len({r['national'] for r in rows.values()}),
                fingerprint_rule='Only exact importer namespace substitutions normalized, keeping all other opaque state bytes; equal graph hashes do not prove equal clips, timing, geometry or gameplay.',
                panel_rule='Initial shared-mechanism regression only. It does not cover every exact controller graph or grant member gameplay passes. Investigate graph/mapping/asset exceptions separately.',
                scope='Module/track dependencies, controller fingerprints, bone registry, move availability and evolution references.',
                remaining_checks=['Authentic icon identity against source catalog','Material/mesh texture dependencies and visual correctness',
                                  'Representative runtime movement, physical/ranged/status moves, actual evolution and saved reload',
                                  'Mapping/timing, form and geometry exceptions require their own evidence'],
                inference_rule='A representative can validate shared behavior only. It never marks every member individually gameplay/visual passed.',
                gameplay_individual_full_passes_retained=2,pidove_gust_candidate_observed=True,
                groups=groups_out,representative_keys=sorted(chosen),
                errors_or_failures=[r for r in rows.values() if r['core_static_status']!='pass'],
                elapsed_seconds=round(time.monotonic()-started,3))
    write_json(out/'result.json',report)
    print(json.dumps({k:report[k] for k in ('audit_complete','audited','total','core_static_counts','shared_state_groups','representatives','raw_state_fingerprints','normalized_state_fingerprints','initial_regression_panel_count','elapsed_seconds')}),flush=True)

if __name__=='__main__':main()
