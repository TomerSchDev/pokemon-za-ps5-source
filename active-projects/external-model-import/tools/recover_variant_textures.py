"""Recover only indexed, missing authentic textures from the read-only supplied game."""
from pathlib import Path
import hashlib,json,os,time
from run_pc_gallery import QA,WORK
from catalog_inventory import VIOLET
from source_archives import Oodle,fnv1a64

def main():
    index=QA/'missing-variant-texture-index.json'
    deadline=time.monotonic()+600
    while not index.exists():
        assert time.monotonic()<deadline,'Source metadata index did not finish'
        time.sleep(10)
    info=json.loads(index.read_text(encoding='utf-8'))
    assert not info['source_paths_not_found'] and not info['other_missing']
    source=VIOLET/'arc/data.trpfs'
    assert source.stat().st_size==info['source_size']
    decoder=Oodle();dest=QA/'variant-texture-repairs-r1'
    cache=WORK/'render-fixes';certificate=cache/'verified-hashes.json'
    hashes=json.loads(certificate.read_text(encoding='utf-8'));report=[]
    with source.open('rb') as stream:
        for item in info['missing_textures']:
            record=item['source_record'];assert fnv1a64(item['source_path'])==record['hash']
            assert 0<record['csize']<=128*1024*1024 and record['data']+record['csize']<=info['source_size']
            stream.seek(record['data']);raw=stream.read(record['csize']);assert len(raw)==record['csize']
            payload=decoder.unpack(record['comp'],record['size'],raw);assert payload[:4]==b'BNTX'
            payload=payload.replace(item['old_prefix'].encode(),item['new_prefix'].encode())
            relative=Path(item['target_path']);assert not relative.is_absolute() and '..' not in relative.parts
            target=dest/'romfs/ik_pokemon/data'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            digest=hashlib.sha256(payload).hexdigest()
            if target.exists():assert target.read_bytes()==payload
            else:target.write_bytes(payload)
            cache_relative='mods/00-variant-textures/romfs/ik_pokemon/data/'+relative.as_posix()
            local=cache/cache_relative;local.parent.mkdir(parents=True,exist_ok=True)
            if local.exists():assert local.read_bytes()==payload
            else:
                temp=local.with_name(local.name+'.qa-new');temp.write_bytes(payload);os.replace(temp,local)
            hashes[cache_relative]=digest
            report.append(dict(item,bytes=len(payload),sha256=digest))
    result={'source_game_unchanged':True,'canonical_texture_data_on_NAS':True,'temporary_PC_runtime_cache':True,
            'textures':report,'models_affected':sorted({k for x in report for k in x['referenced_by']}),
            'runtime_validation':'pending isolated female-variant probe'}
    (dest/'texture-repairs.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
    temp=certificate.with_suffix('.qa-new');temp.write_text(json.dumps(hashes),encoding='utf-8');os.replace(temp,certificate)
    print(json.dumps({'recovered_textures':len(report),'bytes':sum(x['bytes'] for x in report),'models_affected':len(result['models_affected'])}),flush=True)

if __name__=='__main__':main()
