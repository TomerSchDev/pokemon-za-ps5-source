"""Resolve model file names from the source model's own dependency graph and animation resources."""
import collections
from pathlib import Path
import re
from source_archives import fnv1a64


def resolve_folder(game, folder, prefix='pokemon/data'):
    base=prefix+'/'+folder+'/'
    stem=folder.split('/')[-1]
    seeds=[stem+suffix for suffix in ('.trmdl','.trmmt','.trpokecfg','.tracn','_base.tracn','_base.tracr',
           '_base.tracl','_base.tracp','_base.tracs','_base.tralk','_base.trssp','_base.trmdt','_base.trslp',
           '_base_motion_detector.trmdd','_00000.trskl','_10000.trskl','_20000.trskl','.trskl','.trmtr',
           '_rare.trmtr','.trmsh','.trmbf','_defence.hkx','_00.bntx')]
    seeds += [f'{stem}_lod{i}.{ext}' for i in range(1,4) for ext in ('trmsh','trmbf')]
    seeds += [f'icon/{stem}_00{suffix}.bntx' for suffix in ('','_0','_1','_2','_3')]
    seeds += [f'{stem}_{i}0000.trskl' for i in range(4)]
    queue=[base+s for s in seeds]
    found,seen,dependencies={},set(),set()
    while queue:
        path=queue.pop()
        if path in seen:
            continue
        seen.add(path)
        record=game.files.get(fnv1a64(path))
        if record is None:
            continue
        found[path]=record
        if record['size']>8<<20 or path.endswith(('.bntx','.trmbf','.hkx','.tranm')):
            continue
        data=game.read(path)
        for raw in re.findall(rb'[ -~]{4,}',data):
            try:
                string=raw.decode('ascii')
            except UnicodeDecodeError:
                continue
            for candidate in re.findall(r'[\w./-]+\.[a-z0-9]{2,9}',string):
                name=candidate.rsplit('/',1)[-1]
                dependencies.add(candidate)
                queue.extend((candidate,base+candidate,base+name,prefix+'/'+candidate))
            if re.fullmatch(r'[\w-]+',string) and len(string)<100:
                for ext in ('.tranm','.tracm','.traef','.trcrv'):
                    queue.extend((base+string+ext,base+stem+'_'+string+ext))
    packs=collections.Counter(r['pack'] for r in found.values())
    hashes={fnv1a64(path) for path in found}
    unknown=[r for name,records in game.packs if name in packs for r in records if r['hash'] not in hashes]
    return found,unknown,sorted(dependencies)


def extract_folder(game, folder, out, prefix='pokemon/data'):
    out=Path(out)
    paths,unknown,deps=resolve_folder(game,folder,prefix)
    for path in paths:
        dest=out/path
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(game.read(path))
    return dict(files=len(paths),bytes=sum(r['size'] for r in paths.values()),
                extensions=dict(collections.Counter(Path(p).suffix for p in paths)),
                unresolved=[dict(hash=f'{r["hash"]:016x}',bytes=r['size'],pack=r['pack']) for r in unknown],
                dependencies=deps)
