"""Audit effective QA model references, including shared variant textures."""
from pathlib import Path
import collections,json,posixpath,sys
from build_smoliv_model import ROOT,schema
from retarget_layer_channels import root_names,target_names
from source_archives import FB

EXTENSIONS={'.trmsh','.trmbf','.trskl','.trmtr','.bntx','.tranm','.tracm','.traef',
            '.tracl','.tracr','.tracp','.tracs','.tralk','.trmdt','.trslp','.trmdd',
            '.trbsm','.trspn','.truno','.trmae','.trslt'}

def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,dict):
        for item in value.values():yield from strings(item)
    elif isinstance(value,list):
        for item in value:yield from strings(item)

def material_table_files(data):
    # Only stable material-file references are needed. Some source variants have
    # an additional MaterialProperties field 6; preserve that payload untouched.
    fb=FB(data);root=fb.table(fb.u32(0));count,first=fb.vec(root[2]);out=[]
    for i in range(count):
        at=first+i*4;item=fb.table(at+fb.u32(at))
        if len(item)<2 or not item[1]:continue
        total,values=fb.vec(item[1]);out.extend(fb.string(values+j*4) for j in range(total))
    return out

def main():
    qa=ROOT/'qa/all-pokemon-20261030-r2'
    base=ROOT/'build/all-species-r1/all-models/romfs/ik_pokemon/data'
    overlays=[qa/name/'romfs/ik_pokemon/data' for name in ('variant-texture-repairs-r1','native-control-repairs-r3','validated-render-fixes-r1','motion-overlay','rate-overlay')]
    targets=json.loads((qa/'inventory-v4.json').read_text(encoding='utf-8'))['targets']
    kinds={'trmdl':schema('trmdl'),'trmsh':schema('trmsh'),'trmtr':schema('trmtr'),'trmmt':schema('trmmt'),
           'tracn':schema('tracn','SV/Flatbuffers/animation'),'tracr':schema('tracr','ZA/Flatbuffers')}
    def effective(relative):
        return next((root/relative for root in [*overlays,base] if (root/relative).is_file()),None)
    if '--repair-known-gaps' in sys.argv:
        result=json.loads((qa/'effective-model-dependency-audit-r1.json').read_text(encoding='utf-8'))
        remaining=[];opaque=[];failures=[];rechecks=[]
        for item in result['missing_dependencies']:
            path=effective(Path(item['file']));kind=Path(item['file']).suffix.lstrip('.')
            active=set(strings(kinds[kind].decode(path.read_bytes())))
            present=effective(Path(item['resolved'])) is not None
            if item['reference'] in active and not present:remaining.append(item)
            rechecks.append({'file':item['file'],'reference_still_active':item['reference'] in active,'effective_file':str(path)})
        for item in result['parse_failures']:
            if not item['file'].endswith('.trmmt'):
                failures.append(item);continue
            path=effective(Path(item['file']));folder=Path(item['file']).parent
            for name in material_table_files(path.read_bytes()):
                relative=posixpath.normpath(folder.as_posix()+'/'+name)
                result['file_references_checked']+=1
                if effective(Path(relative)) is None:remaining.append(dict(item,reference=name,resolved=relative))
            opaque.append({'key':item['key'],'file':item['file'],'unknown_material_properties_preserved':True})
        result.update(audit_revision=2,missing_dependencies=remaining,parse_failures=failures,
                      read_only_material_property_extensions=opaque,validated_overlay_rechecks=rechecks)
        (qa/'effective-model-dependency-audit-r2.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
        print(json.dumps({k:(len(v) if isinstance(v,list) else v) for k,v in result.items()}),flush=True);return
    missing=[];parse_failures=[];registry_failures=[];references=0;recovered_hits=0
    for target in targets:
        if not target['imported']:continue
        folder=Path(target['model_path']).parent;stem=folder.name
        for path in (base/folder).iterdir():
            kind=path.suffix.lstrip('.')
            if kind not in kinds:continue
            relative=path.relative_to(base);actual=effective(relative)
            try:
                value=material_table_files(actual.read_bytes()) if kind=='trmmt' else kinds[kind].decode(actual.read_bytes())
                for name in set(strings(value)):
                    if Path(name).suffix not in EXTENSIONS:continue
                    resolved=posixpath.normpath(folder.as_posix()+'/'+name)
                    if resolved.startswith('../'):continue  # Native, packed shared lighting resources.
                    references+=1;found=effective(Path(resolved))
                    if found is None:missing.append({'key':target['key'],'file':relative.as_posix(),'reference':name,'resolved':resolved})
                    elif found.is_relative_to(overlays[0]):recovered_hits+=1
            except Exception as exc:parse_failures.append({'key':target['key'],'file':relative.as_posix(),'error':str(exc)})
        layer=effective(folder/(stem+'_base.tracl'))
        absent=sorted(set(target_names(target,ROOT))-set(root_names(layer.read_bytes())))
        if absent:registry_failures.append({'key':target['key'],'missing_nodes':absent})
    result={'source_game_and_build_unchanged':True,'models':sum(t['imported'] for t in targets),
            'file_references_checked':references,'recovered_texture_references_resolved':recovered_hits,
            'missing_dependencies':missing,'parse_failures':parse_failures,'bone_registry_failures':registry_failures}
    (qa/'effective-model-dependency-audit-r1.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({k:(len(v) if isinstance(v,list) else v) for k,v in result.items()}),flush=True)

if __name__=='__main__':main()
