"""Read-only scan of local 2.0.2 RomFS for validated BNSH containers.

Raw containers stay in private-data. No game execution or console connection.
"""
from pathlib import Path
import argparse, hashlib, json, struct, sys, time
from forecast import ROOT, DEFAULT_PC


def bnsh_headers(data):
    start=0
    while True:
        pos=data.find(b'BNSH\0\0\0\0',start)
        if pos<0:return
        start=pos+8
        if pos+0xC0>len(data):continue
        bom,block=struct.unpack_from('<H',data,pos+12)[0],struct.unpack_from('<H',data,pos+22)[0]
        size=struct.unpack_from('<I',data,pos+28)[0]
        if bom!=0xFEFF or not 0x40<=block<min(size,0x1000) or pos+size>len(data):continue
        if data[pos+block:pos+block+4]!=b'grsc':continue
        count=struct.unpack_from('<I',data,pos+block+28)[0]
        table=struct.unpack_from('<Q',data,pos+block+32)[0]
        if not 0<count<=200000 or not block+48<=table<=size-count*64:continue
        yield pos,size,count


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--all',action='store_true')
    ap.add_argument('--pc',type=Path,default=DEFAULT_PC)
    a=ap.parse_args()
    sys.path.insert(0,str(a.pc/'randomizer-lab'))
    from inspect_game import Game
    g=Game(a.pc/'update-2.0.2-20261025/game/romfs.bin',a.pc/'release-v0.1.4/ZA Recomp/zaprompts/_internal/ooz.dll')
    out=ROOT/'private-data/offline-shaders-20261028/bnsh';out.mkdir(parents=True,exist_ok=True)
    evidence=ROOT/'evidence/offline-shaders-20261028';evidence.mkdir(exist_ok=True)
    mode='all' if a.all else 'named'
    report=dict(schema=1,mode=mode,complete=False,files_checked=0,bytes_checked=0,
        containers=[],errors=[],oversize=[],source='update-2.0.2-20261025/game/romfs.bin')
    found={};last=time.monotonic();start=last
    def save():
        report['elapsed_seconds']=round(time.monotonic()-start,1)
        report['containers']=[found[k] for k in sorted(found)]
        dest=evidence/('bnsh-scan-'+mode+'.json');tmp=dest.with_suffix('.new')
        tmp.write_text(json.dumps(report,indent=2));tmp.replace(dest)
    def scan(data,where):
        report['files_checked']+=1;report['bytes_checked']+=len(data)
        for off,size,count in bnsh_headers(data):
            blob=data[off:off+size];sha=hashlib.sha256(blob).hexdigest()
            if sha not in found:
                path=out/(sha+'.bnsh')
                if path.exists():assert hashlib.sha256(path.read_bytes()).hexdigest()==sha
                else:path.write_bytes(blob)
                name_off=struct.unpack_from('<I',blob,16)[0]
                end=blob.find(b'\0',name_off,min(name_off+1024,len(blob)))
                name=blob[name_off:end].decode('utf-8',errors='replace') if 0<name_off<end else ''
                found[sha]=dict(sha256=sha,bytes=size,variations=count,name=name,sources=[])
            found[sha]['sources'].append(dict(file=where,offset=off))
    packs=g.packs if a.all else [p for p in g.packs if '.bnsh' in p['name'].lower()]
    for pi,pack in enumerate(packs):
        for r in pack['files']:
            where=pack['name']+'#'+r['hash']
            if r['size']>256<<20:
                report['oversize'].append(dict(file=where,bytes=r['size']));continue
            try:
                data=g.oodle.unpack(r['compression'],r['size'],g.pack[r['offset']:r['offset']+r['compressed_size']])
                scan(data,where)
            except Exception as error:
                report['errors'].append(dict(file=where,error=str(error)))
        if time.monotonic()-last>15:
            save();print(json.dumps(dict(packs=pi+1,total_packs=len(packs),files=report['files_checked'],bnsh=len(found))),flush=True);last=time.monotonic()
    if a.all:
        for name,(_,size) in g.entries.items():
            if name in ('arc/data.trpfs','arc/data.trpfd'):continue
            if size>256<<20:
                report['oversize'].append(dict(file=name,bytes=size));continue
            try:scan(g.read(name),name)
            except Exception as error:report['errors'].append(dict(file=name,error=str(error)))
    report['complete']=True;save()
    print(json.dumps(dict(files=report['files_checked'],bytes=report['bytes_checked'],bnsh=len(found),
        variations=sum(x['variations'] for x in found.values()),errors=len(report['errors']),oversize=len(report['oversize']),elapsed_seconds=report['elapsed_seconds'])))


if __name__=='__main__':main()
