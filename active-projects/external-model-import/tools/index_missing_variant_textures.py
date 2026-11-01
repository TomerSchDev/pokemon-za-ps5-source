"""Read-only source index lookup for missing cross-variant Violet textures."""
from pathlib import Path
import collections,json,posixpath,mmap
from build_smoliv_model import ROOT,schema
from catalog_inventory import VIOLET
import source_archives

def main():
    qa=ROOT/'qa/all-pokemon-20261030-r2';base=ROOT/'build/all-species-r1/all-models/romfs/ik_pokemon/data'
    models=json.loads((ROOT/'build/violet-model-candidates-r1/conversion.json').read_text(encoding='utf-8'))['models']
    prefixes={m['target_folder'].split('/')[0]:m['source_folder'].split('/')[0] for m in models if m.get('status')=='geometry_materials_converted'}
    targets=json.loads((qa/'inventory-v4.json').read_text(encoding='utf-8'))['targets']
    material=schema('trmtr');missing={};other=[]
    for target in targets:
        if not target['imported'] or target['source']!='violet':continue
        folder=Path(target['model_path']).parent
        for path in (base/folder).glob('*.trmtr'):
            for mat in material.decode(path.read_bytes())['materials']:
                for texture in mat.get('textures',[]):
                    name=texture['texture_file'];relative=posixpath.normpath(folder.as_posix()+'/'+name)
                    if relative.startswith('../'):continue  # Shared original game lighting resources.
                    if (base/relative).is_file():continue
                    prefix=relative.split('/')[0]
                    if prefix not in prefixes:
                        other.append({'key':target['key'],'missing':relative});continue
                    source='pokemon/data/'+relative.replace(prefix,prefixes[prefix])
                    item=missing.setdefault(relative,{'target_path':relative,'source_path':source,'old_prefix':prefixes[prefix],
                                                     'new_prefix':prefix,'referenced_by':[]})
                    if target['key'] not in item['referenced_by']:item['referenced_by'].append(target['key'])
    # Resolve only the packs already recorded by the original extraction's
    # unresolved-hash manifest. Do not walk unrelated source payload headers.
    bank=json.loads((ROOT/'source-bank/source-bank.json').read_text(encoding='utf-8'))
    known={int(item['hash'],16):item['pack'] for model in bank['models']
           for item in model.get('unresolved',[]) if item.get('pack')}
    wanted={source_archives.fnv1a64(item['source_path']) for item in missing.values()}
    assert wanted<=set(known),'Missing texture hash was not recorded in the extraction manifest'
    packs={source_archives.fnv1a64(known[key]):known[key] for key in wanted}
    records={}
    with (VIOLET/'arc/data.trpfs').open('rb') as handle:
        data=mmap.mmap(handle.fileno(),0,access=mmap.ACCESS_READ);fb=source_archives.FB(data)
        assert data[:8]==b'ONEPACK\0'
        at=fb.u64(8);table=fb.table(at+fb.u32(at))
        count,hashes=fb.vec(table[0]);n,offsets=fb.vec(table[1]);assert count==n
        for i in range(count):
            pack_hash=fb.u64(hashes+8*i)
            if pack_hash not in packs:continue
            at=fb.u64(offsets+8*i);fields=fb.table(at+fb.u32(at))
            total,hp=fb.vec(fields[0]);n,fp=fb.vec(fields[1]);assert total==n
            for j in range(total):
                key=fb.u64(hp+8*j)
                if key not in wanted:continue
                field=fp+4*j;fs=fb.table(field+fb.u32(field));length,position=fb.vec(fs[4])
                records[key]={'hash':key,'data':position,'csize':length,'size':fb.u64(fs[3]) if len(fs)>3 and fs[3] else length,
                              'comp':data[fs[1]] if len(fs)>1 and fs[1] else 255,'pack':packs[pack_hash]}
        data.close()
    unresolved=[]
    for item in missing.values():
        key=source_archives.fnv1a64(item['source_path']);record=records.get(key)
        if record is None:unresolved.append(item['source_path'])
        else:item['source_record']=record
    stat=(VIOLET/'arc/data.trpfs').stat()
    result={'read_only':True,'source_size':stat.st_size,'source_mtime_seconds':int(stat.st_mtime),
            'missing_textures':list(missing.values()),'source_paths_not_found':unresolved,'other_missing':other}
    (qa/'missing-variant-texture-index.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({'missing_textures':len(missing),'models_affected':len({k for x in missing.values() for k in x['referenced_by']}),
                      'source_paths_not_found':unresolved,'other_missing':other}),flush=True)

if __name__=='__main__':main()
