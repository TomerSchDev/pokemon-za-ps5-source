"""Bounded FlatBuffers/BFBS inspection using the public reflection.fbs layout.
Retains scalar offsets for later reviewed patches; does not write game data.
"""
import struct
FMT={1:'B',2:'?',3:'b',4:'B',5:'h',6:'H',7:'i',8:'I',9:'q',10:'Q',11:'f',12:'d'}
class Buffer:
    def __init__(self,data):self.data=data
    def scalar(self,p,fmt):
        size=struct.calcsize('<'+fmt)
        if p<0 or p+size>len(self.data):raise ValueError('Out of bounds scalar')
        return struct.unpack_from('<'+fmt,self.data,p)[0]
    def pointer(self,p):
        q=p+self.scalar(p,'I')
        if not 0<=q<len(self.data):raise ValueError('Out of bounds reference')
        return q
    def fields(self,p):
        v=p-self.scalar(p,'i');n=self.scalar(v,'H');obj_size=self.scalar(v+2,'H')
        if n<4 or n%2 or n>1024 or p+obj_size>len(self.data):raise ValueError('Invalid vtable')
        return [p+o if (o:=self.scalar(v+4+2*i,'H')) else None for i in range((n-4)//2)]
    def field(self,p,i):
        t=self.fields(p);return t[i] if i<len(t) else None
    def value(self,p,i,fmt,default=0):
        q=self.field(p,i);return self.scalar(q,fmt) if q is not None else default
    def text(self,p):
        p=self.pointer(p);n=self.scalar(p,'I')
        if n>1<<20 or p+4+n>len(self.data):raise ValueError('Invalid string length')
        return self.data[p+4:p+4+n].decode('utf-8')
    def string(self,p,i,default=''):
        q=self.field(p,i);return self.text(q) if q is not None else default
    def vector(self,p,size=4):
        p=self.pointer(p);n=self.scalar(p,'I')
        if n>1000000 or p+4+n*size>len(self.data):raise ValueError('Invalid vector')
        return [p+4+i*size for i in range(n)]
    def tables(self,p,i):
        q=self.field(p,i);return [self.pointer(x) for x in self.vector(q)] if q is not None else []
class Schema:
    def __init__(self,data):
        if data[4:8]!=b'BFBS':raise ValueError('Not a BFBS schema')
        b=Buffer(data);root=b.scalar(0,'I');self.objects=[]
        for obj in b.tables(root,0):
            fields=[]
            for f in b.tables(obj,1):
                tp=b.pointer(b.field(f,1))
                fields.append(dict(name=b.string(f,0),id=b.value(f,2,'H'),offset=b.value(f,3,'H'),
                    type=dict(base=b.value(tp,0,'b'),element=b.value(tp,1,'b'),index=b.value(tp,2,'i',-1),fixed_length=b.value(tp,3,'H')),
                    default_integer=b.value(f,4,'q'),default_real=b.value(f,5,'d'),required=b.value(f,7,'?',False)))
            self.objects.append(dict(name=b.string(obj,0),is_struct=b.value(obj,2,'?',False),size=b.value(obj,4,'i'),fields=sorted(fields,key=lambda f:f['id'])))
        self.root=b.string(b.pointer(b.field(root,4)),0) if b.field(root,4) is not None else None
        self.enums=[]
        for e in b.tables(root,1):self.enums.append(dict(name=b.string(e,0),values={str(b.value(v,1,'q')):b.string(v,0) for v in b.tables(e,1)}))
    def decode(self,data,offsets=True):
        b=Buffer(data);ri=next(i for i,o in enumerate(self.objects) if o['name']==self.root)
        nodes=0
        def obj(p,idx,depth):
            nonlocal nodes
            nodes+=1
            if depth>40 or nodes>500000:raise ValueError('Decode limit')
            o=self.objects[idx];out={};loc={}
            if offsets:out['$offset']=p
            for f in o['fields']:
                t=f['type'];base=t['base'];q=p+f['offset'] if o['is_struct'] else b.field(p,f['id'])
                if q is None:
                    if base in FMT:val=f['default_real'] if base in (11,12) else f['default_integer']
                    elif base==14:val=[]
                    else:val=None
                else:
                    loc[f['name']]=q
                    val=value(q,base,t['index'],t,depth+1)
                out[f['name']]=val
            if offsets:out['$fields']=loc
            return out
        def value(p,base,idx,t,depth):
            if base in FMT:return b.scalar(p,FMT[base])
            if base==13:return b.text(p)
            if base==15:
                o=self.objects[idx];return obj(p if o['is_struct'] else b.pointer(p),idx,depth)
            if base==14:
                el=t['element'];size=struct.calcsize(FMT[el]) if el in FMT else self.objects[idx]['size'] if el==15 and self.objects[idx]['is_struct'] else 4
                return [value(q,el,idx,t,depth+1) for q in b.vector(p,size)]
            if base==17:
                el=t['element'];size=struct.calcsize(FMT[el]) if el in FMT else self.objects[idx]['size'] if el==15 and self.objects[idx]['is_struct'] else 0
                count=t['fixed_length']
                if not size or count>4096 or p+size*count>len(data):raise ValueError('Invalid fixed array')
                return [value(p+i*size,el,idx,t,depth+1) for i in range(count)]
            raise ValueError(f'Unsupported reflection base {base}')
        return obj(b.scalar(0,'I'),ri,0)
