"""Control: source Sword mesh in a neutral one-bone bind pose, isolating skeleton conversion."""
from pathlib import Path
import shutil
import struct
import sys
from build_smoliv_model import schema,encode_checked,STEM
from sword_geometry import canonical
from fbcodec import Schema

ROOT=Path(__file__).resolve().parents[1]
out=Path(sys.argv[1]);shutil.copytree(ROOT/'build/caterpie-r5/mods',out/'mods')
folder=out/'mods/smoliv-real-model/romfs/ik_pokemon/data/pm0935/pm0935_00_00';stem='pm0010_00'
s=schema('trskl')
skl=dict(transform_nodes=[dict(name='origin',parent_idx=-1,rig_idx=0,transform=dict(VecScale=dict(x=1.,y=1.,z=1.),VecRot=dict(x=0.,y=0.,z=0.),VecTranslate=dict(x=0.,y=0.,z=0.)))],
         bones=[dict(inherit_position=1,unk_bool_2=1,matrix={k:{a:float(i==j) for j,a in enumerate(('x','y','z'))} for i,k in enumerate(('x','y','z','w'))})],rig_offset=0)
(folder/(stem+'.trskl')).write_bytes(encode_checked(s,skl))
msh=schema('trmsh').decode((folder/(stem+'.trmsh')).read_bytes())
mbf=schema('trmbf').decode((folder/(stem+'.trmbf')).read_bytes())
for shape,buffer in zip(msh['meshes'],mbf['buffers']):
    layout=shape['attributes'][0];stride=layout['size'][0]['size'];attrs={a['attribute']:a.get('position',0) for a in layout['attrs']};raw=bytearray(buffer['vertex_buffer'][0]['buffer'])
    for at in range(0,len(raw),stride):
        y=struct.unpack_from('<f',raw,at+attrs[1]+4)[0];struct.pack_into('<f',raw,at+attrs[1]+4,y+.16)
        struct.pack_into('<4B',raw,at+attrs[7],0,0,0,0);struct.pack_into('<4H',raw,at+attrs[8],65535,0,0,0)
    buffer['vertex_buffer'][0]['buffer']=list(raw)
    shape['influence']=[dict(index=0,scale=float(len(raw)//stride))]
    for bound in ('min','max'):shape['bounds'][bound]['y']+=.16
(folder/(stem+'.trmsh')).write_bytes(encode_checked(schema('trmsh'),canonical(msh)))
(folder/(stem+'.trmbf')).write_bytes(encode_checked(schema('trmbf'),mbf))
small=Schema();small.add_table('Info',[('does_loop','u32'),('animation_count','u32'),('animation_rate','u32')]);small.add_table('Bone',[]);small.add_table('Track',[('tracks',('vec',('table','Bone')))]);small.add_table('Root',[('info',('table','Info')),('track',('table','Track'))]);small.root='Root'
(folder/'bind_pose.tranm').write_bytes(small.encode(dict(info=dict(does_loop=1,animation_count=1,animation_rate=30),track=dict(tracks=[]))))
s=schema('tracr','ZA/Flatbuffers');v=s.decode((folder/(STEM+'_base.tracr')).read_bytes())
for track in v['track_list']['list']:track['track_resource']['animation']={'filename':'bind_pose.tranm'}
(folder/(STEM+'_base.tracr')).write_bytes(encode_checked(s,v))
print('Static source-mesh control built',flush=True)
