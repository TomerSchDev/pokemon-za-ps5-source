"""Read-only raw NVN shader-header scan outside recognized BNSH byte ranges.

Magic alone is a candidate, never a validated shader. No raw game files are copied.
"""
from pathlib import Path
import bisect, collections, hashlib, json, struct, sys, time
from forecast import ROOT, DEFAULT_PC
from extract_bnsh import bnsh_headers


def main():
    ev=ROOT/'evidence/offline-shaders-20261028'
    sys.path.insert(0,str(DEFAULT_PC/'randomizer-lab'))
    from inspect_game import Game
    from nso import Nso
    g=Game(DEFAULT_PC/'update-2.0.2-20261025/game/romfs.bin',
           DEFAULT_PC/'release-v0.1.4/ZA Recomp/zaprompts/_internal/ooz.dll')
    report=dict(schema=1,complete=False,files_checked=0,bytes_checked=0,inside_bnsh={},
                outside_counts={},outside_hits=[],outside_hits_truncated=False,errors=[],oversize=[],exefs=[])
    inside=collections.Counter();outside=collections.Counter();last=time.monotonic();started=last
    def save():
        report['inside_bnsh']=dict(inside);report['outside_counts']=dict(outside)
        report['elapsed_seconds']=round(time.monotonic()-started,1)
        p=ev/'audit-raw-sph.json';tmp=p.with_suffix('.new');tmp.write_text(json.dumps(report,indent=2));tmp.replace(p)
    def scan(data,where):
        report['files_checked']+=1;report['bytes_checked']+=len(data)
        intervals=sorted((off,off+size) for off,size,count in bnsh_headers(data))
        # Merge overlapping container ranges before binary search.
        merged=[]
        for lo,hi in intervals:
            if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
            else:merged.append((lo,hi))
        starts=[lo for lo,hi in merged]
        for magic,kind in ((b'\x78\x56\x34\x12','graphics'),(b'\x79\x56\x34\x12','compute')):
            start=0
            while True:
                offset=data.find(magic,start)
                if offset<0:break
                start=offset+4
                at=bisect.bisect_right(starts,offset)-1
                if at>=0 and offset<merged[at][1]:inside[kind]+=1;continue
                outside[kind]+=1
                header=0x80 if kind=='graphics' else 0x100
                nvn_zero=offset+0x30<=len(data) and not any(data[offset+4:offset+0x30])
                sph=struct.unpack_from('<I',data,offset+0x30)[0] if offset+0x34<=len(data) else None
                stage=(sph>>10)&15 if sph is not None else None
                enough=offset+header+16<=len(data)
                header_shape=nvn_zero and enough and (stage in (1,2,3,4,5) if kind=='graphics' else not any(data[offset+4:offset+0x100]))
                outside['plausible_header' if header_shape else 'magic_only']+=1
                if len(report['outside_hits'])<2000:
                    report['outside_hits'].append(dict(file=where,offset=offset,kind=kind,aligned_8=offset%8==0,
                        nvn_prefix_zero=nvn_zero,sph0=None if sph is None else hex(sph),sph_stage=stage,
                        plausible_header=header_shape,following_code_available=enough,
                        header_sha256=hashlib.sha256(data[offset:offset+header]).hexdigest(),
                        first_instruction_words=data[offset+header:offset+header+24].hex() if enough else None))
                else:report['outside_hits_truncated']=True
    def progress():
        nonlocal last
        if time.monotonic()-last>15:
            save();print(json.dumps(dict(files=report['files_checked'],inside=sum(inside.values()),outside=dict(outside))),flush=True)
            last=time.monotonic()
        if time.monotonic()-started>900:raise TimeoutError('Bounded scan exceeded 15 minutes; partial report retained')
    try:
        for pack in g.packs:
            for r in pack['files']:
                where=pack['name']+'#'+r['hash']
                if r['size']>256<<20:
                    report['oversize'].append(dict(file=where,bytes=r['size']));continue
                try:
                    data=g.oodle.unpack(r['compression'],r['size'],g.pack[r['offset']:r['offset']+r['compressed_size']])
                    scan(data,where)
                except Exception as error:report['errors'].append(dict(file=where,error=str(error)))
            progress()
        for name,(_,size) in g.entries.items():
            if name in ('arc/data.trpfs','arc/data.trpfd'):continue
            if size>256<<20:
                report['oversize'].append(dict(file=name,bytes=size));continue
            try:scan(g.read(name),name)
            except Exception as error:report['errors'].append(dict(file=name,error=str(error)))
            progress()
        for name in ('main','sdk','rtld'):
            path=DEFAULT_PC/'update-2.0.2-20261025/game/exefs'/name
            nso=Nso(path);before=sum(outside[k] for k in ('graphics','compute'))
            scan(nso.image,'exefs/'+name)
            report['exefs'].append(dict(name=name,bytes=len(nso.image),build_id=nso.build_id,
                outside_hits=sum(outside[k] for k in ('graphics','compute'))-before))
        report['complete']=True
    finally:save()
    lines=['Raw NVN/SPH coverage audit — 2026-10-28',
        f"Complete: {report['complete']}; files/images checked: {report['files_checked']:,}; decoded bytes: {report['bytes_checked']:,}.",
        'Recognized BNSH byte ranges were excluded from the raw candidate list.',
        'Inside BNSH magic occurrences: '+json.dumps(dict(inside)),
        'Outside BNSH counts: '+json.dumps(dict(outside)),
        f"Errors: {len(report['errors'])}; oversized files skipped: {len(report['oversize'])}.",
        'Magic is not proof of a shader. Plausible headers require the NVN zero prefix and stage/header shape;',
        'they still require a shader code size and valid control context before extraction or compilation.','']
    for x in report['outside_hits']:
        lines.append(f"{x['file']} +0x{x['offset']:x}: {x['kind']}, plausible_header={x['plausible_header']}, aligned8={x['aligned_8']}, SPH={x['sph0']}")
    (ev/'audit-raw-sph.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(complete=report['complete'],inside=dict(inside),outside=dict(outside),errors=report['errors'],seconds=report['elapsed_seconds'])),flush=True)


if __name__=='__main__':main()
