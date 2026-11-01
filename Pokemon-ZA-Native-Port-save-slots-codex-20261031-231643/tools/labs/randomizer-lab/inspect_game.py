"""Read-only index of the locally supplied Z-A RomFS and NSO. No guest code execution."""
from pathlib import Path
import argparse,hashlib,json,mmap,re,struct,sys
ROOT=Path(__file__).resolve().parent
UP=ROOT.parents[1]/'pokeza-recomp'
sys.path.insert(0,str(UP/'tools'));sys.path.insert(0,str(UP/'tools/za'))
from trinity import FB,Oodle

def sha(b):return hashlib.sha256(b).hexdigest()
def fnv(s):
    h=0xCBF29CE484222645
    for c in s.encode():h=((h^c)*0x100000001B3)&0xffffffffffffffff
    return h
def string(fb,p):
    p+=fb.u32(p);n=fb.u32(p)
    return bytes(fb.m[p+4:p+4+n]).decode('utf-8')
class Game:
    def __init__(self,path,ooz):
        self.f=Path(path).open('rb');self.m=mmap.mmap(self.f.fileno(),0,access=mmap.ACCESS_READ)
        h=struct.unpack_from('<10Q',self.m);assert h[0]==0x50
        assert all(o+s<=len(self.m) for o,s in [(h[3],h[4]),(h[7],h[8])])
        self.entries={};dm=memoryview(self.m)[h[3]:h[3]+h[4]];fm=memoryview(self.m)[h[7]:h[7]+h[8]]
        def directory(d):
            names=[];seen=set()
            while d:
                assert d not in seen;seen.add(d)
                n=struct.unpack_from('<I',dm,d+0x14)[0];names.append(bytes(dm[d+24:d+24+n]).decode())
                d=struct.unpack_from('<I',dm,d)[0]
            return '/'.join(reversed(names))
        pos=0
        while pos+32<=len(fm):
            parent,_,off,size,_,n=struct.unpack_from('<IIQQII',fm,pos)
            name=bytes(fm[pos+32:pos+32+n]).decode();d=directory(parent)
            path=(d+'/' if d else '')+name
            assert h[9]+off+size<=len(self.m)
            self.entries[path]=(h[9]+off,size);pos+=32+((n+3)&~3)
        self.oodle=Oodle(ooz)
        start,size=self.entries['arc/data.trpfs'];self.pack=memoryview(self.m)[start:start+size];self.fb=FB(self.pack)
        assert bytes(self.pack[:8])==b'ONEPACK\0'
        rt=self.fb.u64(8);t=self.fb.table(rt+self.fb.u32(rt));n,hp=self.fb.vec(t[0]);n2,op=self.fb.vec(t[1]);assert n==n2
        d=FB(self.read('arc/data.trpfd'));dt=d.table(d.u32(0));nn,np=d.vec(dt[1])
        self.names=[string(d,np+4*i) for i in range(nn)]
        namehash={fnv(s):s for s in self.names}
        self.packs=[];self.fileindex={}
        for i in range(n):
            off=self.fb.u64(op+8*i);ph=self.fb.u64(hp+8*i);name=namehash.get(ph,f'unknown-{ph:016x}')
            t=self.fb.table(off+self.fb.u32(off));nf,fh=self.fb.vec(t[0]);nf2,fp=self.fb.vec(t[1]);assert nf==nf2
            records=[]
            for j in range(nf):
                p=fp+4*j;ft=self.fb.table(p+self.fb.u32(p));nbytes,dp=self.fb.vec(ft[4])
                comp=self.pack[ft[1]] if len(ft)>1 and ft[1] else 0xff
                size=self.fb.u64(ft[3]) if len(ft)>3 and ft[3] else nbytes
                r=dict(hash=f'{self.fb.u64(fh+8*j):016x}',offset=dp,compressed_size=nbytes,size=size,compression=comp,pack=name)
                self.fileindex.setdefault(r['hash'],[]).append(r);records.append(r)
            self.packs.append(dict(name=name,hash=f'{ph:016x}',files=records))
    def read(self,path):
        off,size=self.entries[path];return bytes(self.m[off:off+size])
    def unpack(self,r):
        if r['size']>64<<20:raise ValueError('File exceeds inspection bound')
        return self.oodle.unpack(r['compression'],r['size'],self.pack[r['offset']:r['offset']+r['compressed_size']])
    def file(self,path):
        records=self.fileindex[f'{fnv(path):016x}'];assert len(records)==1
        return self.unpack(records[0])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--game',type=Path,required=True);p.add_argument('--ooz',required=True);a=p.parse_args()
    g=Game(a.game/'romfs.bin',a.ooz);ROOT.mkdir(exist_ok=True)
    (ROOT/'romfs-index.json').write_text(json.dumps(g.entries,indent=2))
    (ROOT/'pack-index.json').write_text(json.dumps(g.packs,indent=2))
    from nso import Nso
    n=Nso(a.game/'exefs/main'); strings=[]
    for m in re.finditer(rb'[ -~]{6,}',n.image):
        s=m.group().decode()
        if re.search(r'trdata|encount|spawner|mega|boss|pokedata|personal|initial.*pokemon|partner|buddy',s,re.I):
            strings.append(dict(va=f'{0x7000000000+m.start():x}',offset=m.start(),value=s))
    (ROOT/'binary-strings.json').write_text(json.dumps(strings,indent=2))
    (ROOT/'main-image.bin').write_bytes(n.image)
    selected=[p['name'] for p in g.packs if re.search('trdata|encount|spawner|mega|boss|pokedata|personal|event.*pokemon|partner|buddy',p['name'],re.I)]
    (ROOT/'candidate-packs.json').write_text(json.dumps(selected,indent=2))
    print(json.dumps(dict(build_id=n.build_id,main_sha256=sha((a.game/'exefs/main').read_bytes()),romfs_files=len(g.entries),packs=len(g.packs),packed_file_hashes=len(g.fileindex),candidate_packs=selected[:100],strings=len(strings)),indent=2))
