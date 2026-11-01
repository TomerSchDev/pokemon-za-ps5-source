"""Read-only module dependency audit; can run directly on the NAS."""
from pathlib import Path
import collections,json,struct,sys

def entries(data):
    u32=lambda p:struct.unpack_from('<I',data,p)[0]
    def table(p):
        vt=p-struct.unpack_from('<i',data,p)[0]
        size=struct.unpack_from('<H',data,vt)[0]
        assert 4<=size<=256 and size%2==0
        return [p+o if (o:=struct.unpack_from('<H',data,vt+4+i*2)[0]) else 0 for i in range((size-4)//2)]
    def string(field):
        at=field+u32(field);length=u32(at)
        return data[at+4:at+4+length].decode('utf-8')
    fields=table(u32(0));at=fields[0]+u32(fields[0]);count=u32(at);out=[]
    for i in range(count):
        field=at+4+i*4;item=table(field+u32(field))
        assert len(item)==2 and all(item)
        out.append({'animation_name':string(item[0]),'filename':string(item[1])})
    return out

def main(root):
    qa=root/'qa/all-pokemon-20261030-r2'
    targets=json.loads((qa/'inventory-v3.json').read_text(encoding='utf-8'))['targets']
    missing=[];failures=[]
    for target in targets:
        if not target['imported']:continue
        folder=Path(target['model_path']).parent
        base=root/'build/all-species-r1/all-models/romfs/ik_pokemon/data'/folder
        try:
            existing={p.name for p in base.iterdir()}
            for entry in entries((base/(folder.name+'_base.tracn')).read_bytes()):
                if entry['filename'] not in existing:missing.append(dict(target=target['key'],**entry))
        except Exception as exc:failures.append({'key':target['key'],'error':str(exc)})
    result={'read_only':True,'missing_dependencies':missing,'failures':failures,
            'module_counts':dict(collections.Counter(x['animation_name'] for x in missing))}
    (qa/'missing-controller-modules-audit.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({'missing_count':len(missing),'module_counts':result['module_counts'],'failures':failures}))

if __name__=='__main__':main(Path(sys.argv[1]))
